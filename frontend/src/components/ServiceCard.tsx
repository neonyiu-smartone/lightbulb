import { memo, useEffect, useLayoutEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { Handle, useUpdateNodeInternals } from '@xyflow/react';

import { type NodeProps, Position } from "@xyflow/react";
import { BaseNode } from "@/components/BaseNode.tsx";
import { useServiceStatus, useServiceFailures } from "../externalDataSources.tsx";


const typeStyles = {
    Platform:  { border: "border-2 border-yellow-400",  color: "text-yellow-500"},
    Pipeline:  { border: "border-2 border-green-300",   color: "text-green-400"},
    Application: { border: "border-2 border-gray-400",  color: "text-gray-500"},
    Report:    { border: "border-2 border-blue-900",    color: "text-blue-900"},
    Alert:     { border: "border-2 border-purple-500",  color: "text-purple-500"},
    Database:   { border: "border border-red-200",      color: "text-red-400"},
    Table:     { border: "border-2 border-cyan-400",    color: "text-cyan-600"},
    Automation:   { border: "border border-orange-200", color: "text-orange-400"},
    default:   { border: "border border-gray-200",      color: "text-gray-400"},
};

const getTypeStyle = (type?: string) => typeStyles[type as keyof typeof typeStyles] || typeStyles.default;

const capitalizeFirst = (str: string) =>
  str.charAt(0).toUpperCase() + str.slice(1);

const ServiceCard = memo(({selected, data}: NodeProps) => {
    const { border, color } = getTypeStyle(data?.type as string);
    const extendedData = data as typeof data & {
        outageService?: string[];
        setOutageService?: Dispatch<SetStateAction<string[]>>;
        onHeightChange?: (serviceId: string, height: number) => void;
        dateRange?: { startDate: string; endDate: string };
    };
    const outageService = extendedData.outageService ?? [];
    const setOutageService = extendedData.setOutageService;
    const serviceId = typeof data?.service_id === 'string' ? data.service_id : undefined;
    const updateNodeInternals = useUpdateNodeInternals();
    const cardRef = useRef<HTMLDivElement | null>(null);
    const lastHeightRef = useRef<number | null>(null);
    const dateRange = extendedData.dateRange;
    
    // Fetch real-time status data
    const { data: statusData, isLoading, error } = useServiceStatus(
        data?.service_id as string,
        dateRange
    );

    const { data: failureData } = useServiceFailures(
        data?.service_id as string,
        dateRange
    );

    useEffect(() => {
        if (!serviceId) {
            return;
        }

        updateNodeInternals(serviceId);
    }, [serviceId, updateNodeInternals, statusData?.last_message, failureData?.length, dateRange?.startDate, dateRange?.endDate]);

    useLayoutEffect(() => {
        if (!serviceId) {
            return;
        }

        const handleMeasurement = () => {
            if (!cardRef.current) {
                return;
            }
            const nextHeight = cardRef.current.offsetHeight;
            if (lastHeightRef.current === nextHeight) {
                return;
            }
            lastHeightRef.current = nextHeight;
            if (extendedData.onHeightChange) {
                extendedData.onHeightChange(serviceId, nextHeight);
            }
        };

        handleMeasurement();
    }, [extendedData, serviceId, statusData?.last_message, failureData?.length, dateRange?.startDate, dateRange?.endDate]);

    useEffect(() => {
        if (!setOutageService || !serviceId) {
            return
        }

        if (statusData && statusData?.last_status_code != null) {
            console.log(statusData?.last_status_code, serviceId)

            if (statusData?.last_status_code === 0) {
                if (outageService.includes(serviceId)) {
                    setOutageService(prev => prev.filter(i => i !== serviceId))
                }
            } else if ([1, 2, 4].includes(statusData?.last_status_code) && !outageService.includes(serviceId)) {
                setOutageService(prev => prev.concat(serviceId))
            }
        }
    }, [statusData, outageService, setOutageService, serviceId])

    // Map status code to readable status and color
    const getStatusInfo = (statusCode?: number) => {
        switch (statusCode) {
            case 0: return { status: 'ok', color: 'bg-emerald-500' };
            case 1: return { status: 'degraded', color: 'bg-amber-500' };
            case 2: return { status: 'failed', color: 'bg-red-500' };
            case 3: return { status: 'starting', color: 'bg-blue-500' };
            case 4: return { status: 'stopped', color: 'bg-slate-500' };
            case 5: return { status: 'unknown', color: 'bg-slate-400' };
            default: return { status: 'unknown', color: 'bg-slate-400' };
        }
    };

    const statusInfo = getStatusInfo(statusData?.last_status_code);
    const formatDateTime = (dateString?: string) => {
        if (!dateString) return 'N/A';
        return new Date(dateString).toLocaleString();
    };

    return (
    <BaseNode ref={cardRef} selected={selected} className={`inline-block ${border}`}>
            <div className={`absolute left-0 -mt-8 -ml-3 z-10`}>
                <span className={`bg-gray-100 px-2 py-0.5 text-xs font-semibold ${color} rounded-lg ${border} whitespace-nowrap origin-center inline-block`}>
                    {capitalizeFirst((data?.type as string) ?? "")}
                </span>
            </div>
            <div>
                <div className="flex justify-between items-center">
                    <div>{(data?.label as string) ?? ""}</div>
                    <div className="flex items-center">
                        {isLoading ? (
                            <div className="animate-spin w-3 h-3 border-2 border-gray-300 border-t-blue-500 rounded-full ml-1"></div>
                        ) : error ? (
                            <span className="inline-block w-3 h-3 rounded-full ml-1 bg-gray-500" title="Error loading status"></span>
                        ) : (
                            <span
                                className={`inline-block w-3 h-3 rounded-full ml-1 ${statusInfo.color}`}
                                title={`Status: ${statusInfo.status} (Code: ${statusData?.last_status_code})`}
                            ></span>
                        )}
                        <span className="ml-1 text-sm">{statusInfo.status}</span>
                    </div>
                </div>
                
                {/* Display ServiceStatusSummary data */}
                {statusData && (
                    <div className="text-xs mt-2 space-y-1">
                        <div>Last Check: {formatDateTime(statusData.last_check)}</div>
                        {statusData.last_message && (
                            <div className="text-gray-600 truncate" title={statusData.last_message}>
                                Message: {statusData.last_message}
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-x-2">
                            <div>Checks: {statusData.check_count}</div>
                            <div>Failed: {statusData.failed_count}</div>
                        </div>
                    </div>
                )}
                {failureData && failureData.length > 0 && (
                    <div className="mt-3">
                        <div className="font-semibold text-xs text-gray-700">Recent failures</div>
                        <ul className="mt-1 space-y-1">
                            {failureData.map((failure, index) => (
                                <li key={`${failure.time}-${index}`} className="flex flex-col rounded bg-red-50 px-2 py-1">
                                    <span className="text-[10px] uppercase tracking-wide text-red-600">
                                        {formatDateTime(failure.time)}
                                    </span>
                                    <span className="text-[11px] text-red-700 truncate" title={failure.message}>
                                        {failure.message}
                                    </span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Legacy metric display - keep for backward compatibility */}
                {(data as any)?.metric && (
                    <table className="text-xs mt-1">
                        <tbody>
                            {Object.entries((data as any).metric).map(([key, value]) => (
                                <tr key={key}>
                                    <td className="px-1">{key}</td>
                                    <td className="px-1">{String(value)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                <Handle type="source" position={Position.Right}/>
                <Handle type="target" position={Position.Left}/>
            </div>
        </BaseNode>
    );
});

export default ServiceCard;