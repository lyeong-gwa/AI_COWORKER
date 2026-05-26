/**
 * KnowledgeGraphPage (`/knowledge/graph`)
 *
 * Karpathy v2 — 지식 위키 링크 그래프 시각화.
 * 라이브러리: 순수 SVG (의존 추가 없이 N < 200 그래프에 충분)
 * force-directed 레이아웃: 단순 Fruchterman–Reingold 반복 시뮬레이션
 *
 * Phase 3: 서비스별 노드 색상 + cross-service edge 보라 점선 + 서비스 필터
 *
 * 기능:
 *   - 서비스 드롭다운 필터 (신규)
 *   - 카테고리 드롭다운, page_type 체크박스 5종 필터
 *   - 노드 색상 = service 별 (ServiceBadge 와 동일 매핑)
 *   - 노드 크기 ∝ backlinks_count
 *   - broken edge = 빨간 점선
 *   - cross-service edge = 보라 점선 (crossService === true)
 *   - 노드 클릭 → /knowledge/{id} 상세 이동
 *   - 빈 그래프 friendly empty state
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { knowledgeApi } from '../services/api';
import type { KnowledgeGraphNode, KnowledgeGraphEdge, KnowledgeService, PageType } from '../types';
import { getServiceColor } from '../components/knowledge/ServiceBadge';

// ─── page_type 필터용 색상 (범례 표시용, 노드 색상은 service 기준) ──────────

const PAGE_TYPE_COLOR: Record<PageType | string, string> = {
  Summary: '#3b82f6',    // blue-500
  Entity: '#10b981',     // emerald-500
  Concept: '#8b5cf6',    // violet-500
  Comparison: '#f59e0b', // amber-500
  Synthesis: '#f43f5e',  // rose-500
};

const PAGE_TYPES: PageType[] = ['Summary', 'Entity', 'Concept', 'Comparison', 'Synthesis'];

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

  // 초기 위치: 원 위에 배치
  const layout: LayoutNode[] = nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    const r = Math.min(width, height) * 0.35;
    const backlinks = node.backlinks_count ?? 0;
    return {
      id: node.id,
      x: width / 2 + r * Math.cos(angle),
      y: height / 2 + r * Math.sin(angle),
      vx: 0,
      vy: 0,
      radius: 8 + Math.min(backlinks * 2, 16),
      node,
    };
  });

  const indexById = new Map(layout.map((n) => [n.id, n]));

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const cooling = 1 - iter / ITERATIONS;
    const temp = K * cooling * 0.5;

    // 반발력 (모든 노드 쌍)
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

    // 인력 (엣지)
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

    // 위치 업데이트 + 경계 clamp
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

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [allNodes, setAllNodes] = useState<KnowledgeGraphNode[]>([]);
  const [allEdges, setAllEdges] = useState<KnowledgeGraphEdge[]>([]);
  const [services, setServices] = useState<KnowledgeService[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        setAvailableCategories(metaData.categories);
        setServices(svcData);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

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
        if (next.size <= 1) return prev; // 최소 1개 유지
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

  // 현재 필터 기반 엣지 (broken/crossService 포함)
  const visibleNodeIds = new Set(layout.map((n) => n.id));
  const visibleEdges = allEdges.filter(
    (e) => visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to),
  );
  const layoutMap = new Map(layout.map((n) => [n.id, n]));

  // 범례: 현재 보이는 노드의 서비스 목록
  const visibleServices = Array.from(
    new Set(layout.map((ln) => ln.node.service ?? 'unknown')),
  );
  const hasCrossService = visibleEdges.some((e) => e.crossService);

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
            노드 클릭 시 상세 페이지로 이동합니다. 빨간 점선 = 깨진 링크. 보라 점선 = 서비스 간 링크.
          </p>
        </div>
      </div>

      {/* 필터 바 */}
      <div className="px-6 py-3 border-b border-slate-800 flex flex-wrap gap-4 items-center">
        {/* 서비스 필터 (신규) */}
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
          >
            {/* 배경 패턴 */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
              </pattern>
              <marker
                id="arrowNormal"
                viewBox="0 0 10 10"
                refX="10"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
              </marker>
              <marker
                id="arrowBroken"
                viewBox="0 0 10 10"
                refX="10"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444" />
              </marker>
              <marker
                id="arrowCross"
                viewBox="0 0 10 10"
                refX="10"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#a855f7" />
              </marker>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />

            {/* 엣지 */}
            {visibleEdges.map((edge, i) => {
              const src = layoutMap.get(edge.from);
              const tgt = layoutMap.get(edge.to);
              if (!src || !tgt) return null;

              // 노드 경계까지 축소
              const dx = tgt.x - src.x;
              const dy = tgt.y - src.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 1;
              const x2 = tgt.x - (dx / dist) * (tgt.radius + 6);
              const y2 = tgt.y - (dy / dist) * (tgt.radius + 6);

              const broken = edge.is_broken;
              const cross = edge.crossService;

              // 우선순위: broken > cross > normal
              const strokeColor = broken ? '#ef4444' : cross ? '#a855f7' : '#475569';
              const strokeDash = broken ? '4 3' : cross ? '4 4' : undefined;
              const markerEnd = broken
                ? 'url(#arrowBroken)'
                : cross
                ? 'url(#arrowCross)'
                : 'url(#arrowNormal)';

              return (
                <line
                  key={i}
                  x1={src.x}
                  y1={src.y}
                  x2={x2}
                  y2={y2}
                  stroke={strokeColor}
                  strokeWidth={broken || cross ? 1.5 : 1}
                  strokeDasharray={strokeDash}
                  markerEnd={markerEnd}
                  opacity={0.7}
                />
              );
            })}

            {/* 노드 — 색상은 service 기준 */}
            {layout.map((ln) => {
              const svcId = ln.node.service ?? 'unknown';
              const color = getServiceColor(svcId).dot;
              const isHovered = hoveredNode === ln.id;
              return (
                <g
                  key={ln.id}
                  transform={`translate(${ln.x},${ln.y})`}
                  className="cursor-pointer"
                  onClick={() => handleNodeClick(ln.node)}
                  onMouseEnter={() => setHoveredNode(ln.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                >
                  {/* 외곽 글로우 */}
                  {isHovered && (
                    <circle
                      r={ln.radius + 5}
                      fill={color}
                      opacity={0.2}
                    />
                  )}
                  <circle
                    r={ln.radius}
                    fill={color}
                    fillOpacity={0.85}
                    stroke={isHovered ? '#fff' : color}
                    strokeWidth={isHovered ? 2 : 1}
                    strokeOpacity={0.6}
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
          <div className="absolute bottom-4 right-4 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-2 backdrop-blur-sm min-w-[140px]">
            {/* 서비스 색상 섹션 */}
            {visibleServices.length > 0 && (
              <>
                <div className="text-[10px] font-mono text-slate-500 mb-1.5">서비스</div>
                <div className="space-y-1 mb-2">
                  {visibleServices.map((svcId) => {
                    const cfg = getServiceColor(svcId);
                    const svcMeta = services.find((s) => s.id === svcId);
                    const label = svcMeta?.title ?? svcId;
                    return (
                      <div key={svcId} className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: cfg.dot }}
                        />
                        <span className={`text-[11px] font-mono truncate ${cfg.text}`}>{label}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="border-t border-slate-800 my-2" />
              </>
            )}

            {/* 엣지 범례 */}
            <div className="text-[10px] font-mono text-slate-500 mb-1.5">링크 유형</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <svg width="20" height="6">
                  <line x1="0" y1="3" x2="20" y2="3" stroke="#475569" strokeWidth="1" />
                </svg>
                <span className="text-[11px] text-slate-400 font-mono">일반 링크</span>
              </div>
              <div className="flex items-center gap-2">
                <svg width="20" height="6">
                  <line x1="0" y1="3" x2="20" y2="3" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="4 3" />
                </svg>
                <span className="text-[11px] text-red-400 font-mono">깨진 링크</span>
              </div>
              <div className="flex items-center gap-2">
                <svg width="20" height="6">
                  <line x1="0" y1="3" x2="20" y2="3" stroke="#a855f7" strokeWidth="1.5" strokeDasharray="4 4" />
                </svg>
                <span className="text-[11px] text-purple-400 font-mono">교차 서비스</span>
              </div>
            </div>

            {/* cross-service 없을 때 안내 */}
            {!hasCrossService && (
              <p className="text-[9px] text-slate-600 mt-1.5">
                (P4 마이그레이션 후 교차 링크 표시)
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default KnowledgeGraphPage;
