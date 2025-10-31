import { useCallback, useEffect, useState, useRef, useMemo } from 'react';
import { EventSourcePolyfill } from 'event-source-polyfill';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { type Node, type Edge } from '@xyflow/react';
import { API_ROOT } from "@/constants.tsx";
import { useFlowChart } from "@/externalDataSources.tsx";
import { type Notification, type ServiceNode as ServiceNodeType, type ServiceRelation as ServiceRelationType } from '@/model.tsx';
import ServiceList from './components/ServiceList';
import DetailedFlowView from './components/DetailedFlowView';

const formatDateInput = (date: Date): string => date.toISOString().slice(0, 10);

const addDays = (base: Date, days: number): Date => {
    const next = new Date(base);
    next.setDate(base.getDate() + days);
    return next;
};

// Function to get all services that depend on the target service (downstream)
const get_downstream_dependents = (target_service_id: string, nodes: Array<Node>, edges: Array<Edge>): Array<Node> => {
    const dependents = new Set<string>();
    const visited = new Set<string>();

    const findDownstream = (serviceId: string) => {
        if (visited.has(serviceId)) {
            return;
        }
        visited.add(serviceId);

        const dependentEdges = edges.filter(edge => edge.source === serviceId);
        dependentEdges.forEach(edge => {
            const dependentId = edge.target;
            dependents.add(dependentId);
            findDownstream(dependentId);
        });
    };

    findDownstream(target_service_id);

    return nodes.filter(node => dependents.has(node.id));
};

type WorkflowMonitorConfig = {
    workflow_type: string;
    service_id: string;
    interval_minute: number;
};

const WORKFLOW_MONITOR_ELIGIBLE_TYPES = ['Alert', 'Automation', 'Pipeline'];

type FlowChartCache = {
    serviceNodes: ServiceNodeType[];
    serviceRelations: ServiceRelationType[];
};

type RelationResponse = {
    relation_id: string;
    source_service_id: string;
    target_service_id: string;
    relation_type: string;
    enabled: boolean;
    created_at: string;
};




export default function App() {
    const { data: flowChart } = useFlowChart({ queryKey: ['flowChart'] });
    const [outageService, setOutageService] = useState<string[]>([]);
    const [selectedNode, setSelectedNode] = useState<Node | null>(null);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [newServiceType, setNewServiceType] = useState('');
    const [newServiceLabel, setNewServiceLabel] = useState('');
    const [newServiceId, setNewServiceId] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [formError, setFormError] = useState<string | null>(null);

    // Watcher dialog state
    const [isWatcherDialogOpen, setIsWatcherDialogOpen] = useState(false);
    const [newWatcherEmail, setNewWatcherEmail] = useState('');
    const [isWatcherSubmitting, setIsWatcherSubmitting] = useState(false);
    const [watcherFormError, setWatcherFormError] = useState<string | null>(null);
    const [existingWatchers, setExistingWatchers] = useState<Array<{service_id: string, email: string, created_at: string}>>([]);
    const [isLoadingWatchers, setIsLoadingWatchers] = useState(false);
    const [removingWatcherEmail, setRemovingWatcherEmail] = useState<string | null>(null);
    const [removeConfirmationInput, setRemoveConfirmationInput] = useState('');
    const [isRemovingWatcher, setIsRemovingWatcher] = useState(false);

    // Dependency dialog state
    const [isDependencyDialogOpen, setIsDependencyDialogOpen] = useState(false);
    const [newDependencyServiceId, setNewDependencyServiceId] = useState('');
    const [isDependencySubmitting, setIsDependencySubmitting] = useState(false);
    const [dependencyFormError, setDependencyFormError] = useState<string | null>(null);
    const [existingDependencies, setExistingDependencies] = useState<Array<{relation_id: string, source_service_id: string, target_service_id: string, source_label: string}>>([]);
    const [isLoadingDependencies, setIsLoadingDependencies] = useState(false);
    const [removingDependencyId, setRemovingDependencyId] = useState<string | null>(null);
    const [dependencyRemoveConfirmationInput, setDependencyRemoveConfirmationInput] = useState('');
    const [isRemovingDependency, setIsRemovingDependency] = useState(false);

    // Delete service dialog state
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
    const [deleteConfirmationInput, setDeleteConfirmationInput] = useState('');
    const [isDeletingService, setIsDeletingService] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);
    const [startDate, setStartDate] = useState<string>(() => formatDateInput(new Date()));
    const [endDate, setEndDate] = useState<string>(() => formatDateInput(addDays(new Date(), 1)));

    // Workflow monitor dialog state
    const [isWorkflowMonitorDialogOpen, setIsWorkflowMonitorDialogOpen] = useState(false);
    const [workflowTypeInput, setWorkflowTypeInput] = useState('');
    const [workflowIntervalInput, setWorkflowIntervalInput] = useState(15);
    const [workflowFormError, setWorkflowFormError] = useState<string | null>(null);
    const [isWorkflowSubmitting, setIsWorkflowSubmitting] = useState(false);
    const [isWorkflowMonitorRemoving, setIsWorkflowMonitorRemoving] = useState(false);
    const [workflowRemoveConfirmation, setWorkflowRemoveConfirmation] = useState('');
    const [showWorkflowRemoveConfirmation, setShowWorkflowRemoveConfirmation] = useState(false);

    const sseRef = useRef<EventSource | undefined>(undefined);
    const queryClient = useQueryClient();
    const appendRelationToFlowChartCache = useCallback((relation: { relation_id: string; source_service_id: string; target_service_id: string }) => {
        queryClient.setQueryData<FlowChartCache | undefined>(['flowChart'], (previous) => {
            if (!previous) {
                return previous;
            }

            if (previous.serviceRelations.some(existing => existing.relation_id === relation.relation_id)) {
                return previous;
            }

            const nextRelation: ServiceRelationType = {
                relation_id: relation.relation_id,
                source: relation.source_service_id,
                target: relation.target_service_id,
            };

            return {
                ...previous,
                serviceRelations: [...previous.serviceRelations, nextRelation],
            };
        });
    }, [queryClient]);

    const removeRelationFromFlowChartCache = useCallback((relationId: string) => {
        queryClient.setQueryData<FlowChartCache | undefined>(['flowChart'], (previous) => {
            if (!previous) {
                return previous;
            }

            const nextRelations = previous.serviceRelations.filter(relation => relation.relation_id !== relationId);
            if (nextRelations.length === previous.serviceRelations.length) {
                return previous;
            }

            return {
                ...previous,
                serviceRelations: nextRelations,
            };
        });
    }, [queryClient]);
    const selectedServiceId = selectedNode?.id ?? '';
    const selectedServiceType = useMemo(() => (selectedNode?.data as any)?.type ?? '', [selectedNode]);
    const isWorkflowMonitorEligible = useMemo(
        () => WORKFLOW_MONITOR_ELIGIBLE_TYPES.includes(selectedServiceType),
        [selectedServiceType]
    );

    const {
        data: workflowMonitorConfig,
        error: workflowMonitorError,
        isFetching: isWorkflowMonitorFetching,
        refetch: refetchWorkflowMonitor,
    } = useQuery<WorkflowMonitorConfig | null>({
        queryKey: ['workflowMonitor', selectedServiceId],
        queryFn: async () => {
            if (!selectedServiceId) {
                return null;
            }
            const response = await axios.get<Array<WorkflowMonitorConfig>>(`${API_ROOT}/api/admin/workflow-monitors`);
            return response.data.find(monitor => monitor.service_id === selectedServiceId) ?? null;
        },
        enabled: Boolean(selectedServiceId && isWorkflowMonitorEligible),
        staleTime: 30000,
    });
    const workflowMonitorExists = Boolean(workflowMonitorConfig);
    const workflowMonitorErrorMessage = useMemo(() => {
        if (!workflowMonitorError) {
            return null;
        }
        return workflowMonitorError instanceof Error
            ? workflowMonitorError.message
            : 'Failed to load workflow monitor configuration.';
    }, [workflowMonitorError]);

    useEffect(() => {
        setWorkflowFormError(null);
        setWorkflowTypeInput('');
        setWorkflowIntervalInput(15);
    }, [selectedServiceId]);

    useEffect(() => {
        if (!isWorkflowMonitorEligible && isWorkflowMonitorDialogOpen) {
            setIsWorkflowMonitorDialogOpen(false);
        }
    }, [isWorkflowMonitorEligible, isWorkflowMonitorDialogOpen]);

    useEffect(() => {
        if (!isWorkflowMonitorDialogOpen) {
            return;
        }
        if (workflowMonitorConfig) {
            setWorkflowTypeInput(workflowMonitorConfig.workflow_type);
            setWorkflowIntervalInput(workflowMonitorConfig.interval_minute);
        } else {
            setWorkflowTypeInput('');
            setWorkflowIntervalInput(15);
        }
    }, [isWorkflowMonitorDialogOpen, workflowMonitorConfig]);

    const openWorkflowMonitorDialog = useCallback(() => {
        setWorkflowFormError(null);
        setIsWorkflowMonitorDialogOpen(true);
        if (isWorkflowMonitorEligible) {
            void refetchWorkflowMonitor();
        }
    }, [isWorkflowMonitorEligible, refetchWorkflowMonitor]);

    const closeWorkflowMonitorDialog = useCallback(() => {
        setIsWorkflowMonitorDialogOpen(false);
        setWorkflowFormError(null);
        setWorkflowRemoveConfirmation('');
        setShowWorkflowRemoveConfirmation(false);
    }, []);

    const handleSubmitWorkflowMonitor = useCallback(async () => {
        if (!selectedServiceId) {
            setWorkflowFormError('No service selected.');
            return;
        }

        const sanitizedWorkflowType = workflowTypeInput.trim();
        if (!sanitizedWorkflowType) {
            setWorkflowFormError('Workflow type is required.');
            return;
        }

        if (workflowMonitorExists) {
            setWorkflowFormError('This service already has a workflow monitor configured.');
            return;
        }

        setIsWorkflowSubmitting(true);
        setWorkflowFormError(null);
        try {
            await axios.post(`${API_ROOT}/api/admin/workflow-monitors`, {
                workflow_type: sanitizedWorkflowType,
                service_id: selectedServiceId,
                interval_minute: workflowIntervalInput,
            });
            await refetchWorkflowMonitor();
            closeWorkflowMonitorDialog();
        } catch (error: any) {
            if (axios.isAxiosError(error)) {
                const detail = error.response?.data?.detail;
                setWorkflowFormError(typeof detail === 'string' ? detail : 'Failed to create workflow monitor.');
            } else {
                setWorkflowFormError('Failed to create workflow monitor.');
            }
        } finally {
            setIsWorkflowSubmitting(false);
        }
    }, [selectedServiceId, workflowTypeInput, workflowMonitorExists, workflowIntervalInput, refetchWorkflowMonitor, closeWorkflowMonitorDialog]);

    const handleRemoveWorkflowMonitor = useCallback(async () => {
        if (!workflowMonitorConfig) {
            return;
        }
        if (workflowRemoveConfirmation.trim().toLowerCase() !== 'remove') {
            setWorkflowFormError('Type "remove" to confirm deletion.');
            return;
        }
        setIsWorkflowMonitorRemoving(true);
        setWorkflowFormError(null);
        try {
            await axios.delete(`${API_ROOT}/api/admin/workflow-monitors/${encodeURIComponent(workflowMonitorConfig.workflow_type)}/${encodeURIComponent(workflowMonitorConfig.service_id)}`);
            setWorkflowRemoveConfirmation('');
            setShowWorkflowRemoveConfirmation(false);
            await refetchWorkflowMonitor();
        } catch (error: any) {
            if (axios.isAxiosError(error)) {
                const detail = error.response?.data?.detail;
                setWorkflowFormError(typeof detail === 'string' ? detail : 'Failed to remove workflow monitor.');
            } else {
                setWorkflowFormError('Failed to remove workflow monitor.');
            }
        } finally {
            setIsWorkflowMonitorRemoving(false);
        }
    }, [workflowMonitorConfig, workflowRemoveConfirmation, refetchWorkflowMonitor]);

    const handleSelectService = useCallback((service: ServiceNodeType) => {
        // Create a synthetic Node object for the selected service
        const node: Node = {
            id: service.service_id,
            data: {
                service_id: service.service_id,
                label: service.label,
                type: service.service_type,
            },
            position: { x: 0, y: 0 }, // Position is not relevant here
        };
        setSelectedNode(node);
    }, []);

    const serviceTypeOptions = useMemo(() => {
        if (!flowChart?.serviceNodes?.length) {
            return [];
        }
        const types = new Set<string>();
        flowChart.serviceNodes.forEach(node => {
            if (node.service_type) {
                types.add(node.service_type);
            }
        });
        return Array.from(types).sort();
    }, [flowChart?.serviceNodes]);

    const computeNextServiceId = useCallback((serviceType: string) => {
        if (!serviceType || !flowChart?.serviceNodes) {
            return '';
        }
        const prefix = `${serviceType}-`;
        let maxNumber = 0;
        flowChart.serviceNodes.forEach(node => {
            if (node.service_type === serviceType && node.service_id.startsWith(prefix)) {
                const suffix = node.service_id.slice(prefix.length);
                const parsed = Number.parseInt(suffix, 10);
                if (!Number.isNaN(parsed)) {
                    maxNumber = Math.max(maxNumber, parsed);
                }
            }
        });
        return `${prefix}${maxNumber + 1}`;
    }, [flowChart?.serviceNodes]);

    useEffect(() => {
        if (!isDialogOpen) {
            return;
        }
        if (!newServiceType && serviceTypeOptions.length > 0) {
            const defaultType = serviceTypeOptions[0];
            setNewServiceType(defaultType);
            setNewServiceId(computeNextServiceId(defaultType));
        } else if (newServiceType) {
            setNewServiceId(computeNextServiceId(newServiceType));
        }
    }, [isDialogOpen, serviceTypeOptions, computeNextServiceId, newServiceType]);

    const resetDialogState = useCallback(() => {
        setIsDialogOpen(false);
        setNewServiceType('');
        setNewServiceLabel('');
        setNewServiceId('');
        setIsSubmitting(false);
        setFormError(null);
    }, []);

    const handleSubmitService = useCallback(async () => {
        if (!newServiceType || !newServiceLabel || !newServiceId) {
            setFormError('All fields are required.');
            return;
        }
        setIsSubmitting(true);
        setFormError(null);
        try {
            await axios.post(`${API_ROOT}/api/admin/services`, {
                service_id: newServiceId,
                label: newServiceLabel,
                service_type: newServiceType,
                status_config: '{}',
                metric_config: '{}',
                enabled: true,
            });

            await queryClient.invalidateQueries({ queryKey: ['flowChart'] });
            resetDialogState();
        } catch (error: any) {
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                setFormError(error.response.data.detail);
            } else {
                setFormError('Failed to create service. Please try again.');
            }
        } finally {
            setIsSubmitting(false);
        }
    }, [newServiceType, newServiceLabel, newServiceId, queryClient, resetDialogState]);

    // Available upstream services (exclude selected service and its downstream dependents)
    const availableUpstreamServices = useMemo(() => {
        if (!flowChart?.serviceNodes || !selectedNode) {
            return [];
        }

        const tempNodes = flowChart.serviceNodes.map(i => ({
            id: i.service_id,
            position: { x: 0, y: 0 },
            data: { service_id: i.service_id, label: i.label, type: i.service_type }
        })) as Node[];
        
        const tempEdges = flowChart.serviceRelations.map(i => ({
            id: i.relation_id,
            source: i.source,
            target: i.target
        })) as Edge[];

        const downstreamDependents = get_downstream_dependents(selectedNode.id, tempNodes, tempEdges);
        const excludeIds = new Set([selectedNode.id, ...downstreamDependents.map(node => node.id)]);
        
        return flowChart.serviceNodes
            .filter(service => !excludeIds.has(service.service_id))
            .slice()
            .sort((a, b) => {
                const typeCompare = (a.service_type ?? '').localeCompare(b.service_type ?? '');
                if (typeCompare !== 0) {
                    return typeCompare;
                }
                return (a.label ?? '').localeCompare(b.label ?? '');
            });
    }, [flowChart?.serviceNodes, flowChart?.serviceRelations, selectedNode]);

    const downstreamDependents = useMemo(() => {
        if (!selectedNode) {
            return [];
        }
        return get_downstream_dependents(
            selectedNode.id,
            (flowChart?.serviceNodes ?? []).map(node => ({
                id: node.service_id,
                position: { x: 0, y: 0 },
                data: { service_id: node.service_id, label: node.label, type: node.service_type }
            })) as Node[],
            (flowChart?.serviceRelations ?? []).map(rel => ({
                id: rel.relation_id,
                source: rel.source,
                target: rel.target
            })) as Edge[],
        );
    }, [flowChart?.serviceNodes, flowChart?.serviceRelations, selectedNode]);

    const fetchExistingWatchers = useCallback(async (serviceId: string) => {
        setIsLoadingWatchers(true);
        try {
            const response = await axios.get(`${API_ROOT}/api/admin/services/${serviceId}/watchers`);
            setExistingWatchers(response.data);
        } catch (error) {
            console.error('Error fetching watchers:', error);
            setExistingWatchers([]);
        } finally {
            setIsLoadingWatchers(false);
        }
    }, []);

    const resetWatcherDialog = useCallback(() => {
        setIsWatcherDialogOpen(false);
        setNewWatcherEmail('');
        setIsWatcherSubmitting(false);
        setWatcherFormError(null);
        setExistingWatchers([]);
        setRemovingWatcherEmail(null);
        setRemoveConfirmationInput('');
        setIsRemovingWatcher(false);
    }, []);

    const fetchExistingDependencies = useCallback(async (serviceId: string) => {
        setIsLoadingDependencies(true);
        try {
            // Fetch relations where the current service is the target (upstream dependencies)
            const response = await axios.get(`${API_ROOT}/api/admin/relations`);
            const allRelations = response.data;
            
            // Filter for relations where current service is the target and get service labels
            const upstreamRelations = allRelations.filter((rel: any) => rel.target_service_id === serviceId);
            
            // Get service details to add labels - fetch ALL services including disabled ones
            const servicesResponse = await axios.get(`${API_ROOT}/api/admin/services?limit=1000`);
            const services = servicesResponse.data;
            const serviceMap = new Map(services.map((s: any) => [s.service_id, s.label]));
            
            const dependenciesWithLabels = upstreamRelations.map((rel: any) => {
                const sourceLabel = serviceMap.get(rel.source_service_id);
                return {
                    relation_id: rel.relation_id,
                    source_service_id: rel.source_service_id,
                    target_service_id: rel.target_service_id,
                    source_label: sourceLabel || `${rel.source_service_id} (missing/disabled)`
                };
            });
            
            setExistingDependencies(dependenciesWithLabels);
        } catch (error) {
            console.error('Error fetching dependencies:', error);
            setExistingDependencies([]);
        } finally {
            setIsLoadingDependencies(false);
        }
    }, []);

    const resetDependencyDialog = useCallback(() => {
        setIsDependencyDialogOpen(false);
        setNewDependencyServiceId('');
        setIsDependencySubmitting(false);
        setDependencyFormError(null);
        setExistingDependencies([]);
        setRemovingDependencyId(null);
        setDependencyRemoveConfirmationInput('');
        setIsRemovingDependency(false);
    }, []);

    const handleSubmitWatcher = useCallback(async () => {
        if (!newWatcherEmail || !selectedNode) {
            setWatcherFormError('Email is required.');
            return;
        }
        setIsWatcherSubmitting(true);
        setWatcherFormError(null);
        try {
            await axios.post(`${API_ROOT}/api/admin/services/${selectedNode.id}/watchers`, {
                email: newWatcherEmail,
            });
            setNewWatcherEmail('');
            // Refresh the watchers list
            await fetchExistingWatchers(selectedNode.id);
        } catch (error: any) {
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                setWatcherFormError(error.response.data.detail);
            } else {
                setWatcherFormError('Failed to add watcher. Please try again.');
            }
        } finally {
            setIsWatcherSubmitting(false);
        }
    }, [newWatcherEmail, selectedNode, fetchExistingWatchers]);

    const handleRemoveWatcher = useCallback(async (email: string) => {
        if (!selectedNode || removeConfirmationInput !== 'remove') {
            return;
        }
        setIsRemovingWatcher(true);
        try {
            await axios.delete(`${API_ROOT}/api/admin/services/${selectedNode.id}/watchers`, {
                data: { email }
            });
            // Refresh the watchers list
            await fetchExistingWatchers(selectedNode.id);
            setRemovingWatcherEmail(null);
            setRemoveConfirmationInput('');
        } catch (error) {
            console.error('Error removing watcher:', error);
            setWatcherFormError('Failed to remove watcher. Please try again.');
        } finally {
            setIsRemovingWatcher(false);
        }
    }, [selectedNode, removeConfirmationInput, fetchExistingWatchers]);

    // Fetch existing watchers when watcher dialog opens
    useEffect(() => {
        if (isWatcherDialogOpen && selectedNode) {
            fetchExistingWatchers(selectedNode.id);
        }
    }, [isWatcherDialogOpen, selectedNode, fetchExistingWatchers]);

    // Fetch existing dependencies when dependency dialog opens
    useEffect(() => {
        if (isDependencyDialogOpen && selectedNode) {
            fetchExistingDependencies(selectedNode.id);
        }
    }, [isDependencyDialogOpen, selectedNode, fetchExistingDependencies]);

    const handleSubmitDependency = useCallback(async () => {
        if (!newDependencyServiceId || !selectedNode) {
            setDependencyFormError('Please select a service.');
            return;
        }
        setIsDependencySubmitting(true);
        setDependencyFormError(null);
        try {
            const { data } = await axios.post<RelationResponse>(`${API_ROOT}/api/admin/relations`, {
                source_service_id: newDependencyServiceId,
                target_service_id: selectedNode.id,
                relation_type: 'dependency',
                enabled: true,
            });
            appendRelationToFlowChartCache({
                relation_id: data.relation_id,
                source_service_id: data.source_service_id,
                target_service_id: data.target_service_id,
            });
            setNewDependencyServiceId('');
            // Refresh the dependencies list
            await fetchExistingDependencies(selectedNode.id);
        } catch (error: any) {
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                setDependencyFormError(error.response.data.detail);
            } else {
                setDependencyFormError('Failed to add dependency. Please try again.');
            }
        } finally {
            setIsDependencySubmitting(false);
        }
    }, [newDependencyServiceId, selectedNode, appendRelationToFlowChartCache, fetchExistingDependencies]);

    const handleRemoveDependency = useCallback(async (relationId: string) => {
        if (!selectedNode || dependencyRemoveConfirmationInput !== 'remove') {
            return;
        }
        setIsRemovingDependency(true);
        try {
            await axios.delete(`${API_ROOT}/api/admin/relations/${relationId}`);
            removeRelationFromFlowChartCache(relationId);
            setExistingDependencies(prev => prev.filter(dep => dep.relation_id !== relationId));
            setRemovingDependencyId(null);
            setDependencyRemoveConfirmationInput('');
        } catch (error) {
            console.error('Error removing dependency:', error);
            setDependencyFormError('Failed to remove dependency. Please try again.');
        } finally {
            setIsRemovingDependency(false);
        }
    }, [selectedNode, dependencyRemoveConfirmationInput, removeRelationFromFlowChartCache]);

    const handleOpenDeleteDialog = useCallback(() => {
        setDeleteError(null);
        setDeleteConfirmationInput('');
        setIsDeleteDialogOpen(true);
    }, []);

    const handleCloseDeleteDialog = useCallback(() => {
        setIsDeleteDialogOpen(false);
        setDeleteConfirmationInput('');
        setDeleteError(null);
        setIsDeletingService(false);
    }, []);

    const handleDeleteService = useCallback(async () => {
        if (!selectedNode) {
            return;
        }
        const requiredPhrase = `remove ${(selectedNode.data as any)?.label ?? ''}`.trim();
        if (!deleteConfirmationInput || deleteConfirmationInput.trim() !== requiredPhrase) {
            setDeleteError(`Type "${requiredPhrase}" to confirm.`);
            return;
        }
        setIsDeletingService(true);
        setDeleteError(null);
        try {
            await axios.delete(`${API_ROOT}/api/admin/services/${selectedNode.id}`);
            await queryClient.invalidateQueries({ queryKey: ['flowChart'] });
            setSelectedNode(null);
            handleCloseDeleteDialog();
        } catch (error: any) {
            if (axios.isAxiosError(error) && error.response?.data?.detail) {
                setDeleteError(error.response.data.detail);
            } else {
                setDeleteError('Failed to delete service. Please try again.');
            }
        } finally {
            setIsDeletingService(false);
        }
    }, [selectedNode, deleteConfirmationInput, queryClient, handleCloseDeleteDialog]);

    const setEventStream = (enable: boolean) => {
        if (!enable) {
            sseRef.current?.close();
            sseRef.current = undefined;
            return;
        }

        const sse = new EventSourcePolyfill(API_ROOT + '/api/status/stream');
        sse.onopen = () => {
            sseRef.current = sse;
        };

        // @ts-expect-error polyfill type error
        sse.onmessage = (e: MessageEvent) => {
            const noti: Notification = JSON.parse(e.data);
            if (noti.service_id) {
                queryClient.invalidateQueries({ queryKey: ['serviceStatus', noti.service_id] });
            }
        };

        // @ts-expect-error polyfill type error
        sse.onerror = (e: Event) => {
            console.error(e);
            sse.close();
            sseRef.current = undefined;
        };
    };

    useEffect(() => {
        setEventStream(true);
        return () => setEventStream(false);
    }, [queryClient]);

    useEffect(() => {
        if (new Date(endDate) < new Date(startDate)) {
            setEndDate(startDate);
        }
    }, [startDate, endDate]);

    return (
        <>
            <div className="h-screen w-full bg-slate-50 flex flex-col lg:flex-row">
            
            <div className="w-full lg:w-1/2 bg-white border-b lg:border-b-0 lg:border-r ag-theme-balham flex flex-col h-[50vh] lg:h-screen">
                {/* Header Section */}
                <div className="flex-shrink-0 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-600 text-white p-4 border-b border-slate-500/30">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-xl font-bold">Service Monitor</h1>
                            <p className="text-slate-200 text-sm mt-1">Real-time service health and dependency tracking</p>
                        </div>
                        <div className="flex items-center gap-4">
                            <div className="text-right">
                                <div className="text-xs text-slate-300">Total Services</div>
                                <div className="text-lg font-semibold">{flowChart?.serviceNodes?.length || 0}</div>
                            </div>
                            <button
                                type="button"
                                onClick={() => setIsDialogOpen(true)}
                                className="flex h-9 w-9 items-center justify-center rounded-full border border-white/40 bg-white/10 transition hover:bg-white/20"
                                aria-label="Add service"
                            >
                                <span className="text-2xl leading-none">+</span>
                            </button>
                        </div>
                    </div>
                </div>
                
                {/* Service List Section */}
                <div className="flex-grow overflow-y-auto min-h-0">
                    {flowChart?.serviceNodes ? (
                        <ServiceList services={flowChart.serviceNodes} onSelectService={handleSelectService} />
                    ) : (
                        <div className="flex items-center justify-center h-full text-slate-500">Loading services...</div>
                    )}
                </div>
            </div>

            <div className="w-full flex-1 min-h-0 bg-white flex flex-col px-5 py-4 overflow-y-auto lg:flex-none lg:w-1/2 lg:h-screen lg:px-4 lg:py-4 lg:overflow-visible">
                {selectedNode ? (
                    <div className="flex flex-col px-2 sm:px-4 lg:px-0 lg:flex-1 lg:min-h-0 lg:h-full">
                        {/* Top Section - Service Details, Dependencies, and Placeholders (Fixed Height) */}
                        <div className="flex-shrink-0">
                            {/* Service Details Header */}
                            <div className="flex-shrink-0 pb-4">
                                <div className="flex flex-wrap items-center gap-2 mb-4">
                                    <h2 className="text-lg font-bold">{(selectedNode.data as any)?.label || 'N/A'}</h2>
                                    <div className="flex items-center bg-slate-100 rounded-full px-2 py-1 text-xs font-mono">
                                        <span className="font-semibold text-slate-500 mr-1">ID:</span>
                                        <span className="text-slate-700">{(selectedNode.data as any)?.service_id || selectedNode.id}</span>
                                    </div>
                                    <div className="flex items-center bg-emerald-100 rounded-full px-2 py-1 text-xs">
                                        <span className="font-semibold text-emerald-600 mr-1">Type:</span>
                                        <span className="text-emerald-800">{(selectedNode.data as any)?.type || 'N/A'}</span>
                                    </div>
                                </div>
                                
                                {/* Action Buttons */}
                                <div className="flex items-center gap-2 mb-4">
                                    <button
                                        type="button"
                                        onClick={() => setIsWatcherDialogOpen(true)}
                                        className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                        aria-label="Add watcher"
                                    >
                                        Add Watcher
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => setIsDependencyDialogOpen(true)}
                                        className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                        aria-label="Add upstream dependency"
                                    >
                                        Add Dependency
                                    </button>
                                    {isWorkflowMonitorEligible && (
                                        <button
                                            type="button"
                                            onClick={openWorkflowMonitorDialog}
                                            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 disabled:cursor-not-allowed"
                                            aria-label="Add workflow monitor"
                                            disabled={isWorkflowMonitorFetching}
                                        >
                                            {workflowMonitorExists ? 'Manage Workflow Monitor' : 'Add Workflow Monitor'}
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        onClick={handleOpenDeleteDialog}
                                        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                                        aria-label="Delete service"
                                        disabled={downstreamDependents.length > 0}
                                    >
                                        Delete
                                    </button>
                                </div>
                            </div>


                        </div>

                        {/* Bottom Section - Dependency Flow Chart (Flexible Height) */}
                        <div className="border-t pt-4 flex flex-col gap-4 lg:gap-3 lg:flex-1 lg:min-h-0 lg:overflow-hidden">
                            <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                                <h3 className="text-md font-bold">Dependency Graph</h3>
                                <div className="flex items-center gap-2 text-xs text-slate-600">
                                    <label className="flex items-center gap-1" htmlFor="dependency-start-date">
                                        <span>Start</span>
                                        <input
                                            id="dependency-start-date"
                                            type="date"
                                            value={startDate}
                                            max={endDate}
                                            onChange={(event) => setStartDate(event.target.value)}
                                            className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 focus:border-slate-500 focus:outline-none"
                                        />
                                    </label>
                                    <label className="flex items-center gap-1" htmlFor="dependency-end-date">
                                        <span>End</span>
                                        <input
                                            id="dependency-end-date"
                                            type="date"
                                            value={endDate}
                                            min={startDate}
                                            onChange={(event) => setEndDate(event.target.value)}
                                            className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 focus:border-slate-500 focus:outline-none"
                                        />
                                    </label>
                                </div>
                            </div>
                            <div className="h-[28rem] lg:flex-1 lg:h-full lg:overflow-y-auto">
                                {flowChart ? (
                                    <DetailedFlowView
                                        serviceNodes={flowChart.serviceNodes}
                                        serviceRelations={flowChart.serviceRelations}
                                        selectedNode={selectedNode}
                                        outageService={outageService}
                                        setOutageService={setOutageService}
                                        startDate={startDate}
                                        endDate={endDate}
                                    />
                                ) : (
                                    <div className="flex items-center justify-center h-full text-slate-500">Loading graph...</div>
                                )}
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="text-slate-500 text-center py-8">
                        <p>Select a service from the list to view details and its dependency graph.</p>
                    </div>
                )}
            </div>
            </div>

                        {isWorkflowMonitorDialogOpen && (
                            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
                                <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
                                    <div className="flex items-center justify-between border-b px-4 py-3">
                                        <h3 className="text-lg font-semibold text-slate-800">Workflow Monitor</h3>
                                        <button
                                            type="button"
                                            onClick={closeWorkflowMonitorDialog}
                                            className="text-xl text-slate-500 hover:text-slate-700"
                                            aria-label="Close dialog"
                                        >
                                            ×
                                        </button>
                                    </div>
                                    <div className="px-4 py-4 space-y-4">
                                        {isWorkflowMonitorFetching ? (
                                            <div className="text-sm text-slate-500">Loading workflow monitor configuration…</div>
                                        ) : workflowMonitorErrorMessage ? (
                                            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                                                {workflowMonitorErrorMessage}
                                            </div>
                                        ) : null}

                                                                                {workflowMonitorExists && workflowMonitorConfig ? (
                                                                                    <div className="space-y-3">
                                                                                        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
                                                                                            <div className="flex items-start justify-between gap-3">
                                                                                                <div>
                                                                                                    <p className="font-semibold">Existing configuration</p>
                                                                                                    <p className="mt-1"><span className="font-medium">Workflow:</span> {workflowMonitorConfig.workflow_type}</p>
                                                                                                    <p><span className="font-medium">Interval (minutes):</span> {workflowMonitorConfig.interval_minute}</p>
                                                                                                    <p className="mt-2 text-emerald-700">Each service supports only one workflow monitor.</p>
                                                                                                </div>
                                                                                                <button
                                                                                                    type="button"
                                                                                                    onClick={() => setShowWorkflowRemoveConfirmation((previous) => !previous)}
                                                                                                    className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-700 transition hover:bg-red-50"
                                                                                                >
                                                                                                    {showWorkflowRemoveConfirmation ? 'Cancel removal' : 'Remove'}
                                                                                                </button>
                                                                                            </div>
                                                                                        </div>
                                                                                        {showWorkflowRemoveConfirmation && (
                                                                                            <div className="space-y-2">
                                                                                                <label htmlFor="workflow-remove-confirm" className="block text-xs font-semibold uppercase tracking-wide text-slate-600">Type remove to confirm</label>
                                                                                                <input
                                                                                                    id="workflow-remove-confirm"
                                                                                                    type="text"
                                                                                                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 focus:border-slate-500 focus:outline-none"
                                                                                                    value={workflowRemoveConfirmation}
                                                                                                    onChange={(event) => setWorkflowRemoveConfirmation(event.target.value)}
                                                                                                    placeholder="remove"
                                                                                                    disabled={isWorkflowMonitorRemoving}
                                                                                                />
                                                                                                <button
                                                                                                    type="button"
                                                                                                    onClick={() => void handleRemoveWorkflowMonitor()}
                                                                                                    className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                                                                                                    disabled={isWorkflowMonitorRemoving || workflowRemoveConfirmation.trim().toLowerCase() !== 'remove'}
                                                                                                >
                                                                                                    {isWorkflowMonitorRemoving ? 'Removing…' : 'Confirm removal'}
                                                                                                </button>
                                                                                            </div>
                                                                                        )}
                                                                                    </div>
                                                                                ) : (
                                            <div className="space-y-4">
                                                <div className="space-y-1">
                                                    <label htmlFor="workflow-type" className="block text-xs font-semibold uppercase tracking-wide text-slate-600">Workflow Type</label>
                                                    <input
                                                        id="workflow-type"
                                                        type="text"
                                                        className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 focus:border-slate-500 focus:outline-none"
                                                        value={workflowTypeInput}
                                                        onChange={(event) => setWorkflowTypeInput(event.target.value)}
                                                        placeholder="e.g. WriteStatTable"
                                                        disabled={isWorkflowSubmitting}
                                                    />
                                                </div>
                                                <div className="space-y-1">
                                                    <label htmlFor="workflow-interval" className="block text-xs font-semibold uppercase tracking-wide text-slate-600">Interval (minutes)</label>
                                                                                <input
                                                                                    id="workflow-interval"
                                                                                    type="number"
                                                                                    min={1}
                                                                                    max={1440}
                                                                                    step={1}
                                                                                    className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 focus:border-slate-500 focus:outline-none"
                                                                                    value={workflowIntervalInput}
                                                                                    onChange={(event) => {
                                                                                        const next = Number.parseInt(event.target.value, 10);
                                                                                        if (Number.isNaN(next)) {
                                                                                            setWorkflowIntervalInput(1);
                                                                                            return;
                                                                                        }
                                                                                        setWorkflowIntervalInput(Math.min(1440, Math.max(1, next)));
                                                                                    }}
                                                                                    disabled={isWorkflowSubmitting}
                                                                                />
                                                </div>
                                            </div>
                                        )}

                                        {workflowFormError && (
                                            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                                                {workflowFormError}
                                            </div>
                                        )}
                                    </div>
                                    <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
                                                            <button
                                                                type="button"
                                                                onClick={closeWorkflowMonitorDialog}
                                                                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                                                            >
                                                                Close
                                                            </button>
                                                                                {!workflowMonitorExists && (
                                                                <button
                                                                    type="button"
                                                                    onClick={() => void handleSubmitWorkflowMonitor()}
                                                                    className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                                                                    disabled={workflowMonitorExists || isWorkflowSubmitting || Boolean(workflowMonitorErrorMessage)}
                                                                >
                                                                    {isWorkflowSubmitting ? 'Saving…' : 'Create Monitor'}
                                                                </button>
                                                            )}
                                    </div>
                                </div>
                            </div>
                        )}

            {/* Add Watcher Dialog */}
            {isWatcherDialogOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
                    <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
                        <div className="flex items-center justify-between border-b px-4 py-3">
                            <h3 className="text-lg font-semibold text-slate-800">Manage Watchers</h3>
                            <button
                                type="button"
                                onClick={resetWatcherDialog}
                                className="text-xl text-slate-500 hover:text-slate-700"
                                aria-label="Close dialog"
                            >
                                ×
                            </button>
                        </div>
                        <div className="px-4 py-4 space-y-4">
                            {/* Existing Watchers List */}
                            <div>
                                <h4 className="text-sm font-medium text-slate-700 mb-2">Current Watchers</h4>
                                {isLoadingWatchers ? (
                                    <div className="text-sm text-slate-500">Loading watchers...</div>
                                ) : existingWatchers.length > 0 ? (
                                    <div className="space-y-2 max-h-32 overflow-y-auto">
                                        {existingWatchers.map((watcher) => (
                                            <div key={watcher.email} className="flex items-center justify-between bg-slate-50 px-3 py-2 rounded-md">
                                                <span className="text-sm text-slate-700">{watcher.email}</span>
                                                {removingWatcherEmail === watcher.email ? (
                                                    <div className="flex items-center gap-2">
                                                        <input
                                                            type="text"
                                                            value={removeConfirmationInput}
                                                            onChange={(e) => setRemoveConfirmationInput(e.target.value)}
                                                            placeholder="Type 'remove'"
                                                            className="text-xs px-2 py-1 border border-slate-300 rounded w-24"
                                                        />
                                                        <button
                                                            onClick={() => handleRemoveWatcher(watcher.email)}
                                                            disabled={removeConfirmationInput !== 'remove' || isRemovingWatcher}
                                                            className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                                                        >
                                                            {isRemovingWatcher ? '...' : 'Confirm'}
                                                        </button>
                                                        <button
                                                            onClick={() => {
                                                                setRemovingWatcherEmail(null);
                                                                setRemoveConfirmationInput('');
                                                            }}
                                                            className="text-xs px-2 py-1 bg-slate-300 text-slate-700 rounded hover:bg-slate-400"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        onClick={() => setRemovingWatcherEmail(watcher.email)}
                                                        className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                                                    >
                                                        Remove
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-sm text-slate-500">No watchers configured</div>
                                )}
                            </div>

                            {/* Add New Watcher Form */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700" htmlFor="watcher-email">
                                    Add New Watcher
                                </label>
                                <input
                                    id="watcher-email"
                                    type="email"
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-600 focus:outline-none"
                                    value={newWatcherEmail}
                                    onChange={(event) => setNewWatcherEmail(event.target.value)}
                                    placeholder="Enter email address"
                                />
                            </div>

                            {watcherFormError && (
                                <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                                    {watcherFormError}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
                            <button
                                type="button"
                                onClick={resetWatcherDialog}
                                className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={handleSubmitWatcher}
                                disabled={isWatcherSubmitting}
                                className="rounded-md bg-slate-800 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-60"
                            >
                                {isWatcherSubmitting ? 'Adding…' : 'Add Watcher'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Add Dependency Dialog */}
            {isDependencyDialogOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
                    <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
                        <div className="flex items-center justify-between border-b px-4 py-3">
                            <h3 className="text-lg font-semibold text-slate-800">Manage Dependencies</h3>
                            <button
                                type="button"
                                onClick={resetDependencyDialog}
                                className="text-xl text-slate-500 hover:text-slate-700"
                                aria-label="Close dialog"
                            >
                                ×
                            </button>
                        </div>
                        <div className="px-4 py-4 space-y-4">
                            {/* Existing Dependencies List */}
                            <div>
                                <h4 className="text-sm font-medium text-slate-700 mb-2">Current Dependencies</h4>
                                {isLoadingDependencies ? (
                                    <div className="text-sm text-slate-500">Loading dependencies...</div>
                                ) : existingDependencies.length > 0 ? (
                                    <div className="space-y-2 max-h-32 overflow-y-auto">
                                        {existingDependencies.map((dependency) => (
                                            <div key={dependency.relation_id} className="flex items-center justify-between bg-slate-50 px-3 py-2 rounded-md">
                                                <span className="text-sm text-slate-700">{dependency.source_label} ({dependency.source_service_id})</span>
                                                {removingDependencyId === dependency.relation_id ? (
                                                    <div className="flex items-center gap-2">
                                                        <input
                                                            type="text"
                                                            value={dependencyRemoveConfirmationInput}
                                                            onChange={(e) => setDependencyRemoveConfirmationInput(e.target.value)}
                                                            placeholder="Type 'remove'"
                                                            className="text-xs px-2 py-1 border border-slate-300 rounded w-24"
                                                        />
                                                        <button
                                                            onClick={() => handleRemoveDependency(dependency.relation_id)}
                                                            disabled={dependencyRemoveConfirmationInput !== 'remove' || isRemovingDependency}
                                                            className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                                                        >
                                                            {isRemovingDependency ? '...' : 'Confirm'}
                                                        </button>
                                                        <button
                                                            onClick={() => {
                                                                setRemovingDependencyId(null);
                                                                setDependencyRemoveConfirmationInput('');
                                                            }}
                                                            className="text-xs px-2 py-1 bg-slate-300 text-slate-700 rounded hover:bg-slate-400"
                                                        >
                                                            Cancel
                                                        </button>
                                                    </div>
                                                ) : (
                                                    <button
                                                        onClick={() => setRemovingDependencyId(dependency.relation_id)}
                                                        className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                                                    >
                                                        Remove
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="text-sm text-slate-500">No dependencies configured</div>
                                )}
                            </div>

                            {/* Add New Dependency Form */}
                            <div>
                                <label className="block text-sm font-medium text-slate-700" htmlFor="dependency-service">
                                    Add New Dependency
                                </label>
                                <select
                                    id="dependency-service"
                                    className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-600 focus:outline-none"
                                    value={newDependencyServiceId}
                                    onChange={(event) => setNewDependencyServiceId(event.target.value)}
                                >
                                    <option value="" disabled>Select a service</option>
                                    {Array.from(
                                        availableUpstreamServices.reduce((acc, service) => {
                                            const type = service.service_type ?? 'Ungrouped';
                                            if (!acc.has(type)) {
                                                acc.set(type, []);
                                            }
                                            acc.get(type)?.push(service);
                                            return acc;
                                        }, new Map<string, typeof availableUpstreamServices>())
                                    ).map(([type, services]) => (
                                        <optgroup key={type} label={type}>
                                            {services.map(service => (
                                                <option key={service.service_id} value={service.service_id}>
                                                    {service.label} ({service.service_id})
                                                </option>
                                            ))}
                                        </optgroup>
                                    ))}
                                </select>
                                <p className="mt-1 text-xs text-slate-500">
                                    This service will depend on the selected upstream service
                                </p>
                            </div>

                            {dependencyFormError && (
                                <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                                    {dependencyFormError}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
                            <button
                                type="button"
                                onClick={resetDependencyDialog}
                                className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={handleSubmitDependency}
                                disabled={isDependencySubmitting}
                                className="rounded-md bg-slate-800 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-60"
                            >
                                {isDependencySubmitting ? 'Adding…' : 'Add Dependency'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Delete Service Dialog */}
            {isDeleteDialogOpen && selectedNode && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
                    <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
                        <div className="flex items-center justify-between border-b px-4 py-3">
                            <h3 className="text-lg font-semibold text-slate-800">Delete Service</h3>
                            <button
                                type="button"
                                onClick={handleCloseDeleteDialog}
                                className="text-xl text-slate-500 hover:text-slate-700"
                                aria-label="Close dialog"
                            >
                                ×
                            </button>
                        </div>
                        <div className="px-4 py-4 space-y-4">
                            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                                This action cannot be undone. Deleting <strong>{(selectedNode.data as any)?.label ?? selectedNode.id}</strong> will remove its configuration permanently.
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700" htmlFor="delete-confirmation">
                                    Type <span className="font-mono">remove {(selectedNode.data as any)?.label ?? selectedNode.id}</span> to confirm
                                </label>
                                <input
                                    id="delete-confirmation"
                                    type="text"
                                    value={deleteConfirmationInput}
                                    onChange={(event) => setDeleteConfirmationInput(event.target.value)}
                                    className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-red-500 focus:outline-none"
                                    placeholder={`remove ${(selectedNode.data as any)?.label ?? selectedNode.id}`}
                                />
                            </div>
                            {deleteError && (
                                <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                                    {deleteError}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
                            <button
                                type="button"
                                onClick={handleCloseDeleteDialog}
                                className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={handleDeleteService}
                                disabled={isDeletingService}
                                className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-500 disabled:opacity-60"
                            >
                                {isDeletingService ? 'Deleting…' : 'Delete Service'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {isDialogOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" role="dialog" aria-modal="true">
                    <div className="w-full max-w-md rounded-lg bg-white shadow-xl">
                    <div className="flex items-center justify-between border-b px-4 py-3">
                        <h3 className="text-lg font-semibold text-slate-800">Add New Service</h3>
                        <button
                            type="button"
                            onClick={resetDialogState}
                            className="text-xl text-slate-500 hover:text-slate-700"
                            aria-label="Close dialog"
                        >
                            ×
                        </button>
                    </div>
                    <div className="px-4 py-4 space-y-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-700" htmlFor="new-service-type">
                                Type
                            </label>
                            <select
                                id="new-service-type"
                                className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-600 focus:outline-none"
                                value={newServiceType}
                                onChange={(event) => setNewServiceType(event.target.value)}
                            >
                                <option value="" disabled>Select a type</option>
                                {serviceTypeOptions.map(type => (
                                    <option key={type} value={type}>{type}</option>
                                ))}
                            </select>
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-700" htmlFor="new-service-label">
                                Label
                            </label>
                            <input
                                id="new-service-label"
                                type="text"
                                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-600 focus:outline-none"
                                value={newServiceLabel}
                                onChange={(event) => setNewServiceLabel(event.target.value)}
                                placeholder="Readable name for the service"
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-slate-700" htmlFor="new-service-id">
                                Service ID
                            </label>
                            <input
                                id="new-service-id"
                                type="text"
                                className="mt-1 block w-full rounded-md border border-slate-300 bg-slate-100 px-3 py-2 text-sm text-slate-600"
                                value={newServiceId}
                                readOnly
                            />
                            <p className="mt-1 text-xs text-slate-500">ID format: type-number (auto generated)</p>
                        </div>

                        {formError && (
                            <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-600">
                                {formError}
                            </div>
                        )}
                    </div>
                    <div className="flex items-center justify-end gap-2 border-t px-4 py-3">
                        <button
                            type="button"
                            onClick={resetDialogState}
                            className="rounded-md border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            onClick={handleSubmitService}
                            disabled={isSubmitting}
                            className="rounded-md bg-slate-800 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-60"
                        >
                            {isSubmitting ? 'Adding…' : 'Add Service'}
                        </button>
                    </div>
                    </div>
                </div>
            )}
        </>
    );
}
