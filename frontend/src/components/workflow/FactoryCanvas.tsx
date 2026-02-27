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
import { FormStartNode } from './FormStartNode';
import type { FormStartNodeData } from './FormStartNode';
import { ApiStartNode } from './ApiStartNode';
import type { ApiStartNodeData } from './ApiStartNode';
import { FactoryNode, ConnectionDragContext } from './FactoryNode';
import type { FactoryNodeData } from './FactoryNode';
import { WarehouseNode } from './WarehouseNode';
import type { WarehouseNodeData } from './WarehouseNode';
import { SorterNode } from './SorterNode';
import type { SorterNodeData } from './SorterNode';
import { ApiCallNode } from './ApiCallNode';
import type { ApiCallNodeData } from './ApiCallNode';
import { UnpackerNode } from './UnpackerNode';
import type { UnpackerNodeData } from './UnpackerNode';
import { KnowledgeNode } from './KnowledgeNode';
import type { KnowledgeNodeData } from './KnowledgeNode';
import { MarkdownViewerNode } from './MarkdownViewerNode';
import type { MarkdownViewerNodeData } from './MarkdownViewerNode';
import type { AINode, Workflow } from '../../types';
import { DEF_TYPE, TRIGGER_TYPES, STATIC_OUTPUT_FIELDS, FIELD_MAPPING_PREFIX, EDGE_STYLE } from '../../constants/workflow';

// Union type for all node data
type AnyNodeData = FormStartNodeData | ApiStartNodeData | FactoryNodeData | WarehouseNodeData | SorterNodeData | ApiCallNodeData | UnpackerNodeData | KnowledgeNodeData | MarkdownViewerNodeData;

// Node types registry
const nodeTypes: NodeTypes = {
  formStartNode: FormStartNode,
  apiStartNode: ApiStartNode,
  factoryNode: FactoryNode,
  warehouseNode: WarehouseNode,
  sorterNode: SorterNode,
  apiCallNode: ApiCallNode,
  unpackerNode: UnpackerNode,
  knowledgeNode: KnowledgeNode,
  markdownViewerNode: MarkdownViewerNode,
};

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
  nodes: Node<AnyNodeData>[];
  edges: Edge[];
  viewport: Viewport;
}

export interface FieldDef {
  name: string;
  type: string;
}

export interface FactoryCanvasRef {
  getState: () => CanvasState;
  updateNodeData: (nodeId: string, dataUpdate: Partial<AnyNodeData>) => void;
  getOutputFields: (nodeId: string) => { own: FieldDef[]; passthrough: FieldDef[] };
  getInputFields: (nodeId: string) => FieldDef[];
}

interface FactoryCanvasProps {
  workflow: Workflow;
  aiNodes: AINode[];
  onNodesChange?: () => void;
  onNodeClick?: (node: Node<AnyNodeData>) => void;
  onNodeDoubleClick?: (node: Node<AnyNodeData>) => void;
  onEdgeClick?: (edgeId: string, edge: Edge) => void;
}

// Convert workflow to ReactFlow format
function workflowToReactFlow(workflow: Workflow): { nodes: Node<AnyNodeData>[]; edges: Edge[] } {
  const nodes: Node<AnyNodeData>[] = workflow.nodes.map((inst) => {
    const defType = inst.definitionType;
    const isFormStart = defType === DEF_TYPE.FORM_START;
    const isApiStart = defType === DEF_TYPE.API_START;
    const isResult = defType === DEF_TYPE.RESULT;
    const isSorter = defType === DEF_TYPE.SORTER;
    const isApiCall = defType === DEF_TYPE.API_CALL;
    const isUnpacker = defType === DEF_TYPE.UNPACKER;
    const isKnowledge = defType === DEF_TYPE.KNOWLEDGE;
    const isMarkdownViewer = defType === DEF_TYPE.MARKDOWN_VIEWER;

    let nodeType = 'factoryNode';
    if (isFormStart) nodeType = 'formStartNode';
    else if (isApiStart) nodeType = 'apiStartNode';
    else if (isResult) nodeType = 'warehouseNode';
    else if (isSorter) nodeType = 'sorterNode';
    else if (isApiCall) nodeType = 'apiCallNode';
    else if (isUnpacker) nodeType = 'unpackerNode';
    else if (isKnowledge) nodeType = 'knowledgeNode';
    else if (isMarkdownViewer) nodeType = 'markdownViewerNode';

    return {
      id: inst.id,
      type: nodeType,
      position: inst.position,
      data: {
        nodeId: inst.nodeId,
        instanceName: inst.name,
        inputMapping: inst.inputMapping,
        definitionType: inst.definitionType,
        aiNodeId: inst.aiNodeId,
        ...(isSorter ? { config: inst.config || { rules: [] } } : {}),
        ...(isApiCall ? { config: inst.config || {} } : {}),
        ...(isUnpacker ? { config: inst.config || {} } : {}),
        ...(isFormStart ? { config: inst.config || {} } : {}),
        ...(isApiStart ? { config: inst.config || {} } : {}),
        ...(isKnowledge ? { config: inst.config || {} } : {}),
        ...(isMarkdownViewer ? { config: inst.config || {} } : {}),
      },
    };
  });

  // Build a lookup to determine the default source handle per node type
  const nodeDefTypes = new Map(workflow.nodes.map((n) => [n.id, n.definitionType]));

  const edges: Edge[] = workflow.connections.map((conn) => {
    const srcDefType = nodeDefTypes.get(conn.sourceNodeId);
    // Sorter nodes use "default" handle; all other nodes use "output"
    const defaultSrcHandle = srcDefType === DEF_TYPE.SORTER ? 'default' : 'output';
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
export function canvasToSaveData(nodes: Node<AnyNodeData>[], edges: Edge[], viewport: Viewport) {
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
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
    })),
  };
}

function FactoryCanvasInner(
  { workflow, aiNodes, onNodesChange, onNodeClick, onNodeDoubleClick, onEdgeClick }: FactoryCanvasProps,
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
      if (defType === DEF_TYPE.API_CALL || defType === DEF_TYPE.API_START) {
        return STATIC_OUTPUT_FIELDS[DEF_TYPE.API_CALL].map((f) => f.name);
      }
      if (defType === DEF_TYPE.FORM_START) {
        const aiNodeId = (node.data.aiNodeId || node.data.nodeId) as string;
        const aiNode = aiNodes.find((n) => n.id === aiNodeId);
        return aiNode?.inputSchema?.properties
          ? Object.keys(aiNode.inputSchema.properties)
          : null;
      }
      if (defType === DEF_TYPE.KNOWLEDGE) {
        return STATIC_OUTPUT_FIELDS[DEF_TYPE.KNOWLEDGE].map((f) => f.name);
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
        } else if (dt === DEF_TYPE.API_CALL || dt === DEF_TYPE.API_START) {
          return [...STATIC_OUTPUT_FIELDS[DEF_TYPE.API_CALL]];
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
        } else if (dt === DEF_TYPE.KNOWLEDGE) {
          return [...STATIC_OUTPUT_FIELDS[DEF_TYPE.KNOWLEDGE]];
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
      onNodeClick?.(node as Node<AnyNodeData>);
    },
    [onNodeClick]
  );

  // Handle node double click
  const handleNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeDoubleClick?.(node as Node<AnyNodeData>);
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

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      // Check for starter node (form-start / api-start)
      const starterData = event.dataTransfer.getData('application/starternode');
      if (starterData) {
        const { definitionType } = JSON.parse(starterData);
        const id = genId();

        if (definitionType === DEF_TYPE.FORM_START) {
          const newNode: Node<FormStartNodeData> = {
            id,
            type: 'formStartNode',
            position,
            data: {
              nodeId: DEF_TYPE.FORM_START,
              instanceName: '폼 입력 시작',
              definitionType: DEF_TYPE.FORM_START,
              config: { mode: 'manual' },
            },
          };
          setNodes((nds) => [...nds, newNode]);
        } else if (definitionType === DEF_TYPE.API_START) {
          const newNode: Node<ApiStartNodeData> = {
            id,
            type: 'apiStartNode',
            position,
            data: {
              nodeId: DEF_TYPE.API_START,
              instanceName: 'API 호출 시작',
              definitionType: DEF_TYPE.API_START,
              config: { mode: 'manual' },
            },
          };
          setNodes((nds) => [...nds, newNode]);
        }

        onNodesChange?.();
        return;
      }

      // Check for system node (warehouse/sorter)
      const systemData = event.dataTransfer.getData('application/systemnode');
      if (systemData) {
        const { type, definitionType } = JSON.parse(systemData);
        const id = genId();

        if (type === DEF_TYPE.RESULT) {
          const newNode: Node<WarehouseNodeData> = {
            id,
            type: 'warehouseNode',
            position,
            data: {
              nodeId: DEF_TYPE.RESULT,
              instanceName: '창고',
              definitionType: DEF_TYPE.RESULT,
            },
          };
          setNodes((nds) => [...nds, newNode]);
        } else if (type === DEF_TYPE.SORTER) {
          const newNode: Node<SorterNodeData> = {
            id,
            type: 'sorterNode',
            position,
            data: {
              nodeId: DEF_TYPE.SORTER,
              instanceName: '분류기',
              definitionType: DEF_TYPE.SORTER,
              config: { rules: [] },
            },
          };
          setNodes((nds) => [...nds, newNode]);
        } else if (type === DEF_TYPE.MARKDOWN_VIEWER) {
          const newNode: Node<MarkdownViewerNodeData> = {
            id,
            type: 'markdownViewerNode',
            position,
            data: {
              nodeId: DEF_TYPE.MARKDOWN_VIEWER,
              instanceName: '마크다운 뷰어',
              definitionType: DEF_TYPE.MARKDOWN_VIEWER,
            },
          };
          setNodes((nds) => [...nds, newNode]);
        }

        // Suppress unused var (definitionType is used by sorter/result via type)
        void definitionType;

        onNodesChange?.();
        return;
      }

      // Check for knowledge node
      const knowledgeData = event.dataTransfer.getData('application/knowledgenode');
      if (knowledgeData) {
        const id = genId();
        const newNode: Node<KnowledgeNodeData> = {
          id,
          type: 'knowledgeNode',
          position,
          data: {
            nodeId: DEF_TYPE.KNOWLEDGE,
            instanceName: '지식 검색',
            definitionType: DEF_TYPE.KNOWLEDGE,
            config: { maxResults: 5 },
            inputMapping: {},
          },
        };
        setNodes((nds) => [...nds, newNode]);
        onNodesChange?.();
        return;
      }

      // Check for api-call node
      const apiCallData = event.dataTransfer.getData('application/apicallnode');
      if (apiCallData) {
        const id = genId();
        const newNode: Node<ApiCallNodeData> = {
          id,
          type: 'apiCallNode',
          position,
          data: {
            nodeId: DEF_TYPE.API_CALL,
            instanceName: 'API 호출기',
            definitionType: DEF_TYPE.API_CALL,
            config: {},
            inputMapping: {},
          },
        };
        setNodes((nds) => [...nds, newNode]);
        onNodesChange?.();
        return;
      }

      // Check for unpacker node
      const unpackerData = event.dataTransfer.getData('application/unpackernode');
      if (unpackerData) {
        const id = genId();
        const newNode: Node<UnpackerNodeData> = {
          id,
          type: 'unpackerNode',
          position,
          data: {
            nodeId: DEF_TYPE.UNPACKER,
            instanceName: '언패커',
            definitionType: DEF_TYPE.UNPACKER,
            config: {},
            inputMapping: {},
          },
        };
        setNodes((nds) => [...nds, newNode]);
        onNodesChange?.();
        return;
      }

      // Check for AI node (factory)
      const aiNodeData = event.dataTransfer.getData('application/ainode');
      if (aiNodeData) {
        const aiNode: AINode = JSON.parse(aiNodeData);
        const id = genId();

        const newNode: Node<FactoryNodeData> = {
          id,
          type: 'factoryNode',
          position,
          data: {
            nodeId: aiNode.id,
            instanceName: aiNode.name,
            definitionType: DEF_TYPE.AI_CUSTOM,
            aiNodeId: aiNode.id,
            inputMapping: {},
          },
        };
        setNodes((nds) => [...nds, newNode]);
        onNodesChange?.();
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
    (nodeId: string, dataUpdate: Partial<AnyNodeData>) => {
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

  // Enrich edges with mapping status data for ConveyorBeltEdge badges
  const enrichedEdges = useMemo(() => {
    return edges.map((edge) => {
      const targetFields = getInputFields(edge.target);
      const sourceOutput = getOutputFields(edge.source);

      // 타겟에 입력 필드가 없으면: 데이터가 그냥 통과하는 노드
      if (targetFields.length === 0) {
        // 소스에 출력이 있으면 데이터가 흐르고 있으므로 complete
        if (sourceOutput.own.length > 0 || sourceOutput.passthrough.length > 0) {
          return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'complete' as const } };
        }
        // 소스에도 출력이 없으면 noSchema
        return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'noSchema' as const } };
      }

      // 소스에 출력이 없으면 noSchema
      if (sourceOutput.own.length === 0 && sourceOutput.passthrough.length === 0) {
        return { ...edge, data: { ...(edge.data || {}), mappingStatus: 'noSchema' as const } };
      }

      const targetNode = nodes.find((n) => n.id === edge.target);
      const mapping = (targetNode?.data.inputMapping as Record<string, string>) || {};
      const mappedCount = targetFields.filter((f) => !!mapping[f.name]).length;
      const totalCount = targetFields.length;
      const status = mappedCount === 0 ? 'none' as const : mappedCount >= totalCount ? 'complete' as const : 'partial' as const;

      return { ...edge, data: { ...(edge.data || {}), mappingStatus: status, mappedCount, totalCount } };
    }) as Edge[];
  }, [edges, nodes, getInputFields, getOutputFields]);

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
          nodes={nodes}
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
            nodeColor={(n) => {
              if (n.type === 'formStartNode') return '#d97706';
              if (n.type === 'apiStartNode') return '#0d9488';
              if (n.type === 'warehouseNode') return '#059669';
              if (n.type === 'sorterNode') return '#7c3aed';
              if (n.type === 'apiCallNode') return '#0891b2';
              if (n.type === 'unpackerNode') return '#e11d48';
              if (n.type === 'knowledgeNode') return '#6366f1';
              if (n.type === 'markdownViewerNode') return '#6366f1';
              return '#475569';
            }}
            style={{ bottom: 20, right: 20, background: '#111827', borderRadius: 8 }}
          />
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1f2937" />
        </ReactFlow>
      </div>
    </ConnectionDragContext.Provider>
  );
}

export const FactoryCanvas = forwardRef(FactoryCanvasInner);
