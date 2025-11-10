import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
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
    is_paused: bool = False
    start_offset_minute: int = 0
    task_queue: Optional[str] = None


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
    def extract_interval_metadata(schedule_entry: Any) -> tuple[Optional[int], Optional[int]]:
        """Return interval minutes and start offset from Temporal schedule."""
        interval_minutes = None
        start_offset = None

        schedule = getattr(schedule_entry, 'schedule', None)
        if schedule is not None:
            intervals = getattr(schedule, 'intervals', None)
            if not intervals:
                spec = getattr(schedule, 'spec', None)
                intervals = getattr(spec, 'intervals', None) if spec else None

            if intervals:
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

                if best_seconds is not None:
                    interval_minutes = max(int(best_seconds // 60) or 1, 1)

        info = getattr(schedule_entry, 'info', None)

        candidate_times: list[datetime] = []
        if info is not None:
            primary_iterable = getattr(info, 'next_action_times', None)
            if primary_iterable:
                candidate_times.extend([
                    dt for dt in primary_iterable
                    if isinstance(dt, datetime)
                ])

            future_iterable = getattr(info, 'future_action_times', None)
            if future_iterable:
                candidate_times.extend([
                    dt for dt in future_iterable
                    if isinstance(dt, datetime)
                ])

        if not candidate_times and info is not None:
            recent_actions = getattr(info, 'recent_actions', None)
            if recent_actions:
                for action in recent_actions[:3]:
                    scheduled_time = getattr(action, 'scheduled_at', None)
                    if not isinstance(scheduled_time, datetime):
                        scheduled_time = getattr(action, 'scheduled_time', None)
                    if isinstance(scheduled_time, datetime):
                        candidate_times.append(scheduled_time)

        candidate_times = sorted({dt for dt in candidate_times if isinstance(dt, datetime)})

        if len(candidate_times) >= 2:
            deltas = [
                (b - a).total_seconds()
                for a, b in zip(candidate_times, candidate_times[1:])
                if (b - a).total_seconds() > 0
            ]
            if deltas:
                seconds = min(deltas)
                interval_minutes = interval_minutes or max(int(seconds // 60) or 1, 1)

        first_total_minutes: Optional[int] = None
        if candidate_times:
            first = candidate_times[0]
            if first.tzinfo is not None:
                first_utc = first.astimezone(timezone.utc)
            else:
                first_utc = first.replace(tzinfo=timezone.utc)

            reference = datetime(1970, 1, 1, tzinfo=timezone.utc)
            first_total_minutes = int((first_utc - reference).total_seconds() // 60)

            if interval_minutes is not None and interval_minutes > 0:
                start_offset = first_total_minutes % interval_minutes

        if interval_minutes is None:
            inferred = WorkflowStatusReport._infer_interval_from_history(candidate_times)
            if inferred:
                interval_minutes = inferred

        if interval_minutes is not None and interval_minutes > 0:
            if first_total_minutes is not None:
                start_offset = first_total_minutes % interval_minutes
            elif start_offset is not None:
                start_offset %= interval_minutes

        return interval_minutes, start_offset

    @staticmethod
    def _infer_interval_from_history(candidate_times: List[datetime]) -> Optional[int]:
        """Approximate interval using candidate execution timestamps."""
        candidate_times = sorted({dt for dt in candidate_times if isinstance(dt, datetime)})
        if len(candidate_times) < 2:
            return None

        deltas = [
            (b - a).total_seconds()
            for a, b in zip(candidate_times, candidate_times[1:])
            if (b - a).total_seconds() > 0
        ]

        if not deltas:
            return None

        best_seconds = min(deltas)
        inferred_minutes = max(int(best_seconds // 60) or 1, 1)
        return inferred_minutes

    @staticmethod
    def _collect_datetime_values(values: Any) -> list[datetime]:
        """Normalize iterable datetime values to UTC-aware datetimes."""
        collected: list[datetime] = []
        if not values:
            return collected

        try:
            iterator = list(values)
        except TypeError:
            return collected

        for dt_value in iterator:
            if not isinstance(dt_value, datetime):
                continue
            if dt_value.tzinfo is None:
                collected.append(dt_value.replace(tzinfo=timezone.utc))
            else:
                collected.append(dt_value.astimezone(timezone.utc))
        return collected

    @staticmethod
    def _is_schedule_paused(
        info: Any,
        now_utc: Optional[datetime] = None,
        precomputed_times: Optional[List[datetime]] = None,
    ) -> bool:
        """Determine whether a Temporal schedule should be treated as paused."""
        if info is None:
            return False

        explicit_paused = getattr(info, 'paused', None)
        paused_by = getattr(info, 'paused_by', None)
        status_value = getattr(info, 'status', None)

        status_name = None
        if hasattr(status_value, 'name'):
            status_name = getattr(status_value, 'name', None)
        elif isinstance(status_value, str):
            status_name = status_value

        paused = bool(explicit_paused) or bool(paused_by)

        if not paused and status_name is not None:
            paused = status_name.upper() == 'SCHEDULE_STATUS_PAUSED'

        if not paused and isinstance(status_value, int):
            paused = status_value == 2

        if paused:
            return True

        now = now_utc or datetime.now(timezone.utc)
        tolerance = timedelta(minutes=5)

        if precomputed_times is not None:
            upcoming_candidates = [
                dt_value.replace(tzinfo=timezone.utc)
                if isinstance(dt_value, datetime) and dt_value.tzinfo is None
                else dt_value.astimezone(timezone.utc)
                for dt_value in precomputed_times
                if isinstance(dt_value, datetime)
            ]
        else:
            upcoming_candidates: list[datetime] = []
            upcoming_candidates.extend(WorkflowStatusReport._collect_datetime_values(getattr(info, 'next_action_times', None)))
            upcoming_candidates.extend(WorkflowStatusReport._collect_datetime_values(getattr(info, 'future_action_times', None)))

            next_action = getattr(info, 'next_action_time', None)
            if isinstance(next_action, datetime):
                if next_action.tzinfo is None:
                    upcoming_candidates.append(next_action.replace(tzinfo=timezone.utc))
                else:
                    upcoming_candidates.append(next_action.astimezone(timezone.utc))

        if not upcoming_candidates:
            return False

        threshold = now - tolerance
        if all(candidate < threshold for candidate in upcoming_candidates):
            return True

        return False

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

            if not type_candidates:
                args = getattr(start_workflow, 'arguments', None) or getattr(start_workflow, 'args', None)
                if isinstance(args, (list, tuple)):
                    for value in args:
                        if isinstance(value, dict):
                            potential = value.get('workflowType') or value.get('workflow_type')
                            if isinstance(potential, str):
                                type_candidates.append(potential)
                                break

        if not type_candidates and hasattr(schedule_entry, 'id'):
            id_value = getattr(schedule_entry, 'id', '')
            if isinstance(id_value, str):
                type_candidates.append(id_value)

        for candidate in type_candidates:
            workflow_type = candidate.strip()
            if workflow_type:
                return workflow_type

        return None

    @staticmethod
    def extract_task_queue(schedule_entry: Any) -> Optional[str]:
        """Extract task queue from schedule entry when available."""
        schedule = getattr(schedule_entry, 'schedule', None)
        if schedule is None:
            return None

        action = getattr(schedule, 'action', None)
        start_workflow = getattr(action, 'start_workflow', None) if action else None
        if start_workflow is None:
            return None

        task_queue = getattr(start_workflow, 'task_queue', None)
        if isinstance(task_queue, str) and task_queue.strip():
            return task_queue.strip()

        if hasattr(task_queue, 'name') and isinstance(getattr(task_queue, 'name'), str):
            return getattr(task_queue, 'name').strip()

        if isinstance(task_queue, dict):
            queue_name = task_queue.get('name') or task_queue.get('task_queue')
            if isinstance(queue_name, str) and queue_name.strip():
                return queue_name.strip()

        return None

    async def log_schedule_snapshot(
        self,
        schedule_id: Optional[str],
        schedule_entry: Any = None,
        interval_minute: Optional[int] = None,
        start_offset_minute: Optional[int] = None,
    ) -> None:
        """Log key schedule fields from Temporal for observability."""
        if not schedule_id:
            return

        info = getattr(schedule_entry, 'info', None) if schedule_entry is not None else None
        description = None

        if info is None:
            try:
                handle = self.client.get_schedule_handle(schedule_id)
                description = await handle.describe()
                info = getattr(description, 'info', None)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Unable to describe schedule %s: %s", schedule_id, exc)
                return

        def compute_schedule_times(target_info: Any) -> tuple[list[datetime], list[datetime], Optional[datetime]]:
            if target_info is None:
                return [], [], None
            next_list = self._collect_datetime_values(getattr(target_info, 'next_action_times', None))
            future_list = self._collect_datetime_values(getattr(target_info, 'future_action_times', None))
            next_action_value = getattr(target_info, 'next_action_time', None)
            if isinstance(next_action_value, datetime):
                if next_action_value.tzinfo is None:
                    next_action_utc = next_action_value.replace(tzinfo=timezone.utc)
                else:
                    next_action_utc = next_action_value.astimezone(timezone.utc)
            else:
                next_action_utc = None
            return next_list, future_list, next_action_utc

        next_datetimes, future_datetimes, next_action_dt = compute_schedule_times(info)

        if not future_datetimes and description is None and info is not None:
            try:
                handle = self.client.get_schedule_handle(schedule_id)
                description = await handle.describe()
                info = getattr(description, 'info', None)
                next_datetimes, future_datetimes, next_action_dt = compute_schedule_times(info)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Unable to refresh schedule %s for future times: %s", schedule_id, exc)

        last_completed = None
        if info is not None:
            completed_time = getattr(info, 'last_completed_action_time', None)
            if isinstance(completed_time, datetime):
                if completed_time.tzinfo is None:
                    last_completed = completed_time.replace(tzinfo=timezone.utc).isoformat()
                else:
                    last_completed = completed_time.astimezone(timezone.utc).isoformat()

        recent_info = None
        if info is not None:
            try:
                recent_actions = getattr(info, 'recent_actions', None)
                if recent_actions:
                    recent_info = [
                        {
                            'scheduled_at': getattr(action, 'scheduled_at', None).isoformat()
                            if isinstance(getattr(action, 'scheduled_at', None), datetime) else None,
                            'started_at': getattr(action, 'started_at', None).isoformat()
                            if isinstance(getattr(action, 'started_at', None), datetime) else None,
                            'action_type': type(getattr(action, 'action', None)).__name__ if getattr(action, 'action', None) else None,
                        }
                        for action in recent_actions[:3]
                    ]
            except TypeError:
                recent_info = None

        recent_runs = recent_info or []
        detected_interval, detected_offset = (None, None)
        if schedule_entry is not None:
            detected_interval, detected_offset = self.extract_interval_metadata(schedule_entry)

        interval_value = interval_minute if interval_minute is not None else detected_interval
        offset_value = start_offset_minute if start_offset_minute is not None else detected_offset

        combined_upcoming: list[datetime] = []
        seen_upcoming: set[str] = set()
        for dt_value in next_datetimes + future_datetimes:
            key = dt_value.isoformat()
            if key in seen_upcoming:
                continue
            seen_upcoming.add(key)
            combined_upcoming.append(dt_value)

        if next_action_dt is not None:
            key = next_action_dt.isoformat()
            if key not in seen_upcoming:
                combined_upcoming.append(next_action_dt)

        paused = self._is_schedule_paused(info, precomputed_times=combined_upcoming)

        def datetimes_to_strings(values: list[datetime], limit: int = 3) -> list[str]:
            return [dt.isoformat() for dt in values[:limit]]

        next_times = datetimes_to_strings(next_datetimes)
        future_times = datetimes_to_strings(future_datetimes)

        upcoming_preview = datetimes_to_strings(combined_upcoming)
        next_action_iso = next_action_dt.isoformat() if next_action_dt is not None else None

        recent_preview = [
            f"{entry.get('scheduled_at')}/{entry.get('started_at')}"
            for entry in recent_runs[:3]
        ] if recent_runs else []

        logger.info(
            "Schedule %s paused=%s interval=%s offset=%s next=%s upcoming=%s last_completed=%s recent=%s",
            schedule_id,
            paused,
            interval_value,
            offset_value,
            next_action_iso,
            upcoming_preview,
            last_completed,
            recent_preview,
        )

    async def sync_temporal_workflow_services(self) -> List[WorkflowMonitor]:
        """Sync Temporal schedules into ClickHouse services and build monitor list."""
        try:
            schedules_iterator = await self.client.list_schedules()
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Failed to list Temporal schedules: %s", exc)
            return []

        monitors: List[WorkflowMonitor] = []
        now_utc = datetime.now(timezone.utc)
        async for entry in schedules_iterator:
            schedule_id_raw = getattr(entry, 'id', None)
            schedule_id = schedule_id_raw if isinstance(schedule_id_raw, str) and schedule_id_raw else None

            info = getattr(entry, 'info', None)
            paused = self._is_schedule_paused(info, now_utc)

            workflow_type = self.extract_workflow_type(entry)
            task_queue = self.extract_task_queue(entry)
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

            monitor_schedule_id = schedule_id or workflow_type
            interval_meta, start_offset = self.extract_interval_metadata(entry)
            interval_minute = interval_meta or 15
            offset_minute = start_offset if start_offset is not None else 0
            if start_offset is not None and interval_meta:
                offset_minute = start_offset % interval_minute
            elif interval_meta is not None and interval_meta > 0:
                offset_minute %= interval_minute
            else:
                offset_minute %= interval_minute or 1

            if interval_meta is None:
                logger.debug(
                    "Using default interval %d minutes for schedule %s (workflow type %s)",
                    interval_minute,
                    monitor_schedule_id,
                    workflow_type,
                )
            else:
                logger.debug(
                    "Schedule %s (workflow type %s) interval set to %d minutes (offset %d)",
                    monitor_schedule_id,
                    workflow_type,
                    interval_minute,
                    offset_minute,
                )

            service_id = workflow_type

            self.ensure_workflow_service(service_id)
            monitors.append(
                WorkflowMonitor(
                    workflow_type=workflow_type,
                    dashboard_id=service_id,
                    schedule_id=monitor_schedule_id,
                    interval_minute=interval_minute,
                    is_paused=paused,
                    start_offset_minute=offset_minute,
                    task_queue=task_queue,
                )
            )

            await self.log_schedule_snapshot(monitor_schedule_id, entry)
            logger.debug(
                "Prepared monitor for schedule %s (workflow type %s) with interval %d minutes offset %d",
                monitor_schedule_id,
                workflow_type,
                interval_minute,
                offset_minute,
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

    def compute_monitor_window(self, interval_minute: int, start_offset_minute: int = 0) -> tuple[datetime, datetime, timedelta]:
        """Return the monitoring window start, due time, and applied grace."""
        interval_minutes = max(interval_minute, 1)
        offset = start_offset_minute % interval_minutes
        minute_aligned = self.monitor_time.replace(second=0, microsecond=0)
        reference = datetime(1970, 1, 1)

        grace = timedelta(hours=2) if interval_minutes > 1440 else timedelta()
        adjusted_time = minute_aligned - grace
        if adjusted_time < reference:
            adjusted_time = reference

        elapsed_minutes = int((adjusted_time - reference).total_seconds() // 60)
        offset_remainder = (elapsed_minutes - offset) % interval_minutes
        due_minutes = elapsed_minutes - offset_remainder
        if due_minutes < 0:
            due_minutes = 0

        due_time = reference + timedelta(minutes=due_minutes)
        window_start = due_time - timedelta(minutes=interval_minutes)
        if window_start < reference:
            window_start = reference
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

        queue_query_label = 'task_queue'
        task_queue_filter = None
        if hasattr(self, 'workflow_monitor_list') and self.workflow_monitor_list:
            for monitor in self.workflow_monitor_list:
                if monitor.schedule_id == schedule_id or monitor.workflow_type == workflow_type:
                    if monitor.task_queue:
                        task_queue_filter = monitor.task_queue.replace('"', '\"')
                    break

        if task_queue_filter:
            queries.append((
                queue_query_label,
                f'TaskQueue="{task_queue_filter}"',
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

                info_payload = {
                    'workflow_id': wf.id,
                    'task_queue': getattr(wf, 'task_queue', None),
                    'status': getattr(getattr(wf, 'status', None), 'name', None),
                    'scheduled_at': scheduled_at.isoformat(),
                    'window_start': window_start.isoformat(),
                    'window_end': window_end.isoformat(),
                    'filter': label,
                }

                if not self.check_workflow_schedule_time(scheduled_at, window_start, window_end):
                    logger.debug(
                        "Workflow outside monitoring window: %s",
                        info_payload,
                    )
                    continue

                if wf.id in collected:
                    logger.debug(
                        "Workflow already collected for monitoring window: %s",
                        info_payload,
                    )
                    continue

                collected[wf.id] = WorkflowInfo(
                    id=wf.id,
                    task_queue=wf.task_queue,
                    status=wf.status.value,
                    status_name=wf.status.name,
                    scheduled_at=scheduled_at,
                )
                logger.debug(
                    "Collected workflow execution for monitoring window: %s",
                    info_payload,
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
    def is_interval_due(current_time: datetime, interval_minute: int, start_offset_minute: int = 0) -> bool:
        minute_aligned = current_time.replace(second=0, microsecond=0)
        if interval_minute <= 0:
            return False
        reference = datetime(1970, 1, 1)
        elapsed_minutes = int((minute_aligned - reference).total_seconds() // 60)
        if elapsed_minutes < 0:
            return False

        normalized_interval = max(interval_minute, 1)
        offset = start_offset_minute % normalized_interval
        adjusted_minutes = elapsed_minutes - offset

        if normalized_interval > 1440:
            adjusted_minutes -= 120

        if adjusted_minutes < 0:
            return False

        return adjusted_minutes % normalized_interval == 0

    async def report_status(
        self,
        workflow_type: str,
        service_id: str,
        schedule_id: Optional[str],
        interval_minute: int = 15,
        is_paused: bool = False,
        start_offset_minute: int = 0,
    ):
        if not self.report_endpoint:
            logger.warning("Report endpoint not configured; skipping status for %s", service_id)
            return "skipped_no_endpoint"

        await self.log_schedule_snapshot(
            schedule_id,
            interval_minute=interval_minute,
            start_offset_minute=start_offset_minute,
        )

        window_start, due_time, grace = self.compute_monitor_window(interval_minute, start_offset_minute)
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
            "Evaluating workflow %s (service %s, schedule %s) interval=%d offset=%d window=(%s -> %s) paused=%s",
            workflow_type,
            service_id,
            schedule_id or workflow_type,
            interval_minute,
            start_offset_minute,
            window_start.isoformat(),
            due_time.isoformat(),
            is_paused,
        )

        if is_paused and not workflow_in_period:
            logger.info(
                "Skipping workflow %s (schedule %s) because schedule is paused and no runs found in window",
                workflow_type,
                schedule_id or workflow_type,
            )
            return "skipped_paused"

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
            if self.is_interval_due(
                self.monitor_time,
                config.interval_minute,
                config.start_offset_minute,
            )
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
                    config.is_paused,
                    config.start_offset_minute,
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