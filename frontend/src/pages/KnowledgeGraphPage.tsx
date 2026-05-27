/**
 * KnowledgeGraphPage (`/knowledge/graph`)
 *
 * Phase 2:
 *   - 노드 색상 = community 기준 (6색 팔레트 결정적 매핑)
 *   - 노드 테두리 = service 기준
 *   - 노드 크기 = godScore × 8 + 4
 *   - 엣지 시각 차별화: explicit 실선 cyan / implicit 점선 회색 / crossService 보라 / broken 빨강
 *   - 엣지 클릭 → EdgeInspectorPanel 우측 드로어
 *   - 범례: 엣지 종류 + Community 목록 + Top God Nodes
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { knowledgeApi } from '../services/api';
import type { KnowledgeGraphNode, KnowledgeGraphEdge, KnowledgeService, PageType, KnowledgeCommunity } from '../types';
import { getServiceColor } from '../components/knowledge/ServiceBadge';
import { EdgeInspectorPanel } from '../components/knowledge/EdgeInspectorPanel';

// ─── page_type 필터용 색상 ─────────────────────────────────────────────────────

const PAGE_TYPE_COLOR: Record<PageType | string, string> = {
  Summary: '#3b82f6',
  Entity: '#10b981',
  Concept: '#8b5cf6',
  Comparison: '#f59e0b',
  Synthesis: '#f43f5e',
};

const PAGE_TYPES: PageType[] = ['Summary', 'Entity', 'Concept', 'Comparison', 'Synthesis'];

// ─── Community 색상 팔레트 (6색, community.id 기준 결정적 매핑) ─────────────────

const COMMUNITY_PALETTE = [
  '#0ea5e9', // sky-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#f43f5e', // rose-500
  '#8b5cf6', // violet-500
  '#f97316', // orange-500
];

function getCommunityColor(communityId: number): string {
  return COMMUNITY_PALETTE[((communityId % COMMUNITY_PALETTE.length) + COMMUNITY_PALETTE.length) % COMMUNITY_PALETTE.length];
}

// ─── Force layout 타입 ───────────────────────────────────────────────────────

interface LayoutNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  node: KnowledgeGraphNode;
}

// ─── 단순 force-directed 레이아웃 (Fruchterman–Reingold, 80 반복) ───────────

function buildLayout(
  nodes: KnowledgeGraphNode[],
  edges: KnowledgeGraphEdge[],
  width: number,
  height: number,
): LayoutNode[] {
  const ITERATIONS = 80;
  const K = Math.sqrt((width * height) / Math.max(nodes.length, 1));

  const layout: LayoutNode[] = nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const r = Math.min(width, height) * 0.35;
    // 노드 크기: godScore × 8 + 4 (4px ~ 12px)
    const godScore = node.godScore ?? 0;
    return {
      id: node.id,
      x: width / 2 + r * Math.cos(angle),
      y: height / 2 + r * Math.sin(angle),
      vx: 0,
      vy: 0,
      radius: Math.max(4, Math.min(12, godScore * 8 + 4)),
      node,
    };
  });

  const indexById = new Map(layout.map((n) => [n.id, n]));

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const cooling = 1 - iter / ITERATIONS;
    const temp = K * cooling * 0.5;

    for (let i = 0; i < layout.length; i++) {
      for (let j = i + 1; j < layout.length; j++) {
        const a = layout[i];
        const b = layout[j];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (K * K) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }

    for (const edge of edges) {
      const a = indexById.get(edge.from);
      const b = indexById.get(edge.to);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist * dist) / K;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }

    const padding = 40;
    for (const n of layout) {
      const speed = Math.sqrt(n.vx * n.vx + n.vy * n.vy) || 1;
      n.x += (n.vx / speed) * Math.min(speed, temp);
      n.y += (n.vy / speed) * Math.min(speed, temp);
      n.x = Math.max(padding, Math.min(width - padding, n.x));
      n.y = Math.max(padding, Math.min(height - padding, n.y));
      n.vx = 0;
      n.vy = 0;
    }
  }

  return layout;
}

// ─── 엣지 클릭 히트박스 계산 (선분에서 점까지 거리) ─────────────────────────

function distPointToSegment(
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number,
): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq === 0) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [allNodes, setAllNodes] = useState<KnowledgeGraphNode[]>([]);
  const [allEdges, setAllEdges] = useState<KnowledgeGraphEdge[]>([]);
  const [communities, setCommunities] = useState<KnowledgeCommunity[]>([]);
  const [services, setServices] = useState<KnowledgeService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graphKey, setGraphKey] = useState(0); // refetch 트리거

  // 필터 상태
  const [availableCategories, setAvailableCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('');
  const [selectedService, setSelectedService] = useState<string>('');
  const [selectedPageTypes, setSelectedPageTypes] = useState<Set<PageType>>(
    new Set(PAGE_TYPES),
  );

  // SVG 크기
  const [svgSize, setSvgSize] = useState({ w: 800, h: 600 });
  const [layout, setLayout] = useState<LayoutNode[]>([]);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // EdgeInspector 상태
  const [activeEdge, setActiveEdge] = useState<{ from: string; to: string } | null>(null);

  // 데이터 로드
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [graphData, metaData, svcData] = await Promise.all([
          knowledgeApi.getGraph(),
          knowledgeApi.meta(),
          knowledgeApi.getServices().catch(() => [] as KnowledgeService[]),
        ]);
        setAllNodes(graphData.nodes);
        setAllEdges(graphData.edges);
        setCommunities(graphData.communities ?? []);
        setAvailableCategories(metaData.categories);
        setServices(svcData);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [graphKey]);

  // SVG 크기 관찰
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setSvgSize({ w: Math.max(400, width), h: Math.max(400, height) });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // 필터 적용 + 레이아웃 계산
  useEffect(() => {
    const filteredNodes = allNodes.filter((n) => {
      if (selectedCategory && n.category !== selectedCategory) return false;
      if (selectedService && (n.service ?? 'unknown') !== selectedService) return false;
      if (!selectedPageTypes.has(n.pageType)) return false;
      return true;
    });
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    const filteredEdges = allEdges.filter(
      (e) => nodeIds.has(e.from) && nodeIds.has(e.to),
    );

    if (filteredNodes.length === 0) {
      setLayout([]);
      return;
    }

    const newLayout = buildLayout(filteredNodes, filteredEdges, svgSize.w, svgSize.h);
    setLayout(newLayout);
  }, [allNodes, allEdges, selectedCategory, selectedService, selectedPageTypes, svgSize]);

  const togglePageType = useCallback((pt: PageType) => {
    setSelectedPageTypes((prev) => {
      const next = new Set(prev);
      if (next.has(pt)) {
        if (next.size <= 1) return prev;
        next.delete(pt);
      } else {
        next.add(pt);
      }
      return next;
    });
  }, []);

  const handleNodeClick = useCallback(
    (node: KnowledgeGraphNode) => {
      navigate(`/knowledge?id=${encodeURIComponent(node.id)}`);
    },
    [navigate],
  );

  // SVG 클릭 — 엣지 히트 테스트
  const handleSvgClick = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;

      const HIT_TOLERANCE = 6;

      for (const edge of visibleEdgesRef.current) {
        const src = layoutMapRef.current.get(edge.from);
        const tgt = layoutMapRef.current.get(edge.to);
        if (!src || !tgt) continue;
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const x2 = tgt.x - (dx / dist) * (tgt.radius + 6);
        const y2 = tgt.y - (dy / dist) * (tgt.radius + 6);
        if (distPointToSegment(px, py, src.x, src.y, x2, y2) < HIT_TOLERANCE) {
          setActiveEdge({ from: edge.from, to: edge.to });
          return;
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // ref로 최신 값을 핸들러에서 접근
  const visibleEdgesRef = useRef<KnowledgeGraphEdge[]>([]);
  const layoutMapRef = useRef<Map<string, LayoutNode>>(new Map());

  const visibleNodeIds = new Set(layout.map((n) => n.id));
  const visibleEdges = allEdges.filter(
    (e) => visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to),
  );
  const layoutMap = new Map(layout.map((n) => [n.id, n]));
  visibleEdgesRef.current = visibleEdges;
  layoutMapRef.current = layoutMap;

  // Top God Nodes (top 5)
  const topGodNodes = [...layout]
    .sort((a, b) => (b.node.godScore ?? 0) - (a.node.godScore ?? 0))
    .slice(0, 5);

  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* 헤더 */}
      <div className="px-6 pt-6 pb-4 border-b border-slate-800">
        <div className="w-full">
          <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-1">
            Knowledge · Graph
          </div>
          <h1 className="text-2xl font-light text-slate-50 tracking-tight">위키 링크 그래프</h1>
          <p className="text-xs text-slate-500 mt-1">
            노드 클릭 시 상세 페이지로 이동. 엣지 클릭 시 관계 상세 검사. 빨간 점선 = 깨진 링크. 보라 = 서비스 간 링크.
          </p>
        </div>
      </div>

      {/* 필터 바 */}
      <div className="px-6 py-3 border-b border-slate-800 flex flex-wrap gap-4 items-center">
        {/* 서비스 필터 */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            서비스
          </label>
          <select
            value={selectedService}
            onChange={(e) => setSelectedService(e.target.value)}
            className="px-2 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-sky-600"
          >
            <option value="">전체</option>
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title || s.id}
              </option>
            ))}
          </select>
        </div>

        {/* 카테고리 */}
        <div className="flex items-center gap-2">
          <label className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            카테고리
          </label>
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-2 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-sky-600"
          >
            <option value="">전체</option>
            {availableCategories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {/* page_type 체크박스 */}
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            Type
          </span>
          {PAGE_TYPES.map((pt) => (
            <label key={pt} className="flex items-center gap-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={selectedPageTypes.has(pt)}
                onChange={() => togglePageType(pt)}
                className="w-3 h-3 rounded border-slate-600"
                style={{ accentColor: PAGE_TYPE_COLOR[pt] }}
              />
              <span
                className="text-[11px] font-mono"
                style={{ color: PAGE_TYPE_COLOR[pt] }}
              >
                {pt}
              </span>
            </label>
          ))}
        </div>

        <div className="ml-auto text-[10px] font-mono text-slate-600">
          {layout.length} nodes · {visibleEdges.length} edges
        </div>
      </div>

      {/* 그래프 영역 */}
      <div ref={containerRef} className="flex-1 overflow-hidden relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
              <span className="text-slate-500 text-xs font-mono">그래프 로딩 중...</span>
            </div>
          </div>
        ) : error ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-2">
              <p className="text-red-400 text-sm">{error}</p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="text-xs text-slate-400 underline"
              >
                새로고침
              </button>
            </div>
          </div>
        ) : layout.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center space-y-3 max-w-sm">
              <div className="text-4xl text-slate-700">◇</div>
              <h3 className="text-slate-400 font-medium">아직 wiki 페이지가 없습니다.</h3>
              <p className="text-slate-600 text-sm">
                카테고리에 페이지를 등록하세요. 등록된 페이지의{' '}
                <code className="text-slate-500 font-mono text-xs">[[link]]</code> 구문이
                그래프로 시각화됩니다.
              </p>
              <button
                type="button"
                onClick={() => navigate('/knowledge')}
                className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition-colors"
              >
                지식 문서로 이동
              </button>
            </div>
          </div>
        ) : (
          <svg
            ref={svgRef}
            width={svgSize.w}
            height={svgSize.h}
            className="w-full h-full"
            onClick={handleSvgClick}
          >
            {/* 배경 패턴 */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
              </pattern>
              {/* 화살표 마커 */}
              {[
                { id: 'arrowNormal',   fill: '#475569' },
                { id: 'arrowBroken',   fill: '#ef4444' },
                { id: 'arrowCross',    fill: '#a855f7' },
                { id: 'arrowExplicit', fill: '#06b6d4' },
                { id: 'arrowImplicit', fill: '#64748b' },
              ].map(({ id, fill }) => (
                <marker
                  key={id}
                  id={id}
                  viewBox="0 0 10 10"
                  refX="10"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={fill} />
                </marker>
              ))}
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />

            {/* 엣지 */}
            {visibleEdges.map((edge, i) => {
              const src = layoutMap.get(edge.from);
              const tgt = layoutMap.get(edge.to);
              if (!src || !tgt) return null;

              const dx = tgt.x - src.x;
              const dy = tgt.y - src.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const x2 = tgt.x - (dx / dist) * (tgt.radius + 6);
              const y2 = tgt.y - (dy / dist) * (tgt.radius + 6);

              const broken = edge.is_broken;
              const cross = edge.crossService;
              const kind = edge.kind ?? 'explicit'; // 백엔드 미지원 시 fallback

              // 우선순위: broken > crossService > kind
              let strokeColor: string;
              let strokeDash: string | undefined;
              let markerEnd: string;
              let strokeWidth: number;

              if (broken) {
                strokeColor = '#ef4444';
                strokeDash = '4 3';
                markerEnd = 'url(#arrowBroken)';
                strokeWidth = 1.5;
              } else if (cross) {
                strokeColor = '#a855f7';
                strokeDash = '4 4';
                markerEnd = 'url(#arrowCross)';
                strokeWidth = 1.5;
              } else if (kind === 'explicit') {
                strokeColor = '#06b6d4'; // cyan
                strokeDash = undefined;
                markerEnd = 'url(#arrowExplicit)';
                strokeWidth = 2;
              } else {
                // implicit
                strokeColor = '#94a3b8'; // slate-400
                strokeDash = '4 3';
                markerEnd = 'url(#arrowImplicit)';
                strokeWidth = 1.5;
              }

              return (
                <line
                  key={i}
                  x1={src.x}
                  y1={src.y}
                  x2={x2}
                  y2={y2}
                  stroke={strokeColor}
                  strokeWidth={strokeWidth}
                  strokeDasharray={strokeDash}
                  markerEnd={markerEnd}
                  opacity={0.7}
                  style={{ cursor: 'pointer' }}
                />
              );
            })}

            {/* 노드 — fill: community 색상, stroke: service 색상 */}
            {layout.map((ln) => {
              const communityColor = getCommunityColor(ln.node.community ?? 0);
              const svcColor = getServiceColor(ln.node.service ?? 'unknown').dot;
              const isHovered = hoveredNode === ln.id;
              return (
                <g
                  key={ln.id}
                  transform={`translate(${ln.x},${ln.y})`}
                  className="cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation(); // SVG onClick 차단
                    handleNodeClick(ln.node);
                  }}
                  onMouseEnter={() => setHoveredNode(ln.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                >
                  {/* 글로우 */}
                  {isHovered && (
                    <circle r={ln.radius + 5} fill={communityColor} opacity={0.25} />
                  )}
                  {/* 노드 원: fill = community, stroke = service */}
                  <circle
                    r={ln.radius}
                    fill={communityColor}
                    fillOpacity={0.8}
                    stroke={svcColor}
                    strokeWidth={isHovered ? 2.5 : 1.5}
                    strokeOpacity={0.9}
                  />
                  {/* 라벨 */}
                  <text
                    dy="0.35em"
                    textAnchor="middle"
                    fontSize={10}
                    fill="#f1f5f9"
                    fontFamily="monospace"
                    pointerEvents="none"
                    style={{ userSelect: 'none' }}
                  >
                    {ln.node.title.length > 12
                      ? ln.node.title.slice(0, 11) + '…'
                      : ln.node.title}
                  </text>
                  {/* 툴팁 */}
                  {isHovered && (
                    <g transform={`translate(${ln.radius + 8},-20)`}>
                      <rect
                        x={0}
                        y={-10}
                        width={Math.min(ln.node.title.length * 7 + 12, 200)}
                        height={22}
                        rx={4}
                        fill="#0f172a"
                        stroke="#334155"
                        strokeWidth={1}
                      />
                      <text
                        x={6}
                        y={6}
                        fontSize={11}
                        fill="#e2e8f0"
                        fontFamily="monospace"
                        pointerEvents="none"
                      >
                        {ln.node.title}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        )}

        {/* 범례 */}
        {!loading && !error && layout.length > 0 && (
          <div className="absolute bottom-4 right-4 bg-slate-900/90 border border-slate-800 rounded-xl px-3 py-3 backdrop-blur-sm w-48 space-y-3 overflow-y-auto max-h-[calc(100vh-200px)]">
            {/* 엣지 종류 */}
            <div>
              <div className="text-[10px] font-mono text-slate-500 mb-1.5 uppercase tracking-wider">엣지 종류</div>
              <div className="space-y-1.5">
                <LegendEdge stroke="#06b6d4" strokeWidth={2} label="Explicit" labelClass="text-cyan-400" />
                <LegendEdge stroke="#94a3b8" strokeWidth={1.5} dasharray="4 3" label="Implicit" labelClass="text-slate-400" />
                <LegendEdge stroke="#a855f7" strokeWidth={1.5} dasharray="4 4" label="Cross-service" labelClass="text-purple-400" />
                <LegendEdge stroke="#ef4444" strokeWidth={1.5} dasharray="4 3" label="Broken" labelClass="text-red-400" />
              </div>
            </div>

            <div className="border-t border-slate-800" />

            {/* Community 목록 */}
            {communities.length > 0 && (
              <div>
                <div className="text-[10px] font-mono text-slate-500 mb-1.5 uppercase tracking-wider">Community</div>
                <div className="space-y-1">
                  {communities.map((c) => {
                    const color = c.color ?? getCommunityColor(c.id);
                    return (
                      <div key={c.id} className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                        <span className="text-[10px] font-mono text-slate-300 truncate">{c.label || `C${c.id}`}</span>
                        <span className="text-[9px] font-mono text-slate-600 ml-auto flex-shrink-0">{c.size}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {communities.length > 0 && topGodNodes.length > 0 && (
              <div className="border-t border-slate-800" />
            )}

            {/* Top God Nodes */}
            {topGodNodes.length > 0 && (
              <div>
                <div className="text-[10px] font-mono text-slate-500 mb-1.5 uppercase tracking-wider">Top God Nodes</div>
                <div className="space-y-1">
                  {topGodNodes.map((ln, i) => (
                    <div key={ln.id} className="flex items-center gap-1.5">
                      <span className="text-[9px] font-mono text-slate-600 w-3 text-right flex-shrink-0">{i + 1}</span>
                      <div
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: getCommunityColor(ln.node.community ?? 0) }}
                      />
                      <span className="text-[10px] font-mono text-slate-300 truncate">{ln.node.title}</span>
                      <span className="text-[9px] font-mono text-amber-600 ml-auto flex-shrink-0">
                        {((ln.node.godScore ?? 0) * 100).toFixed(0)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 노드 색상 설명 */}
            <div className="border-t border-slate-800" />
            <div>
              <div className="text-[9px] font-mono text-slate-600">노드 fill = community</div>
              <div className="text-[9px] font-mono text-slate-600">노드 stroke = service</div>
            </div>
          </div>
        )}
      </div>

      {/* EdgeInspectorPanel */}
      {activeEdge && (
        <EdgeInspectorPanel
          from={activeEdge.from}
          to={activeEdge.to}
          onClose={() => setActiveEdge(null)}
          onPromoted={() => {
            setActiveEdge(null);
            setGraphKey((k) => k + 1);
          }}
        />
      )}
    </div>
  );
}

// ─── 범례 서브 컴포넌트 ───────────────────────────────────────────────────────

interface LegendEdgeProps {
  stroke: string;
  strokeWidth: number;
  dasharray?: string;
  label: string;
  labelClass: string;
}

function LegendEdge({ stroke, strokeWidth, dasharray, label, labelClass }: LegendEdgeProps) {
  return (
    <div className="flex items-center gap-2">
      <svg width="22" height="6" className="flex-shrink-0">
        <line
          x1="0" y1="3" x2="22" y2="3"
          stroke={stroke}
          strokeWidth={strokeWidth}
          strokeDasharray={dasharray}
        />
      </svg>
      <span className={`text-[10px] font-mono ${labelClass}`}>{label}</span>
    </div>
  );
}

export default KnowledgeGraphPage;
