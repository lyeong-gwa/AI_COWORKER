/**
 * 읽기 전용 워크플로우 뷰어 캔버스.
 *
 * - Phase 3a 개편 산출물. 드래그앤드롭/연결 편집/노드 이동 모두 제거.
 * - dagre 자동 레이아웃으로 position을 런타임 계산한다.
 * - 노드/엣지 렌더와 편집 인터랙션은 완전히 분리된 구조다.
 *
 * 이 컴포넌트는 workflow 데이터를 prop으로 받는 pure 컴포넌트이며,
 * 상위 페이지가 실행 버튼/사이드 패널/폼 등을 조립한다.
 */
import { useMemo, useState, useCallback } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
} from '@xyflow/react';
import type { Node, Edge, EdgeTypes, NodeTypes } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { ConveyorBeltEdge } from './ConveyorBeltEdge';
import { EdgeInspectorPanel } from './EdgeInspectorPanel';
import type { InspectedEdge } from './EdgeInspectorPanel';
import { nodeRegistry } from '../../nodes';
import type { Workflow, WorkflowNodeInstance } from '../../types';
import { EDGE_STYLE } from '../../constants/workflow';
import { autoLayout } from '../../utils/autoLayout';

// Re-export for pages that want to manage edge selection externally
export type { InspectedEdge };

// Node types from registry
const nodeTypes: NodeTypes = nodeRegistry.getNodeTypes();

// Conveyor belt edge types
const edgeTypes: EdgeTypes = {
  conveyorBelt: ConveyorBeltEdge,
};

const defaultEdgeOptions = {
  type: 'conveyorBelt' as const,
  animated: true,
  style: EDGE_STYLE,
};

// Legacy definition type normalization (과거 DB에 남아있는 'form' 타입을 'form-start'로 정규화)
const LEGACY_DEF_TYPE_MAP: Record<string, string> = {
  form: 'form-start',
};

interface NodeProgressEntry {
  status: string;
  output?: unknown;
  error?: string;
  startTime?: string;
  endTime?: string;
}

export interface WorkflowViewerCanvasProps {
  /** 표시할 워크플로우 */
  workflow: Workflow;
  /** 노드별 실행 진행 상태 (SSE 등으로 주입) */
  nodeProgress?: Record<string, NodeProgressEntry>;
  /** 노드 클릭 시 상위로 알림 (읽기 전용 사이드 패널 등에 활용) */
  onNodeClick?: (node: Node<any>) => void;
  /** 엣지 클릭 시 상위로 알림 (선택 사항) */
  onEdgeClick?: (edgeId: string, edge: Edge) => void;
  /** 캔버스 빈 영역 클릭 시 상위로 알림 (드로어 닫기 등) */
  onPaneClick?: () => void;
  /**
   * [P-7] 외부에서 제어하는 선택된 엣지 (controlled 모드).
   * 미전달 시 내부 state로 동작 (uncontrolled fallback).
   */
  selectedEdge?: InspectedEdge | null;
  /**
   * [P-7] 엣지 선택/해제 시 외부로 알림 (controlled 모드).
   * 미전달 시 내부 state로 동작 (uncontrolled fallback).
   */
  onEdgeSelect?: (edge: InspectedEdge | null) => void;
}

/**
 * Workflow 도메인 객체를 ReactFlow 노드/엣지로 변환.
 * position은 autoLayout이 채운다. 여기서는 임시 position (0,0)만 지정.
 */
function workflowToReactFlow(workflow: Workflow): { nodes: Node<any>[]; edges: Edge[] } {
  // 안정적 순서를 위해 orderIndex 기준 정렬 (없으면 원래 순서 유지)
  const sortedInstances = [...workflow.nodes].sort((a, b) => {
    const ai = a.orderIndex ?? 0;
    const bi = b.orderIndex ?? 0;
    return ai - bi;
  });

  const nodes: Node<any>[] = sortedInstances.map((inst: WorkflowNodeInstance) => {
    const defType = LEGACY_DEF_TYPE_MAP[inst.definitionType || ''] || inst.definitionType || '';
    const def = nodeRegistry.get(defType);
    const nodeType = def?.reactFlowType || 'factoryNode';

    const baseData: Record<string, unknown> = {
      nodeId: inst.nodeId,
      instanceName: inst.name,
      inputMapping: inst.inputMapping,
      definitionType: defType,
      aiNodeId: inst.aiNodeId,
    };

    if (def?.defaultData) {
      Object.assign(baseData, def.defaultData(inst));
    }

    return {
      id: inst.id,
      type: nodeType,
      position: { x: 0, y: 0 }, // autoLayout이 덮어씀
      data: baseData,
    };
  });

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

export function WorkflowViewerCanvas({
  workflow,
  nodeProgress,
  onNodeClick,
  onEdgeClick,
  onPaneClick,
  selectedEdge: selectedEdgeProp,
  onEdgeSelect,
}: WorkflowViewerCanvasProps) {
  // workflow identity가 바뀔 때만 재계산. 사용자 편집이 없으므로 memoization으로 충분.
  const laidOut = useMemo(() => {
    const { nodes, edges } = workflowToReactFlow(workflow);
    const positioned = autoLayout(nodes, edges, { direction: 'LR' });
    return { nodes: positioned, edges };
  }, [workflow]);

  // [P-7] 엣지 인스펙터 — controlled/uncontrolled 겸용.
  // onEdgeSelect 가 전달되면 controlled 모드 (Page가 state 관리),
  // 미전달 시 internal state 로 동작 (uncontrolled fallback).
  const isControlled = onEdgeSelect !== undefined;
  const [internalEdge, setInternalEdge] = useState<InspectedEdge | null>(null);
  const inspectedEdge = isControlled ? (selectedEdgeProp ?? null) : internalEdge;
  const setInspectedEdge = useCallback(
    (edge: InspectedEdge | null) => {
      if (isControlled) {
        onEdgeSelect!(edge);
      } else {
        setInternalEdge(edge);
      }
    },
    [isControlled, onEdgeSelect],
  );

  // 실행 상태로 노드 enrichment (SSE 이벤트로 주입된 nodeProgress 반영)
  const enrichedNodes = useMemo(() => {
    if (!nodeProgress || Object.keys(nodeProgress).length === 0) return laidOut.nodes;
    return laidOut.nodes.map((node) => {
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
  }, [laidOut.nodes, nodeProgress]);

  // 엣지는 실행 상태 뱃지만 enrichment (편집 상태는 계산하지 않음)
  const enrichedEdges = useMemo(() => {
    return laidOut.edges.map((edge) => {
      const sourceProgress = nodeProgress?.[edge.source];
      const targetProgress = nodeProgress?.[edge.target];

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

      return {
        ...edge,
        data: {
          ...(edge.data || {}),
          executionStatus,
          sourceOutput: sourceProgress?.output,
          // 편집 가능한 매핑 상태는 제거 — 읽기 전용이므로 뱃지는 'noSchema'로 통일
          mappingStatus: 'noSchema' as const,
        },
      };
    }) as Edge[];
  }, [laidOut.edges, nodeProgress]);

  // 노드 클릭 -> 상위 알림
  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node as Node<any>);
    },
    [onNodeClick]
  );

  // 엣지 클릭: 실행 출력이 있으면 인스펙터 열기 (read-only 조회)
  const handleEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      onEdgeClick?.(edge.id, edge);
      const edgeData = edge.data as { sourceOutput?: unknown } | undefined;
      if (edgeData?.sourceOutput != null) {
        setInspectedEdge({
          edgeId: edge.id,
          sourceNodeId: edge.source,
          targetNodeId: edge.target,
          sourceOutput: edgeData.sourceOutput,
        });
      }
    },
    [onEdgeClick, setInspectedEdge]
  );

  return (
    <div className="flex-1 h-full relative">
      <ReactFlow
        nodes={enrichedNodes}
        edges={enrichedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        // ── 편집 차단 ──
        nodesDraggable={false}
        nodesConnectable={false}
        edgesReconnectable={false}
        elementsSelectable={true}
        deleteKeyCode={null}
        // ── 이벤트 ──
        onNodeClick={handleNodeClick}
        onEdgeClick={handleEdgeClick}
        onPaneClick={onPaneClick ? () => onPaneClick() : undefined}
        fitView
        className="bg-gray-950"
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
      <EdgeInspectorPanel edge={inspectedEdge} onClose={() => setInspectedEdge(null)} />
    </div>
  );
}
