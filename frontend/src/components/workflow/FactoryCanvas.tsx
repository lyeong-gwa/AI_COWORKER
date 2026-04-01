import { useCallback, useRef, useMemo, useEffect, useState, forwardRef, useImperativeHandle } from 'react';
import type { DragEvent } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  useReactFlow,
} from '@xyflow/react';
import type { Connection, Node, Edge, EdgeTypes, NodeTypes, Viewport, OnConnectStartParams } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { ConveyorBeltEdge } from './ConveyorBeltEdge';
import { ConnectionDragContext } from './FactoryNode';
import { nodeRegistry } from '../../nodes';
import type { AINode, Workflow } from '../../types';
import { DEF_TYPE, TRIGGER_TYPES, FIELD_MAPPING_PREFIX, EDGE_STYLE } from '../../constants/workflow';

// Node types from registry
const nodeTypes: NodeTypes = nodeRegistry.getNodeTypes();

// Conveyor belt edge types
const edgeTypes: EdgeTypes = {
  conveyorBelt: ConveyorBeltEdge,
};

// Conveyor belt edge style
const defaultEdgeOptions = {
  type: 'conveyorBelt' as const,
  animated: true,
  style: EDGE_STYLE,
};

export interface CanvasState {
  nodes: Node<any>[];
  edges: Edge[];
  viewport: Viewport;
}

export interface FieldDef {
  name: string;
  type: string;
}

export interface FactoryCanvasRef {
  getState: () => CanvasState;
  updateNodeData: (nodeId: string, dataUpdate: Partial<Record<string, unknown>>) => void;
  getOutputFields: (nodeId: string) => { own: FieldDef[]; passthrough: FieldDef[] };
  getInputFields: (nodeId: string) => FieldDef[];
}

interface NodeProgressEntry {
  status: string;
  output?: unknown;
  error?: string;
  startTime?: string;
  endTime?: string;
}

interface FactoryCanvasProps {
  workflow: Workflow;
  aiNodes: AINode[];
  nodeProgress?: Record<string, NodeProgressEntry>;
  onNodesChange?: () => void;
  onNodeClick?: (node: Node<any>) => void;
  onNodeDoubleClick?: (node: Node<any>) => void;
  onEdgeClick?: (edgeId: string, edge: Edge) => void;
}

// Convert workflow to ReactFlow format
// Legacy definition type normalization
const LEGACY_DEF_TYPE_MAP: Record<string, string> = {
  'form': 'form-start',
};

function workflowToReactFlow(workflow: Workflow): { nodes: Node<any>[]; edges: Edge[] } {
  const nodes: Node<any>[] = workflow.nodes.map((inst) => {
    const defType = LEGACY_DEF_TYPE_MAP[inst.definitionType || ''] || inst.definitionType || '';
    const def = nodeRegistry.get(defType);
    const nodeType = def?.reactFlowType || 'factoryNode';

    // 기본 데이터
    const baseData: any = {
      nodeId: inst.nodeId,
      instanceName: inst.name,
      inputMapping: inst.inputMapping,
      definitionType: defType,
      aiNodeId: inst.aiNodeId,
    };

    // 정의별 추가 데이터 (config 등)
    if (def?.defaultData) {
      Object.assign(baseData, def.defaultData(inst));
    }

    return {
      id: inst.id,
      type: nodeType,
      position: inst.position,
      data: baseData,
    };
  });

  // Build a lookup to determine the default source handle per node type
  const nodeDefTypes = new Map(workflow.nodes.map((n) => [n.id, n.definitionType]));

  const edges: Edge[] = workflow.connections.map((conn) => {
    const srcDefType = nodeDefTypes.get(conn.sourceNodeId) || '';
    const defaultSrcHandle = nodeRegistry.getDefaultSourceHandle(srcDefType);
    return {
      id: conn.id,
      source: conn.sourceNodeId,
      sourceHandle: conn.sourceHandle || defaultSrcHandle,
      target: conn.targetNodeId,
      targetHandle: conn.targetHandle || 'input',
      ...defaultEdgeOptions,
    };
  });

  return { nodes, edges };
}

// Convert ReactFlow to save data format
export function canvasToSaveData(nodes: Node<any>[], edges: Edge[], viewport: Viewport) {
  return {
    viewport: { x: viewport.x, y: viewport.y, zoom: viewport.zoom },
    nodes: nodes.map((n) => ({
      id: n.id,
      nodeId: n.data.nodeId,
      definitionType: n.data.definitionType || DEF_TYPE.AI_CUSTOM,
      aiNodeId: n.data.aiNodeId as string | undefined,
      name: n.data.instanceName,
      position: { x: n.position.x, y: n.position.y },
      config: (n.data as any).config || {},
      configOverrides: {},
      inputMapping: n.data.inputMapping || {},
    })),
    connections: edges.map((e) => ({
      id: e.id,
      sourceNodeId: e.source,
      targetNodeId: e.target,
      sourceHandle: e.sourceHandle ?? undefined,
      targetHandle: e.targetHandle ?? undefined,
    })),
  };
}

function FactoryCanvasInner(
  { workflow, aiNodes, nodeProgress, onNodesChange, onNodeClick, onNodeDoubleClick, onEdgeClick }: FactoryCanvasProps,
  ref: React.Ref<FactoryCanvasRef>
) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition, getViewport } = useReactFlow();
  const idCounterRef = useRef(0);

  // Initialize from workflow
  const initialData = useMemo(() => workflowToReactFlow(workflow), [workflow]);
  const [nodes, setNodes, onNodesStateChange] = useNodesState(initialData.nodes);
  const [edges, setEdges, onEdgesStateChange] = useEdgesState(initialData.edges);

  // Connection validation state
  const [connectionDragState, setConnectionDragState] = useState<{ invalidTargetIds: Set<string> } | null>(null);

  // Sync only when workflow identity changes (initial load or page navigation)
  const lastSyncedIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (workflow.id === lastSyncedIdRef.current) return;
    lastSyncedIdRef.current = workflow.id;
    const data = workflowToReactFlow(workflow);
    setNodes(data.nodes);
    setEdges(data.edges);
  }, [workflow]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fill empty inputMappings for existing trigger→factory connections on load
  useEffect(() => {
    if (!aiNodes.length) return;
    let changed = false;

    setNodes((nds) => {
      const edgeList = edges;
      const updated = nds.map((node) => {
        const defType = node.data.definitionType as string | undefined;
        if (defType !== DEF_TYPE.AI_CUSTOM) return node;

        // Check if this factory has an incoming edge from a start node
        const hasTriggerSource = edgeList.some((e) => {
          if (e.target !== node.id) return false;
          const srcNode = nds.find((n) => n.id === e.source);
          const srcDef = srcNode?.data.definitionType as string | undefined;
          return srcDef != null && TRIGGER_TYPES.has(srcDef);
        });
        if (!hasTriggerSource) return node;

        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        if (!aiNode?.inputSchema?.properties) return node;

        const currentMapping = (node.data.inputMapping as Record<string, string>) || {};
        const newMapping = { ...currentMapping };
        let nodeChanged = false;

        for (const field of Object.keys(aiNode.inputSchema.properties)) {
          if (!newMapping[field]) {
            newMapping[field] = `${FIELD_MAPPING_PREFIX}${field}`;
            nodeChanged = true;
          }
        }

        if (nodeChanged) {
          changed = true;
          return { ...node, data: { ...node.data, inputMapping: newMapping } };
        }
        return node;
      });

      return changed ? updated : nds;
    });

    if (changed) onNodesChange?.();
  }, [aiNodes]); // eslint-disable-line react-hooks/exhaustive-deps

  const genId = useCallback(() => {
    idCounterRef.current += 1;
    return `fn-${Date.now()}-${idCounterRef.current}`;
  }, []);

  // 노드의 OWN output 키를 반환 (null = 제한 없음, 아무거나 연결 가능)
  const getOutputKeys = useCallback(
    (nodeId: string): string[] | null => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return null;
      const defType = node.data.definitionType as string | undefined;

      if (defType === DEF_TYPE.AI_CUSTOM) {
        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        return aiNode?.outputSchema?.properties
          ? Object.keys(aiNode.outputSchema.properties)
          : null;
      }
      // 레지스트리의 고정 출력 필드 확인
      const staticFields = nodeRegistry.getStaticOutputFields(defType as string);
      if (staticFields) {
        return staticFields.map(f => f.name);
      }
      if (defType === DEF_TYPE.FORM_START) {
        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        return aiNode?.inputSchema?.properties
          ? Object.keys(aiNode.inputSchema.properties)
          : null;
      }
      // result, markdown-viewer, sorter, unpacker, 기타: 제한 없음
      return null;
    },
    [nodes, aiNodes]
  );

  // 노드가 업스트림에서 필요로 하는 필드 키를 반환 (null = 아무거나 수용)
  const getNeededInputKeys = useCallback(
    (nodeId: string): string[] | null => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return null;

      // input_mapping이 있으면: $.xxx 에서 최상위 필드명 추출
      const mapping = node.data.inputMapping as Record<string, string> | undefined;
      if (mapping && Object.keys(mapping).length > 0) {
        const neededFields: string[] = [];
        for (const sourceExpr of Object.values(mapping)) {
          if (typeof sourceExpr === 'string' && sourceExpr.startsWith(FIELD_MAPPING_PREFIX)) {
            const topField = sourceExpr.slice(FIELD_MAPPING_PREFIX.length).split('.')[0];
            if (topField && !neededFields.includes(topField)) {
              neededFields.push(topField);
            }
          }
        }
        return neededFields.length > 0 ? neededFields : null;
      }

      // input_mapping이 없으면: AI 노드의 inputSchema 사용
      const defType = node.data.definitionType as string | undefined;
      if (defType === DEF_TYPE.AI_CUSTOM) {
        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        return aiNode?.inputSchema?.properties
          ? Object.keys(aiNode.inputSchema.properties)
          : null;
      }

      return null; // 그 외 노드: 아무거나 수용
    },
    [nodes, aiNodes]
  );

  // Handle new connections (conveyor belts)
  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            id: `edge-${genId()}`,
            ...defaultEdgeOptions,
          },
          eds
        )
      );

      // Auto-set inputMapping: OWN output 이름 일치만 자동매핑 (passthrough 제외)
      if (params.source && params.target) {
        const sourceNode = nodes.find((n) => n.id === params.source);
        const targetNode = nodes.find((n) => n.id === params.target);
        if (sourceNode && targetNode) {
          // source OWN output 키 계산 (getOutputKeys 재사용)
          const srcOwnKeys = getOutputKeys(params.source);

          // target input 필드 계산 (getNeededInputKeys 또는 inputMapping/inputSchema)
          const tgtDef = targetNode.data.definitionType as string | undefined;
          let tgtKeys: string[] = [];
          if (tgtDef === DEF_TYPE.AI_CUSTOM) {
            const aid = (targetNode.data.aiNodeId || targetNode.data.nodeId) as string;
            const an = aiNodes.find((n) => n.id === aid);
            tgtKeys = an?.inputSchema?.properties ? Object.keys(an.inputSchema.properties) : [];
          } else {
            const mp = targetNode.data.inputMapping as Record<string, string> | undefined;
            tgtKeys = mp ? Object.keys(mp) : [];
          }

          if (srcOwnKeys && tgtKeys.length > 0) {
            const currentMapping = (targetNode.data.inputMapping as Record<string, string>) || {};
            const newMapping = { ...currentMapping };
            let changed = false;
            for (const field of tgtKeys) {
              if (!newMapping[field] && srcOwnKeys.includes(field)) {
                newMapping[field] = `${FIELD_MAPPING_PREFIX}${field}`;
                changed = true;
              }
            }
            if (changed) {
              setNodes((nds) =>
                nds.map((n) =>
                  n.id === params.target
                    ? { ...n, data: { ...n.data, inputMapping: newMapping } }
                    : n
                )
              );
            }
          }
        }
      }

      onNodesChange?.();
    },
    [setEdges, setNodes, nodes, aiNodes, genId, onNodesChange, getOutputKeys]
  );

  // 노드의 OWN output 필드 목록 (이름+타입) + passthrough 필드 반환
  const getOutputFields = useCallback(
    (nodeId: string): { own: FieldDef[]; passthrough: FieldDef[] } => {
      // Helper: 특정 노드의 OWN output 필드 계산
      function computeOwnOutput(nId: string): FieldDef[] {
        const nd = nodes.find((n) => n.id === nId);
        if (!nd) return [];
        const dt = nd.data.definitionType as string | undefined;

        if (dt === DEF_TYPE.AI_CUSTOM) {
          const aid = (nd.data.aiNodeId || nd.data.nodeId) as string;
          const aiN = aiNodes.find((a) => a.id === aid);
          if (aiN?.outputSchema?.properties) {
            return Object.entries(aiN.outputSchema.properties).map(([k, v]) => ({ name: k, type: v.type }));
          }
        } else if (dt === DEF_TYPE.FORM_START) {
          const aid = (nd.data.aiNodeId || nd.data.nodeId) as string;
          const aiN = aiNodes.find((a) => a.id === aid);
          if (aiN?.inputSchema?.properties) {
            return Object.entries(aiN.inputSchema.properties).map(([k, v]) => ({ name: k, type: v.type }));
          }
          // BFS fallback: downstream에서 첫 ai-custom 노드의 inputSchema 탐색
          const visited = new Set<string>();
          const queue = [nId];
          while (queue.length > 0) {
            const current = queue.shift()!;
            if (visited.has(current)) continue;
            visited.add(current);
            const outEdges = edges.filter((e) => e.source === current);
            for (const oe of outEdges) {
              const tgtNode = nodes.find((n) => n.id === oe.target);
              if (!tgtNode) continue;
              if ((tgtNode.data.definitionType as string) === DEF_TYPE.AI_CUSTOM) {
                const tgtAiId = (tgtNode.data.aiNodeId || tgtNode.data.nodeId) as string;
                const tgtAiNode = aiNodes.find((a) => a.id === tgtAiId);
                if (tgtAiNode?.inputSchema?.properties) {
                  return Object.entries(tgtAiNode.inputSchema.properties).map(([k, v]) => ({ name: k, type: v.type }));
                }
              }
              queue.push(oe.target);
            }
          }
        } else {
          // 레지스트리의 고정 출력 필드 확인
          const regStaticFields = nodeRegistry.getStaticOutputFields(dt as string);
          if (regStaticFields) {
            return [...regStaticFields];
          }
        }
        return [];
      }

      // Helper: 노드의 effective output (own이 있으면 own, 없으면 업스트림 재귀 탐색)
      function collectEffectiveOutput(nId: string, visited: Set<string>): FieldDef[] {
        if (visited.has(nId)) return [];
        visited.add(nId);

        const own = computeOwnOutput(nId);
        if (own.length > 0) return own;

        // Pass-through 노드: 업스트림의 effective output을 수집
        const result: FieldDef[] = [];
        const inEdges = edges.filter((e) => e.target === nId);
        for (const ie of inEdges) {
          const upstream = collectEffectiveOutput(ie.source, visited);
          for (const f of upstream) {
            if (!result.some((r) => r.name === f.name)) {
              result.push(f);
            }
          }
        }
        return result;
      }

      const own = computeOwnOutput(nodeId);

      // Passthrough: 업스트림 엣지를 재귀적으로 따라 수집
      const passthrough: FieldDef[] = [];
      const ownNames = new Set(own.map((f) => f.name));
      const incomingEdges = edges.filter((e) => e.target === nodeId);
      for (const edge of incomingEdges) {
        const srcEffective = collectEffectiveOutput(edge.source, new Set([nodeId]));
        for (const f of srcEffective) {
          if (!ownNames.has(f.name) && !passthrough.some((p) => p.name === f.name)) {
            passthrough.push(f);
          }
        }
      }

      return { own, passthrough };
    },
    [nodes, aiNodes, edges]
  );

  // 노드의 입력 필드 목록 (이름+타입) 반환
  const getInputFields = useCallback(
    (nodeId: string): FieldDef[] => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return [];
      const defType = node.data.definitionType as string | undefined;

      // ai-custom: inputSchema 사용
      if (defType === DEF_TYPE.AI_CUSTOM) {
        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        if (aiNode?.inputSchema?.properties) {
          return Object.entries(aiNode.inputSchema.properties).map(([k, v]) => ({ name: k, type: v.type }));
        }
      }

      // api-call: inputMapping 키 또는 빈 배열
      if (defType === DEF_TYPE.API_CALL) {
        const mapping = node.data.inputMapping as Record<string, string> | undefined;
        if (mapping) {
          return Object.keys(mapping).map((k) => ({ name: k, type: 'string' }));
        }
      }

      // 기타: inputMapping이 있으면 키 목록
      const mapping = node.data.inputMapping as Record<string, string> | undefined;
      if (mapping && Object.keys(mapping).length > 0) {
        return Object.keys(mapping).map((k) => ({ name: k, type: 'string' }));
      }

      return [];
    },
    [nodes, aiNodes]
  );

  // Check if connecting sourceId → targetId is valid
  // _passthrough 모델: source의 OWN output 키가 target의 필요 필드와 최소 1개 이상 겹쳐야 유효
  const checkConnectionValid = useCallback(
    (sourceId: string, targetId: string): boolean => {
      if (sourceId === targetId) return false;

      const sourceOutputKeys = getOutputKeys(sourceId);
      const targetNeededKeys = getNeededInputKeys(targetId);

      // 어느 한쪽이 null이면 (스키마 없음) 연결 허용
      if (!sourceOutputKeys || !targetNeededKeys) return true;

      // source output과 target needed 사이에 겹치는 키가 있으면 유효
      return sourceOutputKeys.some((key) => targetNeededKeys.includes(key));
    },
    [getOutputKeys, getNeededInputKeys]
  );

  // Validate connection (used by ReactFlow to block invalid connections)
  const isValidConnection = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return false;
      return checkConnectionValid(connection.source, connection.target);
    },
    [checkConnectionValid]
  );

  // Track connection drag for visual feedback
  const onConnectStart = useCallback(
    (_: React.MouseEvent | React.TouchEvent, params: OnConnectStartParams) => {
      if (!params.nodeId || params.handleType !== 'source') {
        setConnectionDragState(null);
        return;
      }

      // 스키마 기반: 연결 불가능한 타겟 노드를 빨간색으로 표시
      const sourceId = params.nodeId;
      const invalidTargetIds = new Set<string>();
      for (const n of nodes) {
        if (n.id === sourceId || !checkConnectionValid(sourceId, n.id)) {
          invalidTargetIds.add(n.id);
        }
      }
      setConnectionDragState({ invalidTargetIds });
    },
    [nodes, checkConnectionValid]
  );

  const onConnectEnd = useCallback(() => {
    setConnectionDragState(null);
  }, []);

  // Handle node position changes
  const handleNodesChange: typeof onNodesStateChange = useCallback(
    (changes) => {
      onNodesStateChange(changes);
      // Check if any position changed
      if (changes.some((c) => c.type === 'position' && 'position' in c && c.position)) {
        onNodesChange?.();
      }
    },
    [onNodesStateChange, onNodesChange]
  );

  // Handle edge changes
  const handleEdgesChange: typeof onEdgesStateChange = useCallback(
    (changes) => {
      onEdgesStateChange(changes);
      if (changes.some((c) => c.type === 'remove')) {
        onNodesChange?.();
      }
    },
    [onEdgesStateChange, onNodesChange]
  );

  // Handle node click
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node as Node<any>);
    },
    [onNodeClick]
  );

  // Handle node double click
  const handleNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeDoubleClick?.(node as Node<any>);
    },
    [onNodeDoubleClick]
  );

  // Drag and drop handler
  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });

      // 1. AI 노드 (application/ainode)
      const aiNodeData = event.dataTransfer.getData('application/ainode');
      if (aiNodeData) {
        const aiNode = JSON.parse(aiNodeData);
        const def = nodeRegistry.get(DEF_TYPE.AI_CUSTOM);
        if (def) {
          const newNode = def.createNodeData(genId(), position, { aiNode });
          setNodes((nds) => [...nds, newNode]);
          onNodesChange?.();
        }
        return;
      }

      // 2. 시스템/스타터 노드 -- 모든 dragType을 시도
      for (const def of nodeRegistry.all()) {
        if (!def.palette?.dragType) continue;
        const data = event.dataTransfer.getData(def.palette.dragType);
        if (!data) continue;

        const parsed = JSON.parse(data);
        const targetDefType = parsed.type || parsed.definitionType;
        if (targetDefType !== def.defType) continue;

        const newNode = def.createNodeData(genId(), position);
        setNodes((nds) => [...nds, newNode]);
        onNodesChange?.();
        return;
      }
    },
    [screenToFlowPosition, setNodes, genId, onNodesChange]
  );

  // Delete selected nodes AND edges on Delete/Backspace
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const target = e.target as HTMLElement;
        if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;

        let changed = false;

        // Delete selected edges
        const selectedEdgeIds = edges.filter((ed) => ed.selected).map((ed) => ed.id);
        if (selectedEdgeIds.length > 0) {
          setEdges((eds) => eds.filter((ed) => !selectedEdgeIds.includes(ed.id)));
          changed = true;
        }

        // Delete selected nodes (and their connected edges)
        const selectedNodeIds = nodes.filter((n) => n.selected).map((n) => n.id);
        if (selectedNodeIds.length > 0) {
          setNodes((nds) => nds.filter((n) => !selectedNodeIds.includes(n.id)));
          setEdges((eds) =>
            eds.filter((ed) => !selectedNodeIds.includes(ed.source) && !selectedNodeIds.includes(ed.target))
          );
          changed = true;
        }

        if (changed) onNodesChange?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [nodes, edges, setNodes, setEdges, onNodesChange]);

  // Update node data
  const updateNodeData = useCallback(
    (nodeId: string, dataUpdate: Partial<Record<string, unknown>>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId ? { ...n, data: { ...n.data, ...dataUpdate } } : n
        )
      );
      onNodesChange?.();
    },
    [setNodes, onNodesChange]
  );

  // Expose state to parent
  useImperativeHandle(ref, () => ({
    getState: () => ({
      nodes,
      edges,
      viewport: getViewport(),
    }),
    updateNodeData,
    getOutputFields,
    getInputFields,
  }));

  // Enrich nodes with execution status from nodeProgress
  const enrichedNodes = useMemo(() => {
    if (!nodeProgress || Object.keys(nodeProgress).length === 0) return nodes;
    return nodes.map((node) => {
      const progress = nodeProgress[node.id];
      if (!progress) return node;
      return {
        ...node,
        data: {
          ...node.data,
          _executionStatus: progress.status,
          _executionOutput: progress.output,
          _executionError: progress.error,
        },
      };
    });
  }, [nodes, nodeProgress]);

  // Enrich edges with mapping status data for ConveyorBeltEdge badges
  const enrichedEdges = useMemo(() => {
    return edges.map((edge) => {
      const targetFields = getInputFields(edge.target);
      const sourceOutput = getOutputFields(edge.source);

      // 소스 노드 실행 상태/출력
      const sourceProgress = nodeProgress?.[edge.source];
      const targetProgress = nodeProgress?.[edge.target];

      // 엣지 실행 상태 결정
      let executionStatus: 'idle' | 'running' | 'completed' | 'failed' = 'idle';
      if (sourceProgress?.status === 'completed' && targetProgress?.status === 'running') {
        executionStatus = 'running';
      } else if (sourceProgress?.status === 'completed' && targetProgress?.status === 'completed') {
        executionStatus = 'completed';
      } else if (sourceProgress?.status === 'failed' || targetProgress?.status === 'failed') {
        executionStatus = 'failed';
      } else if (sourceProgress?.status === 'running') {
        executionStatus = 'running';
      }

      // 타겟에 입력 필드가 없으면: 데이터가 그냥 통과하는 노드
      if (targetFields.length === 0) {
        // 소스에 출력이 있으면 데이터가 흐르고 있으므로 complete
        if (sourceOutput.own.length > 0 || sourceOutput.passthrough.length > 0) {
          return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'complete' as const, executionStatus, sourceOutput: sourceProgress?.output } };
        }
        // 소스에도 출력이 없으면 noSchema
        return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'noSchema' as const, executionStatus, sourceOutput: sourceProgress?.output } };
      }

      // 소스에 출력이 없으면 noSchema
      if (sourceOutput.own.length === 0 && sourceOutput.passthrough.length === 0) {
        return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'noSchema' as const, executionStatus, sourceOutput: sourceProgress?.output } };
      }

      const targetNode = nodes.find((n) => n.id === edge.target);
      const mapping = (targetNode?.data.inputMapping as Record<string, string>) || {};
      const mappedCount = targetFields.filter((f) => !!mapping[f.name]).length;
      const totalCount = targetFields.length;
      const status = mappedCount === 0 ? 'none' as const : mappedCount >= totalCount ? 'complete' as const : 'partial' as const;

      return { ...edge, data: { ...(edge.data || {}), mappingStatus: status, mappedCount, totalCount, executionStatus, sourceOutput: sourceProgress?.output } };
    }) as Edge[];
  }, [edges, nodes, getInputFields, getOutputFields, nodeProgress]);

  // Handle edge click
  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onEdgeClick?.(edge.id, edge);
    },
    [onEdgeClick]
  );

  return (
    <ConnectionDragContext.Provider value={connectionDragState}>
      <div ref={reactFlowWrapper} className="flex-1 h-full">
        <ReactFlow
          nodes={enrichedNodes}
          edges={enrichedEdges}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onConnectStart={onConnectStart as any}
          onConnectEnd={onConnectEnd}
          isValidConnection={isValidConnection as any}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onEdgeClick={handleEdgeClick}
          onDragOver={onDragOver}
          onDrop={onDrop}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={defaultEdgeOptions}
          fitView
          snapToGrid
          snapGrid={[15, 15]}
          className="bg-gray-950"
          deleteKeyCode={null}
        >
          <Controls
            position="bottom-left"
            style={{ bottom: 20, left: 20 }}
            showInteractive={false}
          />
          <MiniMap
            nodeStrokeColor="#333"
            nodeColor={(n) => nodeRegistry.getMinimapColor(n.type || '')}
            style={{ bottom: 20, right: 20, background: '#111827', borderRadius: 8 }}
          />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1f2937" />
        </ReactFlow>
      </div>
    </ConnectionDragContext.Provider>
  );
}

export const FactoryCanvas = forwardRef(FactoryCanvasInner);
