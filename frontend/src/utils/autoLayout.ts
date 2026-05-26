/**
 * 자동 레이아웃 유틸 (dagre 기반)
 *
 * - position/viewport 데이터는 DB/API에 저장되지 않는다.
 * - 워크플로우 뷰어는 마운트 시 이 함수를 호출하여 노드 position을 런타임 계산한다.
 * - 사용자 편집이 없으므로 재호출은 workflow identity가 바뀔 때만 발생한다.
 */

import * as dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/react';

export interface AutoLayoutOptions {
  /** 레이아웃 방향 (Left-to-Right 또는 Top-to-Bottom) */
  direction?: 'LR' | 'TB';
  /** 노드 크기 추정치 (실제 렌더 크기에 맞춰 조정) */
  nodeWidth?: number;
  nodeHeight?: number;
  /** 동일 rank 노드 간 간격 */
  nodeSep?: number;
  /** rank(레벨) 간 간격 */
  rankSep?: number;
}

/**
 * dagre를 사용하여 ReactFlow 노드의 position을 계산한다.
 *
 * - 엣지가 없거나 노드가 비어있어도 안전하게 동작한다.
 * - 반환은 새 배열이며, 원본 nodes 배열은 변경하지 않는다.
 * - position 좌표는 ReactFlow 규약(top-left anchor)에 맞게 보정된다.
 */
export function autoLayout<TNode extends Node>(
  nodes: TNode[],
  edges: Edge[],
  opts: AutoLayoutOptions = {}
): TNode[] {
  const {
    direction = 'LR',
    nodeWidth = 240,
    nodeHeight = 120,
    nodeSep = 80,
    rankSep = 120,
  } = opts;

  // 빈 입력 방어
  if (nodes.length === 0) return nodes;

  const g = new dagre.graphlib.Graph<Record<string, unknown>, { width: number; height: number; x: number; y: number }, Record<string, unknown>>();
  g.setGraph({ rankdir: direction, nodesep: nodeSep, ranksep: rankSep });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    g.setNode(n.id, { width: nodeWidth, height: nodeHeight, x: 0, y: 0 });
  }

  // 유효한 엣지만 추가 (source/target가 노드 집합 안에 있어야 함)
  const nodeIds = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }

  dagre.layout(g);

  return nodes.map((n) => {
    const pos = g.node(n.id);
    if (!pos) return n;
    // dagre는 중심 좌표를 반환하므로 top-left로 보정
    return {
      ...n,
      position: {
        x: pos.x - nodeWidth / 2,
        y: pos.y - nodeHeight / 2,
      },
    };
  });
}
