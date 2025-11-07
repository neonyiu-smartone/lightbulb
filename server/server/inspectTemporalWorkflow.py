import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional

import httpx
from pmconnector import ResourceConnector
from pydantic import BaseModel
from temporalio.client import Client

logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    )


class WorkflowInfo(BaseModel):
    id: str
    task_queue: str
    status: int
    status_name: str
    scheduled_at: datetime


class WorkflowMonitor(BaseModel):
    workflow_type: str
    dashboard_id: str
    schedule_id: Optional[str] = None
    interval_minute: int = 15

# it seems that the workflow status is not being reported correctly

class WorkflowStatusReport:
    def __init__(
        self,
        temporal_client: Client,
        report_endpoint: Optional[str] = None,
        workflow_monitor_list: Optional[List[WorkflowMonitor]] = None,
        clickhouse_client: Optional[object] = None,
    ) -> None:
        self.workflow_monitor_list = workflow_monitor_list or []
        self.client = temporal_client
        self.monitor_time = datetime.now()
        self.report_endpoint = report_endpoint
        self.clickhouse_client = clickhouse_client

        if self.clickhouse_client is None:
            try:
                self.clickhouse_client = ResourceConnector().connect_clickhouse_static('monitor')
            except Exception as error:
                logger.warning("Failed to connect to ClickHouse for workflow monitor configs: %s", error)
                self.clickhouse_client = None

    @staticmethod
    def extract_interval_minutes(schedule_entry: Any) -> Optional[int]:
        """Derive schedule interval (in minutes) from a Temporal schedule list entry."""
        schedule = getattr(schedule_entry, 'schedule', None)
        if schedule is None:
            return None

        intervals = getattr(schedule, 'intervals', None)
        if not intervals:
            spec = getattr(schedule, 'spec', None)
            intervals = getattr(spec, 'intervals', None) if spec else None

        if not intervals:
            return None

        best_seconds: Optional[float] = None
        for interval in intervals:
            every = getattr(interval, 'every', None)
            if every is None or not hasattr(every, 'total_seconds'):
                continue
            seconds = every.total_seconds()
            if seconds <= 0:
                continue
            if best_seconds is None or seconds < best_seconds:
                best_seconds = seconds

        if best_seconds is None:
            return None

        return max(int(best_seconds // 60) or 1, 1)

    def ensure_workflow_service(self, service_id: str) -> None:
        """Ensure a ClickHouse service row exists for the given workflow service id."""
        if self.clickhouse_client is None:
            return

        sanitized_id = service_id.replace("'", "''")

        check_query = f"""
        SELECT count()
        FROM monitor.services
        WHERE service_id = '{sanitized_id}'
        """

        try:
            existing = self.clickhouse_client.execute(check_query)
            if existing and existing[0][0] > 0:
                return

            insert_query = """
            INSERT INTO monitor.services
            (service_id, label, service_type, status_config, metric_config, enabled, created_at, updated_at)
            VALUES ('{service_id}', '{label}', '{service_type}', '{status_config}', '{metric_config}', 1, now(), now())
            """.format(
                service_id=sanitized_id,
                label=sanitized_id,
                service_type='Workflow',
                status_config=json.dumps({}).replace("'", "''"),
                metric_config=json.dumps({}).replace("'", "''")
            )

            self.clickhouse_client.execute(insert_query)
            logger.info("Auto-created workflow service '%s'", service_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to ensure workflow service %s: %s", service_id, exc)

    def extract_workflow_type(self, schedule_entry: Any) -> Optional[str]:
        """Extract the target workflow type from a schedule entry."""
        schedule = getattr(schedule_entry, 'schedule', None)
        if schedule is None:
            return None

        action = getattr(schedule, 'action', None)
        start_workflow = getattr(action, 'start_workflow', None) if action else None

        type_candidates: list[str] = []

        if start_workflow is not None:
            candidate = getattr(start_workflow, 'workflow_type', None)
            if isinstance(candidate, str):
                type_candidates.append(candidate)
            elif hasattr(candidate, 'name'):
                name_attr = getattr(candidate, 'name')
                if isinstance(name_attr, str):
                    type_candidates.append(name_attr)
            elif isinstance(candidate, dict):
                name_value = candidate.get('name')
                if isinstance(name_value, str):
                    type_candidates.append(name_value)

        if not type_candidates and hasattr(schedule_entry, 'id'):
            id_value = getattr(schedule_entry, 'id', '')
            if isinstance(id_value, str):
                type_candidates.append(id_value)

        for candidate in type_candidates:
            workflow_type = candidate.strip()
            if workflow_type:
                return workflow_type

        return None

    async def sync_temporal_workflow_services(self) -> List[WorkflowMonitor]:
        """Sync Temporal schedules into ClickHouse services and build monitor list."""
        try:
            schedules_iterator = await self.client.list_schedules()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to list Temporal schedules: %s", exc)
            return []

        monitors: List[WorkflowMonitor] = []
        async for entry in schedules_iterator:
            schedule_id_raw = getattr(entry, 'id', None)
            schedule_id = schedule_id_raw if isinstance(schedule_id_raw, str) and schedule_id_raw else None

            workflow_type = self.extract_workflow_type(entry)
            if not workflow_type:
                if schedule_id:
                    logger.debug(
                        "Falling back to schedule id %s as workflow type because action workflow type is missing",
                        schedule_id,
                    )
                    workflow_type = schedule_id
                else:
                    logger.debug(
                        "Skipping schedule %s because workflow type is missing",
                        schedule_id_raw or 'unknown',
                    )
                    continue

            interval_minute = self.extract_interval_minutes(entry) or 15
            service_id = workflow_type
            monitor_schedule_id = schedule_id or workflow_type

            self.ensure_workflow_service(service_id)
            monitors.append(
                WorkflowMonitor(
                    workflow_type=workflow_type,
                    dashboard_id=service_id,
                    schedule_id=monitor_schedule_id,
                    interval_minute=interval_minute,
                )
            )
            logger.debug(
                "Prepared monitor for schedule %s (workflow type %s) with interval %d minutes",
                monitor_schedule_id,
                workflow_type,
                interval_minute,
            )

        if monitors:
            logger.info("Synchronized %d Temporal workflow services", len(monitors))

        return monitors

    @staticmethod
    def id_to_datetime(workflow_id: str) -> datetime:
        match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', workflow_id)
        if not match:
            raise ValueError(f"Invalid workflow ID format: {workflow_id}")
        return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S") + timedelta(hours=8)

    def compute_monitor_window(self, interval_minute: int) -> tuple[datetime, datetime, timedelta]:
        """Return the monitoring window start, due time, and applied grace."""
        interval_minutes = max(interval_minute, 1)
        minute_aligned = self.monitor_time.replace(second=0, microsecond=0)
        reference = datetime(1970, 1, 1)

        grace = timedelta(hours=2) if interval_minutes > 1440 else timedelta()
        adjusted_time = minute_aligned - grace
        if adjusted_time < reference:
            adjusted_time = reference

        elapsed_minutes = int((adjusted_time - reference).total_seconds() // 60)
        period_index = elapsed_minutes // interval_minutes
        due_time = reference + timedelta(minutes=period_index * interval_minutes)
        window_start = due_time - timedelta(minutes=interval_minutes)
        return window_start, due_time, grace

    @staticmethod
    def check_workflow_schedule_time(scheduled_at: datetime, window_start: datetime, window_end: datetime) -> bool:
        return window_start < scheduled_at <= window_end

    async def fetch_workflows_in_window(
        self,
        schedule_id: Optional[str],
        workflow_type: str,
        window_start: datetime,
        window_end: datetime,
    ) -> List[WorkflowInfo]:
        """Collect workflow executions within the target window using schedule or workflow filters."""
        queries: list[tuple[str, str]] = []

        sanitized_schedule: Optional[str] = None
        if schedule_id:
            sanitized_schedule = schedule_id.replace('"', '\"')
            queries.append((
                'schedule_id',
                f'WorkflowId STARTS_WITH "{sanitized_schedule}"',
            ))

        if workflow_type:
            sanitized_type = workflow_type.replace('"', '\"')
            # Avoid duplicate query when schedule id already equals workflow type
            if not sanitized_schedule or sanitized_type != sanitized_schedule:
                queries.append((
                    'workflow_type',
                    f'WorkflowType="{sanitized_type}"',
                ))

        collected: dict[str, WorkflowInfo] = {}

        for label, query in queries:
            logger.debug("Querying Temporal with %s filter: %s", label, query)
            try:
                iterator = self.client.list_workflows(query=query)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Failed to list workflows using %s filter (%s): %s", label, query, exc)
                continue

            async for wf in iterator:
                try:
                    scheduled_at = self.id_to_datetime(wf.id)
                except ValueError:
                    logger.debug("Skipping workflow execution %s with unparsable id", wf.id)
                    continue

                if not self.check_workflow_schedule_time(scheduled_at, window_start, window_end):
                    continue

                if wf.id in collected:
                    continue

                collected[wf.id] = WorkflowInfo(
                    id=wf.id,
                    task_queue=wf.task_queue,
                    status=wf.status.value,
                    status_name=wf.status.name,
                    scheduled_at=scheduled_at,
                )

        return list(collected.values())

    def refresh_monitor_configs(self, monitors: Optional[List[WorkflowMonitor]] = None) -> None:
        """Update the active monitor list, falling back to defaults when empty."""
        if monitors:
            normalized: List[WorkflowMonitor] = []
            for monitor in monitors:
                if monitor.schedule_id:
                    normalized.append(monitor)
                else:
                    normalized.append(
                        monitor.model_copy(update={'schedule_id': monitor.workflow_type})
                    )
            self.workflow_monitor_list = normalized
            return

        if not self.workflow_monitor_list:
            logger.info("No workflow monitor configs available after sync; reporting run will skip")

    @staticmethod
    def is_interval_due(current_time: datetime, interval_minute: int) -> bool:
        minute_aligned = current_time.replace(second=0, microsecond=0)
        if interval_minute <= 0:
            return False
        reference = datetime(1970, 1, 1)
        elapsed_minutes = int((minute_aligned - reference).total_seconds() // 60)
        if elapsed_minutes < 0:
            return False

        if interval_minute > 1440:
            elapsed_minutes -= 120
            if elapsed_minutes < 0:
                return False

        return elapsed_minutes % interval_minute == 0

    async def report_status(
        self,
        workflow_type: str,
        service_id: str,
        schedule_id: Optional[str],
        interval_minute: int = 15,
    ):
        if not self.report_endpoint:
            logger.warning("Report endpoint not configured; skipping status for %s", service_id)
            return "skipped_no_endpoint"

        window_start, due_time, grace = self.compute_monitor_window(interval_minute)
        if interval_minute > 1440 and self.monitor_time < due_time + grace:
            logger.debug(
                "Skipping workflow %s (schedule %s) monitoring until %s (within 2h grace)",
                workflow_type,
                schedule_id or workflow_type,
                (due_time + grace).isoformat(),
            )
            return "pending_grace"

        workflow_in_period = await self.fetch_workflows_in_window(
            schedule_id or workflow_type,
            workflow_type,
            window_start,
            due_time,
        )

        status = 1
        message = "Execution is delayed"

        logger.info(
            "Evaluating workflow %s (service %s, schedule %s) interval=%d window=(%s -> %s)",
            workflow_type,
            service_id,
            schedule_id or workflow_type,
            interval_minute,
            window_start.isoformat(),
            due_time.isoformat(),
        )

        if not workflow_in_period:
            logger.warning(
                "No executions found for workflow %s in window ending %s; reporting delayed",
                workflow_type,
                due_time.isoformat(),
            )
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.report_endpoint}/status/{service_id}",
                    json={"message": message, "status_code": status},
                    timeout=10,
                )
                if response.status_code == 200:
                    return "done"
                logger.error(
                    "Failed to send status to %s/status/%s: %s",
                    self.report_endpoint,
                    service_id,
                    response.status_code,
                )
            return

        last_workflow = max(workflow_in_period, key=lambda wf: wf.scheduled_at)
        logger.debug(
            "Latest execution picked for workflow %s: %s (%s)",
            workflow_type,
            last_workflow.id,
            last_workflow.status_name,
        )

        if last_workflow.status_name == 'RUNNING':
            prev_window_end = window_start
            prev_window_start = prev_window_end - timedelta(minutes=interval_minute)

            previous_candidates = await self.fetch_workflows_in_window(
                schedule_id or workflow_type,
                workflow_type,
                prev_window_start,
                prev_window_end,
            )

            previous_workflow = max(
                (wf for wf in previous_candidates if wf.scheduled_at == prev_window_end),
                default=None,
                key=lambda wf: wf.scheduled_at,
            )

            if previous_workflow:
                last_workflow = previous_workflow
                message = "Execution in progress"
                logger.debug(
                    "Using previous execution %s for workflow %s due to current RUNNING state",
                    previous_workflow.id,
                    workflow_type,
                )
            else:
                message = "Execution in progress"
                logger.debug(
                    "Workflow %s still running; no completed prior run found",
                    workflow_type,
                )

        if last_workflow.status_name != 'RUNNING':
            match last_workflow.status:
                case 3 | 4 | 5 | 7:
                    status = 2
                    message = "Execution failed"
                case 2:
                    status = 0
                    message = "Execution completed"

        logger.info(
            "Posting status for workflow %s (service %s, schedule %s): code=%d message='%s' source_run=%s",
            workflow_type,
            service_id,
            schedule_id or workflow_type,
            status,
            message,
            last_workflow.id,
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.report_endpoint}/status/{service_id}",
                json={"message": message, "status_code": status},
                timeout=10,
            )
            if response.status_code == 200:
                return "done"

            logger.error(
                "Failed to send status to %s/status/%s: %s",
                self.report_endpoint,
                service_id,
                response.status_code,
            )

    async def run_report_status(self):
        # Refresh monitor timestamp so each polling cycle uses the current wall clock
        logger.info("Starting workflow monitor run")
        discovered_monitors = await self.sync_temporal_workflow_services()
        logger.debug("Discovered %d workflows from Temporal", len(discovered_monitors))
        self.monitor_time = datetime.now()
        if discovered_monitors:
            self.refresh_monitor_configs(discovered_monitors)
        else:
            self.refresh_monitor_configs()

        if not self.workflow_monitor_list:
            logger.info("No workflow monitors configured from Temporal; skipping reporting run")
            return

        eligible_configs = [
            config for config in self.workflow_monitor_list
            if self.is_interval_due(self.monitor_time, config.interval_minute)
        ]

        logger.info(
            "Monitor snapshot at %s: %d total configs, %d due",
            self.monitor_time.isoformat(),
            len(self.workflow_monitor_list),
            len(eligible_configs),
        )

        if not eligible_configs:
            logger.debug("No workflow monitors due at %s", self.monitor_time.isoformat())
            return

        tasks = [
            asyncio.create_task(
                self.report_status(
                    config.workflow_type,
                    config.dashboard_id,
                    config.schedule_id,
                    config.interval_minute,
                )
            )
            for config in eligible_configs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Report results: %s", results)


if __name__ == "__main__":
    async def run():
        client: Client = await Client.connect("temporal-frontend-headless.temporal.svc.cluster.local:7233", namespace="default")
        report_endpoint = 'http://localhost:14306'
        status_report = WorkflowStatusReport(client, report_endpoint)
        await status_report.run_report_status()

    asyncio.run(run())