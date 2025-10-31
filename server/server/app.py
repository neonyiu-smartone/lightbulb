import asyncio
import random
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
import requests
import uvicorn
from fastapi import FastAPI, Security, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from sse_starlette import EventSourceResponse
from typing import List, Dict, Set, Any, Optional
from collections import defaultdict
from server.orm import db
from server.model import (
    FlowchartResponse, ServiceNode, ServiceRelation,
    ServiceCreateRequest, ServiceUpdateRequest, ServiceResponse,
    RelationCreateRequest, RelationUpdateRequest, RelationResponse,
    BulkOperationResponse, ServiceStatus, ServiceStatusSummary, ServiceStatusMap,
    ServiceStatusUpdateRequest, Notification, ServiceFailureRecord
)
from pydantic import BaseModel, Field
from pmconnector import ResourceConnector
from inspectTemporalWorkflow import WorkflowStatusReport
from temporalio.client import Client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

log_config = uvicorn.config.LOGGING_CONFIG
log_config['formatters']['access']['fmt'] = '%(asctime)s - %(levelname)s - %(message)s'
log_config['formatters']['default']['fmt'] = '%(asctime)s - %(levelname)s - %(message)s'

notification_queue: dict[str, asyncio.Queue[Notification]] = {}
ALERT_WEBHOOK_ENDPOINT = os.getenv('ALERT_WEBHOOK_ENDPOINT', "https://alert-service.nova.hksmartone.com/api/email")


WATCHER_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS monitor.service_watchers
ON CLUSTER production
(
    service_id String,
    email String,
    created_at DateTime DEFAULT now()
)
ENGINE = ReplicatedMergeTree()
ORDER BY (service_id, email)
"""

WORKFLOW_MONITOR_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS monitor.workflow_monitor_configs
ON CLUSTER production
(
    workflow_type String,
    service_id String,
    interval_minute UInt16
)
ENGINE = ReplicatedMergeTree()
ORDER BY (workflow_type, service_id)
"""


def ensure_watcher_table(client: Any) -> None:
    client.execute(WATCHER_TABLE_DDL)


def ensure_workflow_monitor_table(client: Any) -> None:
    client.execute(WORKFLOW_MONITOR_TABLE_DDL)


def load_service_relations(client: Any) -> Dict[str, List[str]]:
    relations_query = """
    SELECT source_service_id, target_service_id
    FROM monitor.service_relations
    WHERE enabled = 1
    """
    result = client.execute(relations_query)
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for source, target in result:
        adjacency[source].append(target)
    return adjacency


def collect_downstream_services(service_id: str, client: Any) -> Set[str]:
    adjacency = load_service_relations(client)
    downstream: Set[str] = set()
    stack = [service_id]
    while stack:
        current = stack.pop()
        for neighbor in adjacency.get(current, []):
            if neighbor not in downstream:
                downstream.add(neighbor)
                stack.append(neighbor)
    return downstream


def fetch_watchers(client: Any, service_ids: Set[str]) -> Dict[str, List[str]]:
    if not service_ids:
        return {}
    service_list = ",".join(f"'{sid.replace("'", "''")}'" for sid in service_ids)
    query = f"""
    SELECT service_id, email
    FROM monitor.service_watchers
    WHERE service_id IN ({service_list})
    """
    result = client.execute(query)
    watchers: Dict[str, List[str]] = defaultdict(list)
    for service_id, email in result:
        watchers[email].append(service_id)
    return watchers


def fetch_service_labels(client: Any, service_ids: Set[str]) -> Dict[str, str]:
    if not service_ids:
        return {}
    service_list = ",".join(f"'{sid.replace("'", "''")}'" for sid in service_ids)
    query = f"""
    SELECT service_id, label
    FROM monitor.services
    WHERE service_id IN ({service_list})
    """
    result = client.execute(query)
    return {service_id: label for service_id, label in result}


def resolve_date_range(start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime]:
    """Resolve inclusive date input strings into an exclusive datetime range."""
    today = datetime.now().date()
    try:
        start_date = datetime.strptime(start, '%Y-%m-%d').date() if start else today
    except ValueError as exc:
        raise HTTPException(status_code=400, detail='Invalid start date format. Use YYYY-MM-DD.') from exc

    if end:
        try:
            end_date_candidate = datetime.strptime(end, '%Y-%m-%d').date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='Invalid end date format. Use YYYY-MM-DD.') from exc
    else:
        end_date_candidate = start_date + timedelta(days=1)

    if end_date_candidate < start_date:
        raise HTTPException(status_code=400, detail='End date must not be earlier than start date.')

    if end and end_date_candidate == start_date:
        end_date_candidate = end_date_candidate + timedelta(days=1)

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date_candidate, datetime.min.time())
    return start_dt, end_dt


def send_alert(email: str,
                           failing_service: Dict[str, str],
                           affected_services: List[Dict[str, str]],
                           status_code: int,
                           message: str) -> None:
    current_time = datetime.now()
    rop_window_end = current_time + timedelta(minutes=15)
    summary_labels = {failing_service['label']}
    summary_labels.update(svc['label'] for svc in affected_services)
    affected_summary = ", ".join(sorted(summary_labels))
    table_rows = []
    seen_ids: Set[str] = set()
    combined_services = [failing_service, *affected_services]
    for svc in combined_services:
        if svc['service_id'] in seen_ids:
            continue
        seen_ids.add(svc['service_id'])
        table_rows.append({
            'Service ID': svc['service_id'],
            'Service Name': svc['label']
        })

    payload = {
        "subject": f"Real Time Service Alert | {failing_service['label']}",
        "recipients": [email],
        "content": [
            {
                "type": "header",
                "level": 3,
                "content": "Real Time Service Alert"
            },
            {
                "type": "text",
                "content": (
                    f"Current window: {current_time:%Y-%m-%d %H:%M} - {rop_window_end:%Y-%m-%d %H:%M}\n"
                    f"Failing service: {failing_service['label']} ({failing_service['service_id']})\n"
                    f"Status code: {status_code}\n"
                    f"Message: {message}"
                ),
                "inline": False
            },
            {
                "type": "text",
                "content": f"Affected services: {affected_summary}",
                "inline": False
            },
            {
                "type": "table",
                "columns": ['Service ID', 'Service Name'],
                "content": table_rows
            }
        ]
    }

    try:
        response = requests.post(ALERT_WEBHOOK_ENDPOINT, json=payload, timeout=5)
        if response.status_code >= 400:
            logging.error("Failed to send alert placeholder for %s: %s", email, response.text)
    except Exception as exc:
        logging.error("Error calling alert webhook for %s: %s", email, exc)


def notify_watchers_for_failure(client: Any, failing_service_id: str, status_code: int, message: str) -> None:
    impacted_services = {failing_service_id}
    impacted_services.update(collect_downstream_services(failing_service_id, client))
    watcher_map = fetch_watchers(client, impacted_services)
    if not watcher_map:
        return
    service_labels = fetch_service_labels(client, impacted_services)
    failing_service_payload = {
        "service_id": failing_service_id,
        "label": service_labels.get(failing_service_id, failing_service_id)
    }
    for email, services in watcher_map.items():
        affected_payload = [
            {
                "service_id": sid,
                "label": service_labels.get(sid, sid)
            }
            for sid in services
        ]
        send_alert(email, failing_service_payload, affected_payload, status_code, message)

async def notify(notification: Notification):
    for key, queue in notification_queue.items():
        await queue.put(notification)

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # connector = pmconnector.ResourceConnector()
#     # data = connector.read_secret('postgres', 'cellist')
#     # if db.provider is None:
#     #     db.bind(
#     #         provider='postgres',
#     #         user=data['username'],
#     #         password=data['password'],
#     #         host=data['host'],
#     #         database=data['database'],
#     #     )
#
#     if db.provider is None:
#         db.bind(
#             provider='sqlite',
#             filename='database.sqlite',
#             create_db=True
#         )
#         db.generate_mapping(create_tables=True)
#         # logger = logging.getLogger('refresh_clickhouse')
#     yield
#     db.disconnect()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(periodic_workflow_report())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://localhost:5176', 'https://lightbulb.nova.hksmartone.com'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*']
)

@app.get('/')
def get_health():
    return {'health': 'ok'}


@app.get('/flowchart', response_model=FlowchartResponse)
def get_service_schema():
    """Get the service schema from the React Flow chart."""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Query services from monitor.services table
        services_query = """
        SELECT 
            service_id,
            label,
            service_type
        FROM monitor.services 
        WHERE enabled = 1
        ORDER BY service_id
        """
        
        services_result = client.execute(services_query)
        service_nodes = [
            ServiceNode(
                service_id=row[0],
                label=row[1], 
                service_type=row[2]
            )
            for row in services_result
        ]
        
        # Query service relations from monitor.service_relations table
        relations_query = """
        SELECT 
            relation_id,
            source_service_id,
            target_service_id
        FROM monitor.service_relations 
        WHERE enabled = 1
        ORDER BY source_service_id, target_service_id
        """
        
        relations_result = client.execute(relations_query)
        service_relations = [
            ServiceRelation(
                relation_id=row[0],
                source=row[1],
                target=row[2]
            )
            for row in relations_result
        ]

        return FlowchartResponse(
            serviceNodes=service_nodes,
            serviceRelations=service_relations
        )

    except Exception as e:
        logging.error(f"Failed to query flowchart data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve flowchart data: {str(e)}"
        )


@app.get('/status/{service_id}', response_model=ServiceStatusSummary)
def get_service_status(service_id: str, start: Optional[str] = None, end: Optional[str] = None):
    """Get service status aggregated over the requested period."""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')

        start_dt, end_dt = resolve_date_range(start, end)
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        sanitized_service_id = service_id.replace("'", "''")

        query = f"""
        SELECT
            service_id,
            toDateTime('{start_str}') AS range_start,
            maxMerge(last_check) AS last_check,
            argMaxMerge(last_status_code) AS last_status_code,
            argMaxMerge(last_message) AS last_message,
            countMerge(check_count) AS check_count,
            sumMerge(failure_count) AS failure_count
        FROM monitor.service_status_summary
        WHERE service_id = '{sanitized_service_id}'
          AND stime >= toDateTime('{start_str}')
          AND stime < toDateTime('{end_str}')
        GROUP BY service_id, range_start
        ORDER BY service_id
        """

        result = client.execute(query)

        if not result:
            raise HTTPException(
                status_code=404, 
                detail=f"No status found for service '{service_id}'"
            )
            
        row = result[0]
        return ServiceStatusSummary(
            service_id=service_id,
            stime=row[1],
            last_check=row[2],
            last_status_code=row[3],
            last_message=row[4],
            check_count=row[5],
            failed_count=row[6]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get status for service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve service status: {str(e)}"
        )

@app.get('/status/{service_id}/failures', response_model=List[ServiceFailureRecord])
def get_recent_service_failures(service_id: str, limit: int = 5, start: Optional[str] = None, end: Optional[str] = None):
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')

        sanitized_service_id = service_id.replace("'", "''")
        start_dt, end_dt = resolve_date_range(start, end)
        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
        SELECT service_id, time, message
        FROM monitor.service_status
        WHERE service_id = '{sanitized_service_id}'
          AND status_code = 2
          AND time >= toDateTime('{start_str}')
          AND time < toDateTime('{end_str}')
        ORDER BY time DESC
        LIMIT {max(limit, 0)}
        """

        result = client.execute(query)
        return [
            ServiceFailureRecord(
                service_id=row[0],
                time=row[1].strftime('%Y-%m-%d %H:%M:%S') if hasattr(row[1], 'strftime') else str(row[1]),
                message=row[2]
            )
            for row in result
        ]

    except Exception as e:
        logging.error(f"Failed to fetch failure history for service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve service failure history: {str(e)}"
        )


# SSE endpoint for real-time status updates
@app.get('/api/status/stream')
async def stream_service_status(request: Request):
    """Stream real-time service status updates via Server-Sent Events"""
    ts = datetime.now().timestamp()
    items = ['potato', 'orange', 'wagyu']
    name = random.choice(items)
    key = f'{name}_{ts}'
    notification_queue[key] = asyncio.Queue()

    async def event_generator(req: Request):        
        while True:
            
            if await req.is_disconnected():
                del notification_queue[key]
                break
            try:
                event = notification_queue[key].get_nowait()
                yield event.model_dump_json()
            except asyncio.QueueEmpty as e:
                await asyncio.sleep(1)
 
    g = event_generator(request)

    return EventSourceResponse(g)


@app.post('/status/{service_id}', response_model=ServiceStatus)
async def update_service_status(service_id: str, status_update: ServiceStatusUpdateRequest):
    """
    Update the status of a specific service.
    
    This endpoint accepts status updates for a service and stores them in the ClickHouse database.
    It supports both basic status information and additional metrics like CPU/memory usage.
    """
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Validate that the service exists
        service_check_query = """
        SELECT COUNT(*) FROM monitor.services 
        WHERE service_id = '{service_id}' AND enabled = 1
        """.format(service_id=service_id)
        
        service_exists = client.execute(service_check_query)
        if service_exists[0][0] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found or disabled"
            )
        
        # Prepare the insert query - using the actual table schema from bootstrap.py
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert the status update into ClickHouse
        insert_query = """
        INSERT INTO monitor.service_status 
        (service_id, time, status_code, message)
        VALUES ('{service_id}', '{time}', {status_code}, '{message}')
        """.format(
            service_id=service_id,
            time=current_time,
            status_code=status_update.status_code,
            message=status_update.message.replace("'", "\'"),  # Escape single quotes
        )
        
        client.execute(insert_query)
        
        logging.info(f"Status updated for service '{service_id}': status_code={status_update.status_code}, message='{status_update.message}'")
        await notify(Notification(service_id=service_id))

        if status_update.status_code == 2:
            try:
                ensure_watcher_table(client)
                notify_watchers_for_failure(client, service_id, status_update.status_code, status_update.message)
            except Exception as alert_error:
                logging.error(f"Failed to process watcher alerts for service '{service_id}': {alert_error}")

        # Return the updated status in the expected format
        return ServiceStatus(
            service_id=service_id,
            status_code=status_update.status_code,
            message=status_update.message,
            time=current_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update status for service '{service_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update service status: {str(e)}"
        )


@app.post('/trace')
def get_service_run_trace():
    pass


class UpdateTraceRequest(BaseModel):
    service_id: str
    timestamp: str


class ServiceWatcherRequest(BaseModel):
    email: str


class ServiceWatcherResponse(BaseModel):
    service_id: str
    email: str
    created_at: str


class WorkflowMonitorConfigRequest(BaseModel):
    workflow_type: str = Field(..., min_length=1)
    service_id: str = Field(..., min_length=1)
    interval_minute: int = Field(default=15, ge=1, le=1440)


class WorkflowMonitorConfigResponse(BaseModel):
    workflow_type: str
    service_id: str
    interval_minute: int



@app.post('/update-trace')
def update_service_run_trace(update_trace_request: UpdateTraceRequest):
    pass


@app.get('/error_log/{service_id}')
def get_service_error_log():
    pass


# @app.get('/assets/{path:path}')
# def serve_static(path: str):
#     file_path = os.path.join('dist/assets', path)
#     if path.endswith('.css'):
#         return FileResponse(file_path, media_type='text/css')
#     elif path.endswith('.js'):
#         return FileResponse(file_path, media_type='text/javascript')


# @app.get('/{path:path}')
# def catch_all(path: str):
#     return FileResponse(os.path.join('dist/index.html'))


# Admin API Endpoints - Service Management

@app.get('/api/admin/services', response_model=List[ServiceResponse])
def list_services(skip: int = 0, limit: int = 100):
    """List all services with pagination"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        query = """
        SELECT 
            service_id,
            label,
            service_type,
            status_config,
            metric_config,
            enabled,
            created_at,
            updated_at
        FROM monitor.services 
        ORDER BY service_id
        LIMIT {limit} OFFSET {skip}
        """.format(limit=limit, skip=skip)
        
        result = client.execute(query)
        services = [
            ServiceResponse(
                service_id=row[0],
                label=row[1],
                service_type=row[2],
                status_config=row[3],
                metric_config=row[4],
                enabled=bool(row[5]),
                created_at=str(row[6]),
                updated_at=str(row[7])
            )
            for row in result
        ]
        
        return services

    except Exception as e:
        logging.error(f"Failed to list services: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve services: {str(e)}"
        )


@app.get('/api/admin/services/{service_id}', response_model=ServiceResponse)
def get_service(service_id: str):
    """Get specific service details"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        query = """
        SELECT 
            service_id,
            label,
            service_type,
            status_config,
            metric_config,
            enabled,
            created_at,
            updated_at
        FROM monitor.services 
        WHERE service_id = '{service_id}'
        """.format(service_id=service_id)
        
        result = client.execute(query)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found"
            )
        
        row = result[0]
        return ServiceResponse(
            service_id=row[0],
            label=row[1],
            service_type=row[2],
            status_config=row[3],
            metric_config=row[4],
            enabled=bool(row[5]),
            created_at=str(row[6]),
            updated_at=str(row[7])
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve service: {str(e)}"
        )


@app.post('/api/admin/services', response_model=ServiceResponse)
def create_service(service: ServiceCreateRequest):
    """Create a new service"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Check if service already exists
        check_query = "SELECT COUNT(*) FROM monitor.services WHERE service_id = '{}'".format(service.service_id)
        existing = client.execute(check_query)
        
        if existing[0][0] > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Service '{service.service_id}' already exists"
            )
        
        # Insert new service
        insert_query = """
        INSERT INTO monitor.services 
        (service_id, label, service_type, status_config, metric_config, enabled, created_at, updated_at)
        VALUES ('{service_id}', '{label}', '{service_type}', '{status_config}', '{metric_config}', {enabled}, now(), now())
        """.format(
            service_id=service.service_id,
            label=service.label.replace("'", "''"),  # Escape single quotes
            service_type=service.service_type,
            status_config=service.status_config.replace("'", "''"),
            metric_config=service.metric_config.replace("'", "''"),
            enabled=1 if service.enabled else 0
        )
        
        client.execute(insert_query)
        
        # Return the created service
        return get_service(service.service_id)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to create service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create service: {str(e)}"
        )


@app.put('/api/admin/services/{service_id}', response_model=ServiceResponse)
def update_service(service_id: str, updates: ServiceUpdateRequest):
    """Update an existing service"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Check if service exists
        check_query = "SELECT COUNT(*) FROM monitor.services WHERE service_id = '{}'".format(service_id)
        existing = client.execute(check_query)
        
        if existing[0][0] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found"
            )
        
        # Build update query dynamically
        update_fields = []
        if updates.label is not None:
            update_fields.append(f"label = '{updates.label.replace("'", "''")}'")
        if updates.service_type is not None:
            update_fields.append(f"service_type = '{updates.service_type}'")
        if updates.status_config is not None:
            update_fields.append(f"status_config = '{updates.status_config.replace("'", "''")}'")
        if updates.metric_config is not None:
            update_fields.append(f"metric_config = '{updates.metric_config.replace("'", "''")}'")
        if updates.enabled is not None:
            update_fields.append(f"enabled = {1 if updates.enabled else 0}")
        
        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="No fields to update"
            )
        
        update_fields.append("updated_at = now()")
        
        update_query = """
        ALTER TABLE monitor.services UPDATE {fields}
        WHERE service_id = '{service_id}'
        """.format(
            fields=", ".join(update_fields),
            service_id=service_id
        )
        
        client.execute(update_query)
        
        # Return the updated service
        return get_service(service_id)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update service: {str(e)}"
        )


@app.get('/api/admin/services/{service_id}/watchers', response_model=List[ServiceWatcherResponse])
def list_service_watchers(service_id: str):
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_watcher_table(client)

        sanitized_service_id = service_id.replace("'", "''")
        query = f"""
        SELECT service_id, email, toString(created_at)
        FROM monitor.service_watchers
        WHERE service_id = '{sanitized_service_id}'
        ORDER BY email
        """

        result = client.execute(query)
        return [
            ServiceWatcherResponse(service_id=row[0], email=row[1], created_at=row[2])
            for row in result
        ]

    except Exception as e:
        logging.error(f"Failed to list watchers for service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve service watchers: {str(e)}"
        )


@app.post('/api/admin/services/{service_id}/watchers', response_model=ServiceWatcherResponse)
def add_service_watcher(service_id: str, watcher: ServiceWatcherRequest):
    email = watcher.email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email must not be empty")

    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_watcher_table(client)

        sanitized_service_id = service_id.replace("'", "''")
        sanitized_email = email.replace("'", "''")

        service_exists_query = f"""
        SELECT COUNT(*)
        FROM monitor.services
        WHERE service_id = '{sanitized_service_id}'
        """
        service_exists = client.execute(service_exists_query)
        if service_exists[0][0] == 0:
            raise HTTPException(status_code=404, detail=f"Service '{service_id}' not found")

        insert_query = f"""
        INSERT INTO monitor.service_watchers (service_id, email)
        VALUES ('{sanitized_service_id}', '{sanitized_email}')
        """
        client.execute(insert_query)

        fetch_query = f"""
        SELECT service_id, email, toString(created_at)
        FROM monitor.service_watchers
        WHERE service_id = '{sanitized_service_id}' AND email = '{sanitized_email}'
        ORDER BY created_at DESC
        LIMIT 1
        """
        row = client.execute(fetch_query)[0]
        return ServiceWatcherResponse(service_id=row[0], email=row[1], created_at=row[2])

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to add watcher for service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add service watcher: {str(e)}"
        )


@app.delete('/api/admin/services/{service_id}/watchers')
def delete_service_watcher(service_id: str, watcher: ServiceWatcherRequest):
    email = watcher.email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email must not be empty")

    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_watcher_table(client)

        sanitized_service_id = service_id.replace("'", "''")
        sanitized_email = email.replace("'", "''")

        delete_query = f"""
        ALTER TABLE monitor.service_watchers ON CLUSTER production DELETE
        WHERE service_id = '{sanitized_service_id}' AND email = '{sanitized_email}'
        """
        client.execute(delete_query)

        return {"message": f"Watcher '{email}' removed from service '{service_id}'"}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete watcher for service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete service watcher: {str(e)}"
        )


@app.get('/api/admin/workflow-monitors', response_model=List[WorkflowMonitorConfigResponse])
def list_workflow_monitors():
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_workflow_monitor_table(client)

        query = """
        SELECT workflow_type, service_id, interval_minute
        FROM monitor.workflow_monitor_configs
        ORDER BY workflow_type, service_id
        """

        rows = client.execute(query)
        return [
            WorkflowMonitorConfigResponse(
                workflow_type=row[0],
                service_id=row[1],
                interval_minute=int(row[2])
            )
            for row in rows
        ]

    except Exception as exc:
        logging.error(f"Failed to list workflow monitors: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to list workflow monitors: {exc}")


@app.post('/api/admin/workflow-monitors', response_model=WorkflowMonitorConfigResponse, status_code=201)
def add_workflow_monitor(config: WorkflowMonitorConfigRequest):
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_workflow_monitor_table(client)

        workflow_type = config.workflow_type.strip()
        service_id = config.service_id.strip()
        interval_minute = config.interval_minute

        if not workflow_type or not service_id:
            raise HTTPException(status_code=400, detail='workflow_type and service_id must not be empty')

        sanitized_workflow = workflow_type.replace("'", "''")
        sanitized_service = service_id.replace("'", "''")

        exists_query = f"""
        SELECT COUNT(*)
        FROM monitor.workflow_monitor_configs
        WHERE workflow_type = '{sanitized_workflow}' AND service_id = '{sanitized_service}'
        """
        existing = client.execute(exists_query)
        if existing and existing[0][0] > 0:
            raise HTTPException(status_code=409, detail='Workflow monitor config already exists')

        insert_query = f"""
        INSERT INTO monitor.workflow_monitor_configs (workflow_type, service_id, interval_minute)
        VALUES ('{sanitized_workflow}', '{sanitized_service}', {interval_minute})
        """
        client.execute(insert_query)

        return WorkflowMonitorConfigResponse(
            workflow_type=workflow_type,
            service_id=service_id,
            interval_minute=interval_minute
        )

    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Failed to add workflow monitor config: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to add workflow monitor config: {exc}")


@app.delete('/api/admin/workflow-monitors/{workflow_type}/{service_id}')
def delete_workflow_monitor(workflow_type: str, service_id: str):
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        ensure_workflow_monitor_table(client)

        sanitized_workflow = workflow_type.replace("'", "''")
        sanitized_service = service_id.replace("'", "''")

        delete_query = f"""
        ALTER TABLE monitor.workflow_monitor_configs ON CLUSTER production DELETE
        WHERE workflow_type = '{sanitized_workflow}' AND service_id = '{sanitized_service}'
        """
        client.execute(delete_query)

        return {"message": f"Workflow monitor '{workflow_type}' for service '{service_id}' removed"}

    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"Failed to delete workflow monitor config: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to delete workflow monitor config: {exc}")


@app.delete('/api/admin/services/{service_id}')
def delete_service(service_id: str, force: bool = False):
    """Delete a service and optionally its relations"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Check if service exists
        check_query = "SELECT COUNT(*) FROM monitor.services WHERE service_id = '{}'".format(service_id)
        existing = client.execute(check_query)
        
        if existing[0][0] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_id}' not found"
            )
        
        # Check for dependent relations
        relations_query = """
        SELECT COUNT(*) FROM monitor.service_relations 
        WHERE source_service_id = '{service_id}' OR target_service_id = '{service_id}'
        """.format(service_id=service_id)
        
        relations_count = client.execute(relations_query)[0][0]
        
        if relations_count > 0 and not force:
            raise HTTPException(
                status_code=409,
                detail=f"Service '{service_id}' has {relations_count} dependent relations. Use force=true to delete anyway."
            )
        
        # Delete relations if force is true
        if force and relations_count > 0:
            delete_relations_query = """
            ALTER TABLE monitor.service_relations DELETE 
            WHERE source_service_id = '{service_id}' OR target_service_id = '{service_id}'
            """.format(service_id=service_id)
            client.execute(delete_relations_query)
        
        # Delete the service
        delete_query = "ALTER TABLE monitor.services DELETE WHERE service_id = '{}'".format(service_id)
        client.execute(delete_query)
        
        return {"message": f"Service '{service_id}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete service {service_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete service: {str(e)}"
        )


# Admin API Endpoints - Service Relations Management

@app.get('/api/admin/relations', response_model=List[RelationResponse])
def list_relations(skip: int = 0, limit: int = 100):
    """List all service relations with pagination"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        query = """
        SELECT 
            relation_id,
            source_service_id,
            target_service_id,
            relation_type,
            enabled,
            created_at
        FROM monitor.service_relations 
        ORDER BY source_service_id, target_service_id
        LIMIT {limit} OFFSET {skip}
        """.format(limit=limit, skip=skip)
        
        result = client.execute(query)
        relations = [
            RelationResponse(
                relation_id=row[0],
                source_service_id=row[1],
                target_service_id=row[2],
                relation_type=row[3],
                enabled=bool(row[4]),
                created_at=str(row[5])
            )
            for row in result
        ]
        
        return relations

    except Exception as e:
        logging.error(f"Failed to list relations: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve relations: {str(e)}"
        )


@app.get('/api/admin/relations/{relation_id}', response_model=RelationResponse)
def get_relation(relation_id: str):
    """Get specific relation details"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        query = """
        SELECT 
            relation_id,
            source_service_id,
            target_service_id,
            relation_type,
            enabled,
            created_at
        FROM monitor.service_relations 
        WHERE relation_id = '{relation_id}'
        """.format(relation_id=relation_id)
        
        result = client.execute(query)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Relation '{relation_id}' not found"
            )
        
        row = result[0]
        return RelationResponse(
            relation_id=row[0],
            source_service_id=row[1],
            target_service_id=row[2],
            relation_type=row[3],
            enabled=bool(row[4]),
            created_at=str(row[5])
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to get relation {relation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve relation: {str(e)}"
        )


@app.post('/api/admin/relations', response_model=RelationResponse)
def create_relation(relation: RelationCreateRequest):
    """Create a new service relation"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Validate that both services exist
        source_check = "SELECT COUNT(*) FROM monitor.services WHERE service_id = '{}'".format(relation.source_service_id)
        target_check = "SELECT COUNT(*) FROM monitor.services WHERE service_id = '{}'".format(relation.target_service_id)
        
        source_exists = client.execute(source_check)[0][0] > 0
        target_exists = client.execute(target_check)[0][0] > 0
        
        if not source_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Source service '{relation.source_service_id}' not found"
            )
        
        if not target_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Target service '{relation.target_service_id}' not found"
            )
        
        # Check for circular dependency
        circular_check = """
        WITH RECURSIVE dependency_check AS (
            SELECT source_service_id, target_service_id, 1 as depth
            FROM monitor.service_relations 
            WHERE source_service_id = '{source}'
            UNION ALL
            SELECT sr.source_service_id, sr.target_service_id, dc.depth + 1
            FROM monitor.service_relations sr
            JOIN dependency_check dc ON sr.source_service_id = dc.target_service_id
            WHERE dc.depth < 10
        )
        SELECT COUNT(*) FROM dependency_check WHERE target_service_id = '{target}'
        """.format(source=relation.source_service_id, target=relation.target_service_id)
        
        circular_result = client.execute(circular_check)
        if circular_result[0][0] > 0:
            raise HTTPException(
                status_code=409,
                detail="Creating this relation would cause a circular dependency"
            )
        
        # Generate relation ID
        import uuid
        relation_id = str(uuid.uuid4())
        
        # Insert new relation
        insert_query = """
        INSERT INTO monitor.service_relations 
        (relation_id, source_service_id, target_service_id, relation_type, enabled, created_at)
        VALUES ('{relation_id}', '{source}', '{target}', '{type}', {enabled}, now())
        """.format(
            relation_id=relation_id,
            source=relation.source_service_id,
            target=relation.target_service_id,
            type=relation.relation_type,
            enabled=1 if relation.enabled else 0
        )
        
        client.execute(insert_query)
        
        # Return the created relation
        return get_relation(relation_id)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to create relation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create relation: {str(e)}"
        )


@app.put('/api/admin/relations/{relation_id}', response_model=RelationResponse)
def update_relation(relation_id: str, updates: RelationUpdateRequest):
    """Update an existing relation"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Check if relation exists
        check_query = "SELECT COUNT(*) FROM monitor.service_relations WHERE relation_id = '{}'".format(relation_id)
        existing = client.execute(check_query)
        
        if existing[0][0] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Relation '{relation_id}' not found"
            )
        
        # Build update query dynamically
        update_fields = []
        if updates.relation_type is not None:
            update_fields.append(f"relation_type = '{updates.relation_type}'")
        if updates.enabled is not None:
            update_fields.append(f"enabled = {1 if updates.enabled else 0}")
        
        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="No fields to update"
            )
        
        update_query = """
        ALTER TABLE monitor.service_relations UPDATE {fields}
        WHERE relation_id = '{relation_id}'
        """.format(
            fields=", ".join(update_fields),
            relation_id=relation_id
        )
        
        client.execute(update_query)
        
        # Return the updated relation
        return get_relation(relation_id)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to update relation {relation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update relation: {str(e)}"
        )


@app.delete('/api/admin/relations/{relation_id}')
def delete_relation(relation_id: str):
    """Delete a service relation"""
    try:
        client = ResourceConnector().connect_clickhouse_static('monitor')
        
        # Check if relation exists
        check_query = "SELECT COUNT(*) FROM monitor.service_relations WHERE relation_id = '{}'".format(relation_id)
        existing = client.execute(check_query)
        
        if existing[0][0] == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Relation '{relation_id}' not found"
            )
        
        # Delete the relation
        delete_query = "ALTER TABLE monitor.service_relations DELETE WHERE relation_id = '{}'".format(relation_id)
        client.execute(delete_query)
        
        return {"message": f"Relation '{relation_id}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Failed to delete relation {relation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete relation: {str(e)}"
        )

async def periodic_workflow_report():
    while True:
        try:
            if datetime.now().minute % 5 == 0:
                client: Client = await Client.connect("temporal-frontend-headless.temporal.svc.cluster.local:7233",
                                                      namespace="default")
                report_endpoint = 'http://localhost:14306' 
                status_report = WorkflowStatusReport(client, report_endpoint)
                await status_report.run_report_status()
            
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error running periodic workflow report: {e}")


if __name__ == '__main__':
    uvicorn.run('app:app', host='0.0.0.0', port=14306, reload=False)