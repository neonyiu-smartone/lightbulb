import { memo, useMemo, useRef, useCallback, createContext, useContext, useState, useEffect } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { useQueries } from '@tanstack/react-query';
import { fetchServiceStatus, fetchWorkflowScheduleSnapshot } from '@/externalDataSources';
import { type ServiceNode, type ServiceStatusSummary, type WorkflowScheduleSnapshot } from '@/model';
import { type ColDef, type GridApi, type GridReadyEvent, type ICellRendererParams, type GetRowIdParams, type RowGroupOpenedEvent } from 'ag-grid-community';

type StatusSummaryCounts = {
    ok: number;
    degraded: number;
    failed: number;
    starting: number;
    stopped: number;
    unknown: number;
    others: number;
    total: number;
};

type StatusMeta = {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
};

type ScheduleMeta = {
    isLoading: boolean;
    isError: boolean;
};

interface ServiceStatusContextValue {
    statusByService: Record<string, ServiceStatusSummary | undefined>;
    summaryByType: Record<string, StatusSummaryCounts>;
    statusStateByService: Record<string, StatusMeta>;
    scheduleByService: Record<string, WorkflowScheduleSnapshot | undefined>;
    scheduleStateByService: Record<string, ScheduleMeta>;
}

const ServiceStatusContext = createContext<ServiceStatusContextValue>({
    statusByService: {},
    summaryByType: {},
    statusStateByService: {},
    scheduleByService: {},
    scheduleStateByService: {},
});

const useServiceStatusContext = () => useContext(ServiceStatusContext);

type ServiceRow = ServiceNode & { _status_code: number | null };
type StatusCellRendererProps = ICellRendererParams<ServiceRow>;

const defaultSummaryCounts = (total: number): StatusSummaryCounts => ({
    ok: 0,
    degraded: 0,
    failed: 0,
    starting: 0,
    stopped: 0,
    unknown: total,
    others: 0,
    total,
});

const parseTimestamp = (value?: string | null): number | null => {
    if (!value) {
        return null;
    }
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
};

const formatHktDateTime = (isoString: string | null): { iso: string; label: string } | null => {
    if (!isoString) {
        return null;
    }
    const timestamp = parseTimestamp(isoString);
    if (timestamp === null) {
        return null;
    }
    const formatter = new Intl.DateTimeFormat('en-HK', {
        timeZone: 'Asia/Hong_Kong',
        dateStyle: 'medium',
        timeStyle: 'short',
    });
    return {
        iso: isoString,
        label: formatter.format(timestamp),
    };
};

const selectNextUpcomingAction = (
    snapshot: WorkflowScheduleSnapshot,
): { iso: string; timestamp: number } | null => {
    const nowMs = Date.now();
    const candidates: string[] = [];
    if (snapshot.next_action_time) {
        candidates.push(snapshot.next_action_time);
    }
    if (Array.isArray(snapshot.upcoming_action_times)) {
        candidates.push(...snapshot.upcoming_action_times);
    }
    if (!candidates.length) {
        return null;
    }
    const enriched = candidates
        .map(entry => ({ entry, timestamp: parseTimestamp(entry) }))
        .filter(item => item.timestamp !== null) as Array<{ entry: string; timestamp: number }>;
    if (!enriched.length) {
        return null;
    }
    const future = enriched.filter(item => item.timestamp >= nowMs).sort((a, b) => a.timestamp - b.timestamp);
    if (future.length) {
        return { iso: future[0].entry, timestamp: future[0].timestamp };
    }
    const pastSorted = enriched.sort((a, b) => b.timestamp - a.timestamp);
    return { iso: pastSorted[0].entry, timestamp: pastSorted[0].timestamp };
};

const StatusCellRenderer = ({ data, node }: StatusCellRendererProps) => {
    const {
        statusByService,
        summaryByType,
        statusStateByService,
        scheduleByService,
        scheduleStateByService,
    } = useServiceStatusContext();

    if (node?.group) {
        const groupKey = String(node.key ?? '');

        const fallbackCounts = (): StatusSummaryCounts => {
            const counts = defaultSummaryCounts(node.allLeafChildren?.length ?? 0);
            (node.allLeafChildren ?? []).forEach(child => {
                const service = child.data as ServiceRow | undefined;
                if (!service?.service_id) {
                    return;
                }
                const statusCode = statusByService[service.service_id]?.last_status_code ?? service._status_code ?? null;
                switch (statusCode) {
                    case 0:
                        counts.ok += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                    case 1:
                        counts.degraded += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                    case 2:
                        counts.failed += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                    case 3:
                        counts.starting += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                    case 4:
                        counts.stopped += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                    case 5:
                    case null:
                    case undefined:
                        break;
                    default:
                        counts.others += 1;
                        counts.unknown = Math.max(0, counts.unknown - 1);
                        break;
                }
            });
            return counts;
        };

        const counts = summaryByType[groupKey] ?? fallbackCounts();

        const summary = [
            { label: 'OK', count: counts.ok, color: 'bg-emerald-100 text-emerald-700' },
            { label: 'Degraded', count: counts.degraded, color: 'bg-amber-100 text-amber-700' },
            { label: 'Failed', count: counts.failed, color: 'bg-red-100 text-red-700' },
            { label: 'Starting', count: counts.starting, color: 'bg-blue-100 text-blue-700' },
            { label: 'Stopped', count: counts.stopped, color: 'bg-slate-200 text-slate-700' },
            { label: 'Unknown', count: counts.unknown, color: 'bg-slate-300 text-slate-700' },
            { label: 'Others', count: counts.others, color: 'bg-violet-100 text-violet-700' },
        ].filter(item => item.count > 0 || item.label === 'OK' || item.label === 'Failed');

        return (
            <div className="flex flex-wrap items-center gap-2">
                {summary.map(item => (
                    <div
                        key={item.label}
                        title={`${item.label}: ${item.count}`}
                        className={`inline-flex min-w-[2.5rem] items-center justify-center rounded-full px-2 py-1 text-xs font-semibold ${item.color}`}
                    >
                        {item.count}
                    </div>
                ))}
            </div>
        );
    }

    const serviceId = data?.service_id;
    if (!serviceId) {
        return <span className="text-slate-400">—</span>;
    }

    const status = statusByService[serviceId];
    const statusMeta = statusStateByService[serviceId];
    const schedule = scheduleByService[serviceId];
    const scheduleMeta = scheduleStateByService[serviceId];

    if (!status) {
        if (statusMeta?.isLoading) {
            return <span className="text-slate-400">Loading...</span>;
        }

        if (statusMeta?.isError) {
            if (data?.service_type !== 'Workflow') {
                return <span className="text-slate-400">Status unavailable</span>;
            }
            if (scheduleMeta?.isLoading) {
                return <span className="text-slate-400">Checking schedule...</span>;
            }

            if (schedule) {
                if (schedule.paused) {
                    return (
                        <div className="flex flex-col">
                            <span className="font-semibold text-slate-600">Paused</span>
                            <span className="text-xs text-slate-500">Workflow schedule is paused</span>
                        </div>
                    );
                }

                const nextRunCandidate = selectNextUpcomingAction(schedule);
                if (nextRunCandidate) {
                    const formattedNextRun = formatHktDateTime(nextRunCandidate.iso) ?? {
                        iso: nextRunCandidate.iso,
                        label: nextRunCandidate.iso,
                    };

                    return (
                        <div className="flex flex-col">
                            <span className="font-semibold text-slate-600">
                                Next run (HKT)
                                {' '}
                                <time dateTime={formattedNextRun.iso}>{formattedNextRun.label}</time>
                            </span>
                            <span className="text-xs text-slate-500">Status unavailable since last check</span>
                        </div>
                    );
                }

                return (
                    <div className="flex flex-col">
                        <span className="font-semibold text-slate-600">No recent status</span>
                        <span className="text-xs text-slate-500">No upcoming runs scheduled</span>
                    </div>
                );
            }

            if (scheduleMeta?.isError) {
                return <span className="text-slate-400">Schedule unavailable</span>;
            }

            return <span className="text-slate-400">Status unavailable</span>;
        }

        return <span className="text-slate-400">—</span>;
    }

    const statusDisplayMap: Record<number, { text: string; color: string }> = {
        0: { text: 'OK', color: 'text-emerald-600' },
        1: { text: 'DEGRADED', color: 'text-amber-600' },
        2: { text: 'FAILED', color: 'text-red-600' },
        3: { text: 'STARTING', color: 'text-blue-600' },
        4: { text: 'STOPPED', color: 'text-slate-500' },
        5: { text: 'UNKNOWN', color: 'text-slate-400' },
    };

    const statusCode = status.last_status_code ?? 5;
    const currentStatus = statusDisplayMap[statusCode] ?? statusDisplayMap[5];

    return (
        <div className="flex flex-col">
            <span className={`font-semibold ${currentStatus.color}`}>{currentStatus.text}</span>
            {status.last_message && <span className="text-xs text-slate-500">{status.last_message}</span>}
        </div>
    );
};

const ServiceTypeGroupRenderer = ({ node, value }: ICellRendererParams<ServiceRow>) => {
    if (!node) {
        return null;
    }

    if (!node.group) {
        const row = node.data as ServiceRow | undefined;
        return (
            <div className="flex flex-col">
                <span className="font-semibold text-slate-700">{value ?? 'Unnamed Service'}</span>
                <span className="text-xs text-slate-500">{row?.service_type ?? 'Unknown Type'}</span>
            </div>
        );
    }

    return (
        <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-700">
                {value ?? node.key ?? 'Unknown Type'}
            </span>
            <span className="text-xs text-slate-500">({node.allLeafChildren?.length ?? 0})</span>
        </div>
    );
};

interface ServiceListProps {
    services: ServiceNode[];
    onSelectService: (service: ServiceNode) => void;
}
const ServiceListComponent = ({ services, onSelectService }: ServiceListProps) => {
    const gridApiRef = useRef<GridApi<ServiceRow> | null>(null);
    const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
    const expandedGroupKeysRef = useRef<Set<string>>(new Set());
    const statusQueries = useQueries({
        queries: services.map((service) => ({
            queryKey: ['serviceStatus', service.service_id],
            queryFn: () => fetchServiceStatus(service.service_id),
            enabled: !!service.service_id,
            staleTime: 30 * 60 * 1000,
            gcTime: 60 * 60 * 1000,
            refetchOnWindowFocus: false,
            refetchOnReconnect: false,
            refetchOnMount: false,
            retry: 0,
        })),
    });

    const isWorkflowService = (service: ServiceNode | undefined): boolean => service?.service_type === 'Workflow';

    const scheduleQueries = useQueries({
        queries: services.map((service, index) => {
            const statusQuery = statusQueries[index];
            const shouldFetchSchedule = Boolean(service.service_id)
                && isWorkflowService(service)
                && Boolean(statusQuery?.isError);
            return {
                queryKey: ['workflowSchedule', service.service_id],
                queryFn: () => fetchWorkflowScheduleSnapshot(service.service_id),
                enabled: shouldFetchSchedule,
                staleTime: 15 * 60 * 1000,
                gcTime: 30 * 60 * 1000,
                refetchOnWindowFocus: false,
                refetchOnReconnect: false,
                refetchOnMount: false,
                retry: 0,
            };
        }),
    });

    const statusMap = useMemo(() => {
        const map: Record<string, ServiceStatusSummary | undefined> = {};
        services.forEach((service, index) => {
            map[service.service_id] = statusQueries[index]?.data;
        });
        return map;
    }, [services, statusQueries]);

    const statusStateByService = useMemo(() => {
        const map: Record<string, StatusMeta> = {};
        services.forEach((service, index) => {
            const query = statusQueries[index];
            map[service.service_id] = {
                isLoading: Boolean(query?.isLoading || query?.isFetching),
                isError: Boolean(query?.isError),
                error: query?.error ?? null,
            };
        });
        return map;
    }, [services, statusQueries]);

    const scheduleMap = useMemo(() => {
        const map: Record<string, WorkflowScheduleSnapshot | undefined> = {};
        services.forEach((service, index) => {
            map[service.service_id] = scheduleQueries[index]?.data;
        });
        return map;
    }, [services, scheduleQueries]);

    const scheduleStateByService = useMemo(() => {
        const map: Record<string, ScheduleMeta> = {};
        services.forEach((service, index) => {
            const query = scheduleQueries[index];
            map[service.service_id] = {
                isLoading: Boolean(query?.isLoading || query?.isFetching),
                isError: Boolean(query?.isError),
            };
        });
        return map;
    }, [services, scheduleQueries]);

    const statusSummaryByType = useMemo(() => {
        const summary: Record<string, StatusSummaryCounts> = {};
        services.forEach(service => {
            const type = service.service_type ?? 'Unknown';
            if (!summary[type]) {
                summary[type] = { ok: 0, degraded: 0, failed: 0, starting: 0, stopped: 0, unknown: 0, others: 0, total: 0 };
            }
            const counts = summary[type];
            const statusCode = statusMap[service.service_id]?.last_status_code ?? null;
            counts.total += 1;
            switch (statusCode) {
                case 0:
                    counts.ok += 1;
                    break;
                case 1:
                    counts.degraded += 1;
                    break;
                case 2:
                    counts.failed += 1;
                    break;
                case 3:
                    counts.starting += 1;
                    break;
                case 4:
                    counts.stopped += 1;
                    break;
                case 5:
                case null:
                case undefined:
                    counts.unknown += 1;
                    break;
                default:
                    counts.others += 1;
                    break;
            }
        });
        return summary;
    }, [services, statusMap]);

    const rowData = useMemo(() => {
        const sorted = services.slice().sort((a, b) => {
            const aType = (a.service_type ?? '').toLowerCase();
            const bType = (b.service_type ?? '').toLowerCase();
            if (aType !== bType) {
                return aType.localeCompare(bType);
            }

            const aLabel = (a.label ?? '').toLowerCase();
            const bLabel = (b.label ?? '').toLowerCase();
            if (aLabel !== bLabel) {
                return aLabel.localeCompare(bLabel);
            }

            return a.service_id.localeCompare(b.service_id);
        });

        return sorted.map(service => ({
            ...service,
            _status_code: statusMap[service.service_id]?.last_status_code ?? null,
        }));
    }, [services, statusMap]);

    const columnDefs = useMemo((): ColDef<ServiceRow>[] => [
        {
            headerName: 'Label',
            field: 'label',
            sortable: true,
            filter: true,
            flex: 2,
            showRowGroup: 'service_type',
            cellRenderer: 'agGroupCellRenderer',
            cellRendererParams: {
                suppressCount: true,
                innerRenderer: ServiceTypeGroupRenderer,
            },
        },
        {
            headerName: 'Status',
            sortable: true,
            flex: 1,
            cellRenderer: StatusCellRenderer,
            valueGetter: (params: any) => params.data?._status_code ?? null,
        },
        {
            headerName: 'Type',
            field: 'service_type',
            rowGroup: true,
            hide: true,
        },
    ], []);

    const getRowId = useCallback((params: GetRowIdParams<ServiceRow>) => {
        if (params.data?.service_id) {
            return params.data.service_id;
        }
        if (params.parentKeys?.length) {
            return `group-${params.parentKeys.join('|')}`;
        }
        return `group-level-${params.level ?? 0}`;
    }, []);

    const handleRowSelected = useCallback((event: any) => {
        if (event.node.isSelected() && !event.node.group) {
            const service = event.data as ServiceNode;
            setSelectedServiceId(service.service_id);
            onSelectService(service);
        }
    }, [onSelectService]);

    const handleRowGroupOpened = useCallback((event: RowGroupOpenedEvent<ServiceRow>) => {
        const key = String(event.node.key ?? '');
        if (!key) {
            return;
        }
        if (event.node.expanded) {
            expandedGroupKeysRef.current.add(key);
        } else {
            expandedGroupKeysRef.current.delete(key);
        }
    }, []);

    const handleGridReady = useCallback((params: GridReadyEvent<ServiceRow>) => {
        gridApiRef.current = params.api;
        params.api.sizeColumnsToFit();
    }, []);

    useEffect(() => {
        if (!gridApiRef.current) {
            return;
        }
        const expandedKeys = expandedGroupKeysRef.current;
        gridApiRef.current.forEachNode(node => {
            if (node.group) {
                const key = String(node.key ?? '');
                if (!key) {
                    return;
                }
                node.setExpanded(expandedKeys.has(key));
            }
        });
    }, [rowData]);

    useEffect(() => {
        if (!selectedServiceId || !gridApiRef.current) {
            return;
        }
        const api = gridApiRef.current;
        const node = api.getRowNode(selectedServiceId);
        if (!node) {
            return;
        }
        let parent = node.parent;
        while (parent) {
            const key = String(parent.key ?? '');
            if (key) {
                expandedGroupKeysRef.current.add(key);
            }
            parent.setExpanded(true);
            parent = parent.parent;
        }
        node.setSelected(true);
        api.ensureNodeVisible(node, 'middle');
    }, [selectedServiceId, rowData]);

    return (
        <div className="h-full w-full font-sans overflow-hidden">
            <ServiceStatusContext.Provider
                value={{
                    statusByService: statusMap,
                    summaryByType: statusSummaryByType,
                    statusStateByService,
                    scheduleByService: scheduleMap,
                    scheduleStateByService,
                }}
            >
                <AgGridReact<ServiceRow>
                    columnDefs={columnDefs}
                    rowData={rowData}
                    rowSelection="single"
                    onRowSelected={handleRowSelected}
                    onRowGroupOpened={handleRowGroupOpened}
                    onGridReady={handleGridReady}
                    groupDisplayType="custom"
                    getRowId={getRowId}
                    groupDefaultExpanded={0}
                    suppressMenuHide={true}
                    animateRows={true}
                    rowHeight={28}
                    headerHeight={32}
                    suppressHorizontalScroll={true}
                />
            </ServiceStatusContext.Provider>
        </div>
    );
};

export default memo(ServiceListComponent);
