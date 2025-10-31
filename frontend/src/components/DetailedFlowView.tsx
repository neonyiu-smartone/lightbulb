import { useEffect, useState, useRef, type Dispatch, type SetStateAction } from 'react';
import dagre from '@dagrejs/dagre';
import {
    Background,
    ReactFlow,
    ConnectionLineType,
    Controls,
    type Node, type Edge, type ReactFlowInstance
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import ServiceCard from "@/components/ServiceCard.tsx";
import { InitialPosition, nodeWidth, nodeHeight } from "@/constants.tsx";
import { type ServiceNode as ServiceNodeType, type ServiceRelation } from '@/model.tsx';

const nodeTypes = {
    baseNode: ServiceCard,
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

// Function to get all services that the target service depends on (upstream)
const get_upstream_dependencies = (target_service_id: string, nodes: Array<Node>, edges: Array<Edge>): Array<Node> => {
    const dependencies = new Set<string>();
    const visited = new Set<string>();

    const findUpstream = (serviceId: string) => {
        if (visited.has(serviceId)) {
            return;
        }
        visited.add(serviceId);

        const dependencyEdges = edges.filter(edge => edge.target === serviceId);
        dependencyEdges.forEach(edge => {
            const dependencyId = edge.source;
            dependencies.add(dependencyId);
            findUpstream(dependencyId);
        });
    };

    findUpstream(target_service_id);

    return nodes.filter(node => dependencies.has(node.id));
};

const getElementLayout = (serviceNodes: Array<ServiceNodeType>,
                          serviceEdges: Array<ServiceRelation>,
                          outageService: Array<string>,
                          setOutageService: Dispatch<SetStateAction<string[]>>,
                          nodeDimensions: Record<string, number>,
                          highlightedNodeIds: Set<string> = new Set(),
                          selectedNodeId: string | null = null,
                          direction = 'LR',
                          range?: { startDate: string; endDate: string }): {edges: Array<Edge>, nodes: Array<Node>} => {
    
    // Create a fresh dagre graph for each layout calculation
    const localDagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
    const isHorizontal = direction === 'LR';
    localDagreGraph.setGraph({ rankdir: direction });

    // Calculate all nodes affected by outages (outage nodes + their dependents)
    const outageAffectedIds = new Set<string>();
    const tempNodes = serviceNodes.map(i => ({
        id: i.service_id,
        position: { x: 0, y: 0 },
        data: { service_id: i.service_id, label: i.label, type: i.service_type }
    })) as Node[];
    
    const tempEdges = serviceEdges.map(i => ({
        id: i.relation_id,
        source: i.source,
        target: i.target
    })) as Edge[];

    // For each service in outage, find all its dependents
    outageService.forEach(outageServiceId => {
        outageAffectedIds.add(outageServiceId);
        const dependents = get_downstream_dependents(outageServiceId, tempNodes, tempEdges);
        dependents.forEach(dep => outageAffectedIds.add(dep.id));
    });

    const nodes = serviceNodes.map(i => {
        const isHighlighted = highlightedNodeIds.has(i.service_id);
        const isSelected = selectedNodeId === i.service_id;
        const isInOutage = outageService.includes(i.service_id);
        const isOutageDependent = outageAffectedIds.has(i.service_id) && !isInOutage;
        const isDimmed = selectedNodeId && !isHighlighted && !isSelected;

        // Determine the appropriate className based on priority
        let className = '';
        if (isInOutage) {
            className = 'outage-node';
        } else if (isOutageDependent) {
            className = 'outage-dependent-node';
        } else if (isSelected) {
            className = 'selected-node';
        } else if (isHighlighted) {
            className = 'highlighted-node';
        }

        return {
            id: i.service_id,
            position: InitialPosition,
            data: {
                service_id: i.service_id,
                label: i.label,
                type: i.service_type,
                outageService: outageService,
                setOutageService: setOutageService,
                dateRange: range,
            },
            type: "baseNode",
            style: {
                opacity: isDimmed ? 0.3 : 1,
                transition: 'opacity 0.3s ease',
                zIndex: isInOutage ? 2000 : isOutageDependent ? 1500 : isSelected ? 3000 : isHighlighted ? 100 : 1,
            },
            className,
        };
    });

    const edges = serviceEdges.map(i => {
        const isOutage = outageService.indexOf(i.source) > -1;
        const isHighlighted = highlightedNodeIds.has(i.source) && highlightedNodeIds.has(i.target);
        const isOutageRelated = outageAffectedIds.has(i.source) && outageAffectedIds.has(i.target);
        const isDimmed = selectedNodeId && !isHighlighted;

        // Determine edge className based on priority
        let className = '';
        if (isOutageRelated || isOutage) {
            className = 'outage';
        } else if (isHighlighted) {
            className = 'highlighted';
        }

        return {
            id: i.relation_id,
            source: i.source,
            target: i.target,
            animated: isHighlighted || isOutage || isOutageRelated,
            style: {
                stroke: isOutage || isOutageRelated ? 'oklch(0.65 0.25 15)' : 
                       isHighlighted ? 'oklch(0.6 0.15 240)' : 'oklch(0.5 0.01 240)',
                strokeWidth: isOutage || isOutageRelated ? 4 : isHighlighted ? 3 : 1,
                opacity: isDimmed ? 0.2 : !isHighlighted && !isOutage && !isOutageRelated ? 0.65 : 1,
                transition: 'opacity 0.3s ease, stroke-width 0.3s ease',
                zIndex: isOutage || isOutageRelated ? 200 : isHighlighted ? 100 : 1,
            },
            className,
        };
    });

    nodes.forEach((node: Node) => {
        const measuredHeight = nodeDimensions[node.id];
        localDagreGraph.setNode(node.id, { width: nodeWidth, height: measuredHeight ?? nodeHeight });
    });

    edges.forEach((edge: Edge) => {
        localDagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(localDagreGraph);

    const newNodes = nodes.map((node: Node) => {
        const nodeWithPosition = localDagreGraph.node(node.id);

        return ({
            ...node,
            targetPosition: isHorizontal ? 'left' : 'top',
            sourcePosition: isHorizontal ? 'right' : 'bottom',
            position: {
                x: nodeWithPosition.x - nodeWidth / 2,
                y: nodeWithPosition.y - ((nodeDimensions[node.id] ?? nodeHeight) / 2),
            },
        });
    });

    // @ts-expect-error is type declaration seem correct
    return { nodes: newNodes, edges };
};

interface DetailedFlowViewProps {
    serviceNodes: ServiceNodeType[];
    serviceRelations: ServiceRelation[];
    selectedNode: Node | null;
    outageService: string[];
    setOutageService: Dispatch<SetStateAction<string[]>>;
    startDate: string;
    endDate: string;
}

export default function DetailedFlowView({ serviceNodes, serviceRelations, selectedNode, outageService, setOutageService, startDate, endDate }: DetailedFlowViewProps) {
    const [nodes, setNodes] = useState<Node[]>([]);
    const [edges, setEdges] = useState<Edge[]>([]);
    const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string>>(new Set());
    const [nodeDimensions, setNodeDimensions] = useState<Record<string, number>>({});
    const reactFlowInstance = useRef<ReactFlowInstance | null>(null);
    const fitViewPendingRef = useRef(false);

    // First effect: Calculate highlighted nodes when selection changes
    useEffect(() => {
        if (selectedNode) {
            const tempNodes = serviceNodes.map(i => ({
                id: i.service_id,
                position: { x: 0, y: 0 },
                data: { service_id: i.service_id, label: i.label, type: i.service_type }
            })) as Node[];
            
            const tempEdges = serviceRelations.map(i => ({
                id: i.relation_id,
                source: i.source,
                target: i.target
            })) as Edge[];

            const downstreamDependents = get_downstream_dependents(selectedNode.id, tempNodes, tempEdges);
            const upstreamDependencies = get_upstream_dependencies(selectedNode.id, tempNodes, tempEdges);
            
            const highlightedIds = new Set<string>([
                selectedNode.id,
                ...downstreamDependents.map(node => node.id),
                ...upstreamDependencies.map(node => node.id)
            ]);
            
            setHighlightedNodeIds(highlightedIds);
        } else {
            setHighlightedNodeIds(new Set());
        }
    }, [selectedNode, serviceNodes, serviceRelations]);

    useEffect(() => {
        if (selectedNode) {
            const relatedNodeIds = new Set(highlightedNodeIds);
            const relatedNodes = serviceNodes.filter(n => relatedNodeIds.has(n.service_id));
            const relatedEdges = serviceRelations.filter(e => relatedNodeIds.has(e.source) && relatedNodeIds.has(e.target));

            const { nodes: layoutedNodes, edges: layoutedEdges } = getElementLayout(
                relatedNodes, 
                relatedEdges, 
                outageService, 
                setOutageService,
                nodeDimensions,
                highlightedNodeIds,
                selectedNode?.id || null,
                'LR',
                { startDate, endDate }
            );
            if (layoutedNodes) {
                const nodesWithCallbacks = layoutedNodes.map(node => ({
                    ...node,
                    data: {
                        ...node.data,
                        onHeightChange: (id: string, height: number) => {
                            setNodeDimensions(prev => {
                                if (prev[id] === height) {
                                    return prev;
                                }
                                return { ...prev, [id]: height };
                            });
                        }
                    }
                }));
                setNodes(nodesWithCallbacks);
            }

            if (layoutedEdges) {
                setEdges(layoutedEdges);
            }

            fitViewPendingRef.current = true;
        } else {
            setNodes([]);
            setEdges([]);
            fitViewPendingRef.current = false;
        }
    }, [serviceNodes, serviceRelations, outageService, highlightedNodeIds, selectedNode, setOutageService, nodeDimensions, startDate, endDate]);

    useEffect(() => {
        if (!selectedNode || nodes.length === 0) {
            fitViewPendingRef.current = false;
            return;
        }

        const instance = reactFlowInstance.current;
        if (!instance) {
            fitViewPendingRef.current = true;
            return;
        }

        fitViewPendingRef.current = false;
        const timer = window.setTimeout(() => {
            instance.fitView({
                padding: 0.1,
                duration: 300,
                includeHiddenNodes: false,
            });
        }, 0);

        return () => window.clearTimeout(timer);
    }, [selectedNode, nodes]);

    if (!selectedNode) {
        return (
            <div className="flex items-center justify-center h-full text-slate-500">
                <p>Select a service from the list to see its dependency graph.</p>
            </div>
        );
    }

    return (
        <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            connectionLineType={ConnectionLineType.SmoothStep}
            onInit={(instance) => {
                reactFlowInstance.current = instance;
                if (fitViewPendingRef.current && nodes.length > 0) {
                    instance.fitView({
                        padding: 0.1,
                        duration: 300,
                        includeHiddenNodes: false,
                    });
                    fitViewPendingRef.current = false;
                }
            }}
            fitView={false} // Disable automatic fitView since we're handling it manually
            minZoom={0.1}
            maxZoom={2}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
        >
            <Background />
            <Controls />
        </ReactFlow>
    );
}
