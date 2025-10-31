import logging
from datetime import datetime, timedelta
from typing import List, Optional
import re
import asyncio

import httpx
from pmconnector import ResourceConnector
from temporalio.client import Client
from pydantic import BaseModel


class WorkflowInfo(BaseModel):
    id: str
    task_queue: str
    status: int
    status_name: str
    scheduled_at: datetime


class WorkflowMonitor(BaseModel):
    workflow_type: str
    dashboard_id: str
    interval_minute: int = 15

DEFAULT_WORKFLOW_MONITORS = [
    WorkflowMonitor(workflow_type='WriteStatTable', dashboard_id='pipeline-1', interval_minute=15),
    WorkflowMonitor(workflow_type='KPIAlertWorkflow', dashboard_id='alert-2', interval_minute=15),
    WorkflowMonitor(workflow_type='WriteStatTableDU', dashboard_id='pipeline-4', interval_minute=15),
]

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
                logging.warning("Failed to connect to ClickHouse for workflow monitor configs: %s", error)
                self.clickhouse_client = None

        self.refresh_monitor_configs()

    @staticmethod
    def round_down_and_to_period_start(dt: datetime, interval_minute: int) -> datetime:
        minutes_remainder = dt.minute % interval_minute
        rounded_dt = dt - timedelta(minutes=minutes_remainder + interval_minute,
                                    seconds=dt.second,
                                    microseconds=dt.microsecond)
        return rounded_dt

    @staticmethod
    def id_to_datetime(workflow_id: str) -> datetime:
        match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', workflow_id)
        if not match:
            raise ValueError(f"Invalid workflow ID format: {workflow_id}")
        return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S") + timedelta(hours=8)

    def check_workflow_schedule_time(self, workflow_id: str, interval_minute: int = 15) -> bool:
        schedule_time = self.id_to_datetime(workflow_id)
        monitor_start = self.round_down_and_to_period_start(self.monitor_time, interval_minute)
        if monitor_start <= schedule_time:
            return True
        return False

    def load_workflow_monitor_configs(self) -> List[WorkflowMonitor]:
        if self.clickhouse_client is None:
            return []

        query = """
        SELECT workflow_type, service_id, interval_minute
        FROM monitor.workflow_monitor_configs
        ORDER BY workflow_type, service_id
        """

        rows = self.clickhouse_client.execute(query)
        monitors: List[WorkflowMonitor] = []
        for workflow_type, service_id, interval_minute in rows:
            monitors.append(
                WorkflowMonitor(
                    workflow_type=workflow_type,
                    dashboard_id=service_id,
                    interval_minute=int(interval_minute),
                )
            )
        return monitors

    def refresh_monitor_configs(self) -> None:
        try:
            monitors = self.load_workflow_monitor_configs()
        except Exception as error:
            logging.error("Failed to load workflow monitor configs from ClickHouse: %s", error)
            monitors = []

        if monitors:
            self.workflow_monitor_list = monitors
            logging.debug("Loaded %d workflow monitor configs from ClickHouse", len(monitors))
        elif not self.workflow_monitor_list:
            self.workflow_monitor_list = list(DEFAULT_WORKFLOW_MONITORS)
            logging.info("Falling back to default workflow monitor configs (%d entries)", len(self.workflow_monitor_list))

    @staticmethod
    def is_interval_due(current_time: datetime, interval_minute: int) -> bool:
        minute_aligned = current_time.replace(second=0, microsecond=0)
        if interval_minute <= 0:
            return False
        reference = datetime(1970, 1, 1)
        elapsed_minutes = int((minute_aligned - reference).total_seconds() // 60)
        return elapsed_minutes % interval_minute == 0

    async def report_status(self, workflow_type: str, service_id: str, interval_minute: int = 15):
        last_workflow = None
        workflows = self.client.list_workflows(query=f'WorkflowType="{workflow_type}"')

        workflow_in_period = [WorkflowInfo(id=wf.id,
                                           task_queue=wf.task_queue,
                                           status=wf.status.value,
                                           status_name=wf.status.name,
                                           scheduled_at=self.id_to_datetime(wf.id))
                        async for wf in workflows if self.check_workflow_schedule_time(wf.id, interval_minute)]
 
        status = 1
        message = "Execution is delayed"

        if not workflow_in_period:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.report_endpoint}/status/{service_id}",
                    json={"message": message, "status_code": status},
                    timeout=10
                )
                if response.status_code == 200:
                    return "done"
                logging.error(f"Failed to send status to {self.report_endpoint}/status/{service_id}: {response.status_code}")
            return

        last_workflow = max(workflow_in_period, key=lambda wf: wf.scheduled_at)

        if last_workflow.status_name == 'RUNNING':
            expected_previous_start = last_workflow.scheduled_at - timedelta(minutes=interval_minute)
            workflows = self.client.list_workflows(query=f'WorkflowType="{workflow_type}"')
            workflow_in_previous_period = [WorkflowInfo(id=wf.id,
                                    task_queue=wf.task_queue,
                                    status=wf.status.value,
                                    status_name=wf.status.name,
                                    scheduled_at=self.id_to_datetime(wf.id))
                async for wf in workflows if self.check_workflow_schedule_time(wf.id, interval_minute * 2)]

            previous_workflow = max(
                (wf for wf in workflow_in_previous_period if wf.scheduled_at == expected_previous_start),
                default=None,
                key=lambda wf: wf.scheduled_at
            )

            if previous_workflow:
                last_workflow = previous_workflow
                print(f"Using prior execution {last_workflow.id} for reporting")
            else:
                message = "Execution in progress"
        
        if last_workflow.status_name != 'RUNNING':
            match last_workflow.status:
                case 3 | 4 | 5 | 7:
                    status = 2
                    message = "Execution failed"
                case 2:
                    status = 0
                    message = "Execution Completed"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.report_endpoint}/status/{service_id}",
                json={"message": message, "status_code": status},
                timeout=10
            )
            if response.status_code == 200:
                return "done"
            else:
                logging.error(f"Failed to send status to {self.report_endpoint}/status/{service_id}: {response.status_code}")

    async def run_report_status(self):
        # Refresh monitor timestamp so each polling cycle uses the current wall clock
        self.monitor_time = datetime.now()
        self.refresh_monitor_configs()

        if not self.workflow_monitor_list:
            logging.info("No workflow monitors configured; skipping reporting run")
            return

        eligible_configs = [
            config for config in self.workflow_monitor_list
            if self.is_interval_due(self.monitor_time, config.interval_minute)
        ]

        if not eligible_configs:
            logging.debug("No workflow monitors due at %s", self.monitor_time.isoformat())
            return

        tasks = [
            asyncio.create_task(
                self.report_status(config.workflow_type, config.dashboard_id, config.interval_minute)
            )
            for config in eligible_configs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logging.info(f"Report results: {results}")


if __name__ == "__main__":
    async def run():
        client: Client = await Client.connect("temporal-frontend-headless.temporal.svc.cluster.local:7233", namespace="default")
        report_endpoint = 'http://localhost:14306'
        status_report = WorkflowStatusReport(client, report_endpoint)
        await status_report.run_report_status()

    asyncio.run(run())