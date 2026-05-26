/**
 * Knowledge Viewer Page (`/knowledge`)
 *
 * 정책 갱신 (2026-05-14):
 *   지식문서는 다른 재료(노드/API명세/워크플로우)와 달리 웹 인라인 편집/신규/삭제 허용.
 *   사유: 지식은 복잡한 로직 없는 순수 데이터 덩어리이며 코드리뷰 지표 등 점진적
 *   큐레이션 + RAG 인입을 염두에 둔 결정.
 *
 * Phase 3 (2026-05-26): 사이드바 3단 계층 (서비스 → 카테고리 → 페이지) + ServiceBadge
 *   + 서비스 필터 셀렉트 + 페이지 상세 헤더 ServiceBadge
 *
 * 구성:
 *   좌: 서비스 → 카테고리 → 문서 3-depth 트리 + 검색/신규/서비스필터/펼치기/접기 액션바
 *   우: 보기 모드(읽기) / 편집 모드(인라인) / 신규 등록 모드 (3-state main panel)
 *
 * 상태 보존:
 *   - 트리 펼침 상태 → localStorage("knowledge.tree.expanded.v3", JSON 배열)
 *   - dirty 상태에서 다른 문서 클릭 시 confirm
 */
import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { knowledgeApi } from '../services/api';
import type { KnowledgeDocument, KnowledgeService } from '../types';
import { EmptyState } from '../components/common/EmptyState';
import { useToast } from '../components/common/Toast';
import { PageTypeBadge } from '../components/knowledge/PageTypeBadge';
import { ServiceBadge } from '../components/knowledge/ServiceBadge';
import { LinksPanel } from '../components/knowledge/LinksPanel';
import { LintRunModal } from '../components/knowledge/LintRunModal';
import { MarkdownView } from '../components/knowledge/MarkdownView';
import { ReferencedPagesSection } from '../components/knowledge/ReferencedPagesSection';

// `[[link]]` 본문 추출용 — ReferencedPagesSection 카드 소스로 사용
const WIKILINK_EXTRACT_RE = /\[\[([^\]]+)\]\]/g;

function extractWikiLinks(content: string): string[] {
  if (!content || !content.includes('[[')) return [];
  const out: string[] = [];
  WIKILINK_EXTRACT_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = WIKILINK_EXTRACT_RE.exec(content)) !== null) {
    const raw = m[1].trim();
    // alias `[[id|label]]` 지원
    const pipeIdx = raw.indexOf('|');
    const id = pipeIdx >= 0 ? raw.slice(0, pipeIdx).trim() : raw;
    out.push(id);
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// 상수 / 헬퍼
// ─────────────────────────────────────────────────────────────────────────────

const EXPANDED_STORAGE_KEY = 'knowledge.tree.expanded.v3';

type Mode = 'view' | 'edit' | 'create';

interface DraftState {
  title: string;
  category: string;
  tags: string[];
  content: string;
}

const EMPTY_DRAFT: DraftState = { title: '', category: '', tags: [], content: '' };

function loadExpanded(): Set<string> {
  try {
    const raw = localStorage.getItem(EXPANDED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.filter((x): x is string => typeof x === 'string'));
  } catch {
    // ignore
  }
  return new Set();
}

function saveExpanded(set: Set<string>) {
  try {
    localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(Array.from(set)));
  } catch {
    // ignore
  }
}

interface CategoryGroup {
  category: string;
  docs: KnowledgeDocument[];
}

interface ServiceGroup {
  serviceId: string;
  serviceTitle: string;
  total: number;
  categories: CategoryGroup[];
}

/**
 * 문서들을 서비스 → 카테고리 기준 3단 그룹핑.
 * 서비스: 건수 desc → id asc
 * 카테고리: 건수 desc → 이름 asc
 * 페이지: 제목 asc
 */
function buildTree(
  docs: KnowledgeDocument[],
  services: KnowledgeService[],
  serviceFilter: string,
): ServiceGroup[] {
  // service 필터 적용
  const filtered = serviceFilter ? docs.filter((d) => (d.service ?? 'unknown') === serviceFilter) : docs;

  // 서비스별 grouping
  const byService = new Map<string, KnowledgeDocument[]>();
  for (const d of filtered) {
    const svc = d.service?.trim() || 'unknown';
    if (!byService.has(svc)) byService.set(svc, []);
    byService.get(svc)!.push(d);
  }

  // 서비스 title 조회 맵
  const svcTitleMap = new Map(services.map((s) => [s.id, s.title]));

  const groups: ServiceGroup[] = [];
  for (const [serviceId, svcDocs] of byService) {
    if (svcDocs.length === 0) continue;

    // 카테고리별 grouping
    const byCategory = new Map<string, KnowledgeDocument[]>();
    for (const d of svcDocs) {
      const cat = d.category?.trim() || 'uncategorized';
      if (!byCategory.has(cat)) byCategory.set(cat, []);
      byCategory.get(cat)!.push(d);
    }

    const categories: CategoryGroup[] = [];
    for (const [category, catDocs] of byCategory) {
      const sortedDocs = catDocs.slice().sort((a, b) => a.title.localeCompare(b.title, 'ko'));
      categories.push({ category, docs: sortedDocs });
    }

    categories.sort((a, b) => {
      if (b.docs.length !== a.docs.length) return b.docs.length - a.docs.length;
      return a.category.localeCompare(b.category, 'ko');
    });

    groups.push({
      serviceId,
      serviceTitle: svcTitleMap.get(serviceId) ?? serviceId,
      total: svcDocs.length,
      categories,
    });
  }

  groups.sort((a, b) => {
    if (b.total !== a.total) return b.total - a.total;
    return a.serviceId.localeCompare(b.serviceId, 'ko');
  });

  return groups;
}

function serviceKey(svcId: string): string {
  return `svc::${svcId}`;
}
function categoryKey(svcId: string, cat: string): string {
  return `cat::${svcId}::${cat}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// 컴포넌트
// ─────────────────────────────────────────────────────────────────────────────

export function KnowledgeViewerPage() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [services, setServices] = useState<KnowledgeService[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [serviceFilter, setServiceFilter] = useState<string>('');
  const [expanded, setExpanded] = useState<Set<string>>(() => loadExpanded());

  const [mode, setMode] = useState<Mode>('view');
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [tagInput, setTagInput] = useState('');
  const [saving, setSaving] = useState(false);

  // Karpathy v2: backlinks 상태
  const [backlinks, setBacklinks] = useState<string[]>([]);
  const [backlinksLoading, setBacklinksLoading] = useState(false);

  // Karpathy v2: Lint 모달
  const [showLintModal, setShowLintModal] = useState(false);

  // 최초 로드 시 selectedId 자동 지정 위한 ref (재마운트 회피)
  const initialSelectionDoneRef = useRef(false);

  // ── 데이터 로드 ──────────────────────────────────────────────────────────
  const loadDocs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await knowledgeApi.list();
      setDocs(data);
      return data;
    } catch (e) {
      toast.error(`지식 조회 실패: ${e instanceof Error ? e.message : String(e)}`);
      return [];
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // 서비스 목록 로드 (에러 시 빈 배열 — graceful fallback)
  const loadServices = useCallback(async () => {
    try {
      const data = await knowledgeApi.getServices();
      setServices(data);
    } catch {
      setServices([]);
    }
  }, []);

  useEffect(() => {
    loadDocs().then((data) => {
      if (!initialSelectionDoneRef.current && data.length > 0) {
        // URL ?id=... 우선
        const queryId = searchParams.get('id');
        if (queryId && data.some((d) => d.id === queryId)) {
          setSelectedId(queryId);
        } else {
          setSelectedId(data[0].id);
        }
        initialSelectionDoneRef.current = true;
      }
    });
    loadServices();
    // searchParams는 초기 진입 시점만 참조 (의도적)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadDocs, loadServices]);

  // URL ?id= 외부 변경(브라우저 뒤로/앞으로) 반영
  useEffect(() => {
    const queryId = searchParams.get('id');
    if (!queryId) return;
    if (queryId === selectedId) return;
    if (docs.some((d) => d.id === queryId)) {
      setSelectedId(queryId);
      setMode('view');
    }
  }, [searchParams, docs, selectedId]);

  // Karpathy v2: 선택된 문서의 backlinks 로드
  useEffect(() => {
    if (!selectedId || mode !== 'view') {
      setBacklinks([]);
      return;
    }
    setBacklinksLoading(true);
    knowledgeApi
      .getBacklinks(selectedId)
      .then((res) => setBacklinks(res.backlinks ?? []))
      .catch(() => setBacklinks([]))
      .finally(() => setBacklinksLoading(false));
  }, [selectedId, mode]);

  // ── 검색 + 트리 빌드 ────────────────────────────────────────────────────
  const filteredDocs = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        d.content.toLowerCase().includes(q) ||
        d.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [docs, query]);

  const tree = useMemo(
    () => buildTree(filteredDocs, services, serviceFilter),
    [filteredDocs, services, serviceFilter],
  );

  // 검색이 활성화되면 매칭 결과의 서비스/카테고리 그룹을 자동 펼침
  const effectiveExpanded = useMemo(() => {
    if (!query.trim() && !serviceFilter) return expanded;
    const merged = new Set(expanded);
    for (const svc of tree) {
      merged.add(serviceKey(svc.serviceId));
      for (const cat of svc.categories) merged.add(categoryKey(svc.serviceId, cat.category));
    }
    return merged;
  }, [expanded, tree, query, serviceFilter]);

  // 카테고리 자동완성용 (drafts에서도 추가될 수 있도록 기존 docs 기반)
  const knownCategories = useMemo(() => {
    const set = new Set<string>();
    for (const d of docs) if (d.category) set.add(d.category);
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'ko'));
  }, [docs]);

  // ── selected / dirty ───────────────────────────────────────────────────
  const selected = useMemo(
    () => docs.find((d) => d.id === selectedId) ?? null,
    [docs, selectedId],
  );

  const isDirty = useMemo(() => {
    if (mode === 'view') return false;
    if (mode === 'create') {
      return (
        draft.title.trim() !== '' ||
        draft.category.trim() !== '' ||
        draft.tags.length > 0 ||
        draft.content.trim() !== ''
      );
    }
    if (mode === 'edit' && selected) {
      return (
        draft.title !== selected.title ||
        draft.category !== (selected.category ?? '') ||
        draft.tags.join('') !== (selected.tags ?? []).join('') ||
        draft.content !== selected.content
      );
    }
    return false;
  }, [mode, draft, selected]);

  // ── 트리 토글 ───────────────────────────────────────────────────────────
  const toggleKey = useCallback((key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      saveExpanded(next);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    const next = new Set<string>();
    for (const svc of tree) {
      next.add(serviceKey(svc.serviceId));
      for (const cat of svc.categories) next.add(categoryKey(svc.serviceId, cat.category));
    }
    setExpanded(next);
    saveExpanded(next);
  }, [tree]);

  const collapseAll = useCallback(() => {
    const next = new Set<string>();
    setExpanded(next);
    saveExpanded(next);
  }, []);

  // ── 선택 변경 (dirty 체크) ──────────────────────────────────────────────
  const tryChangeSelection = useCallback(
    (nextId: string | null, nextMode: Mode = 'view') => {
      if (isDirty) {
        const ok = window.confirm('변경사항이 저장되지 않았습니다. 무시하고 이동할까요?');
        if (!ok) return;
      }
      setSelectedId(nextId);
      setMode(nextMode);
      setDraft(EMPTY_DRAFT);
      setTagInput('');
      // URL 동기화 — chip / 카드 / 트리 어디서 호출되든 일관
      if (nextId) {
        setSearchParams({ id: nextId }, { replace: false });
      } else {
        setSearchParams({}, { replace: false });
      }
    },
    [isDirty, setSearchParams],
  );

  // ── 모드 전환 ───────────────────────────────────────────────────────────
  const enterEdit = useCallback(() => {
    if (!selected) return;
    setDraft({
      title: selected.title,
      category: selected.category ?? '',
      tags: [...(selected.tags ?? [])],
      content: selected.content,
    });
    setTagInput('');
    setMode('edit');
  }, [selected]);

  const enterCreate = useCallback(() => {
    if (isDirty) {
      const ok = window.confirm('변경사항이 저장되지 않았습니다. 무시하고 신규 등록을 시작할까요?');
      if (!ok) return;
    }
    setSelectedId(null);
    setDraft(EMPTY_DRAFT);
    setTagInput('');
    setMode('create');
  }, [isDirty]);

  const cancelEdit = useCallback(() => {
    setDraft(EMPTY_DRAFT);
    setTagInput('');
    setMode('view');
  }, []);

  // ── 태그 입력 ───────────────────────────────────────────────────────────
  const commitTagInput = useCallback(() => {
    const raw = tagInput.trim().replace(/^#/, '');
    if (!raw) return;
    setDraft((prev) => {
      if (prev.tags.includes(raw)) return prev;
      return { ...prev, tags: [...prev.tags, raw] };
    });
    setTagInput('');
  }, [tagInput]);

  const removeTag = useCallback((tag: string) => {
    setDraft((prev) => ({ ...prev, tags: prev.tags.filter((t) => t !== tag) }));
  }, []);

  // ── 저장 / 등록 / 삭제 ─────────────────────────────────────────────────
  const validateDraft = useCallback((): string | null => {
    if (!draft.title.trim()) return '제목을 입력하세요.';
    if (!draft.content.trim()) return '본문을 입력하세요.';
    return null;
  }, [draft]);

  const handleSave = useCallback(async () => {
    const err = validateDraft();
    if (err) {
      toast.error(err);
      return;
    }
    if (mode === 'edit' && selected) {
      setSaving(true);
      try {
        const updated = await knowledgeApi.update(selected.id, {
          title: draft.title.trim(),
          content: draft.content,
          category: draft.category.trim() || undefined,
          tags: draft.tags,
        });
        // 목록 갱신
        const fresh = await loadDocs();
        const next = fresh.find((d) => d.id === updated.id) ?? updated;
        setSelectedId(next.id);
        setMode('view');
        setDraft(EMPTY_DRAFT);
        setTagInput('');
        toast.success('지식문서 저장됨');
      } catch (e) {
        toast.error(`저장 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setSaving(false);
      }
    } else if (mode === 'create') {
      setSaving(true);
      try {
        const created = await knowledgeApi.create({
          title: draft.title.trim(),
          content: draft.content,
          category: draft.category.trim() || undefined,
          tags: draft.tags,
        });
        await loadDocs();
        setSelectedId(created.id);
        setMode('view');
        setDraft(EMPTY_DRAFT);
        setTagInput('');
        toast.success('지식문서 등록됨');
      } catch (e) {
        toast.error(`등록 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setSaving(false);
      }
    }
  }, [mode, selected, draft, loadDocs, toast, validateDraft]);

  const handleDelete = useCallback(async () => {
    if (!selected) return;
    const ok = window.confirm(`"${selected.title}" 문서를 삭제할까요?\n복구할 수 없습니다.`);
    if (!ok) return;
    setSaving(true);
    try {
      await knowledgeApi.delete(selected.id);
      const fresh = await loadDocs();
      // 다음 문서 자동 선택
      const idx = docs.findIndex((d) => d.id === selected.id);
      const fallback =
        fresh[Math.min(idx, fresh.length - 1)] ??
        fresh[0] ??
        null;
      setSelectedId(fallback ? fallback.id : null);
      setMode('view');
      setDraft(EMPTY_DRAFT);
      setTagInput('');
      toast.success('지식문서 삭제됨');
    } catch (e) {
      toast.error(`삭제 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }, [selected, docs, loadDocs, toast]);

  // ── Index 재생성 ────────────────────────────────────────────────────────
  const handleRebuildIndex = useCallback(async () => {
    setSaving(true);
    try {
      const result = await knowledgeApi.rebuildIndex({ categories: null });
      toast.success(
        `Index 재생성 완료: ${result.rebuilt.length > 0 ? result.rebuilt.join(', ') : '(변경 없음)'}`,
      );
    } catch (e) {
      toast.error(`Index 재생성 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }, [toast]);

  // ─────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-slate-950">
      {/* Lint 모달 */}
      {showLintModal && (
        <LintRunModal
          categories={knownCategories}
          onClose={() => setShowLintModal(false)}
        />
      )}

      {/* 페이지 헤더 */}
      <div className="px-6 pt-6 pb-4 border-b border-slate-800">
        <div className="w-full">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-mono tracking-[0.25em] uppercase text-slate-500 mb-1">
                Knowledge
              </div>
              <h1 className="text-2xl font-light text-slate-50 tracking-tight">지식 문서</h1>
              <p className="text-xs text-slate-500 mt-1">
                지식 문서는 웹에서도 직접 편집·등록·삭제할 수 있습니다. 다른 재료(노드/API명세/워크플로우)는 CLI 전용 정책이 유지됩니다.
              </p>
            </div>
            {/* Karpathy v2 액션 버튼 */}
            <div className="flex gap-2 flex-shrink-0 items-start mt-1">
              <button
                type="button"
                onClick={() => navigate('/knowledge/graph')}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
              >
                ◈ 그래프
              </button>
              <button
                type="button"
                onClick={() => setShowLintModal(true)}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors disabled:opacity-50"
              >
                ✓ Lint 실행
              </button>
              <button
                type="button"
                onClick={handleRebuildIndex}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors disabled:opacity-50"
                title="_index-{category}.md 전체 재생성"
              >
                {saving ? '처리 중…' : '↻ Index 재생성'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex">
        {/* ── Sidebar ───────────────────────────────────────────────── */}
        <aside className="w-80 flex-shrink-0 border-r border-slate-800 bg-slate-950 flex flex-col">
          {/* 액션바 */}
          <div className="p-3 space-y-2 border-b border-slate-800">
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="🔍 제목·내용·태그 검색"
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-600"
              />
              <button
                type="button"
                onClick={enterCreate}
                className="px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition-colors flex-shrink-0"
                title="새 지식문서 등록"
              >
                ＋ 신규
              </button>
            </div>

            {/* 서비스 필터 셀렉트 */}
            <div className="flex items-center gap-2">
              <label className="text-[10px] font-mono uppercase tracking-wider text-slate-500 flex-shrink-0">
                서비스
              </label>
              <select
                value={serviceFilter}
                onChange={(e) => setServiceFilter(e.target.value)}
                className="flex-1 px-2 py-1.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-sky-600"
              >
                <option value="">전체</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title || s.id}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-2 text-[11px]">
              <button
                type="button"
                onClick={expandAll}
                className="flex-1 px-2 py-1 rounded border border-slate-800 bg-slate-900/40 hover:bg-slate-800 text-slate-300 transition-colors"
              >
                ⊞ 모두 펼치기
              </button>
              <button
                type="button"
                onClick={collapseAll}
                className="flex-1 px-2 py-1 rounded border border-slate-800 bg-slate-900/40 hover:bg-slate-800 text-slate-300 transition-colors"
              >
                ⊟ 모두 접기
              </button>
            </div>
          </div>

          {/* 3단 트리: 서비스 → 카테고리 → 페이지 */}
          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="p-4 space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-12 bg-slate-900/40 rounded animate-pulse" />
                ))}
              </div>
            ) : tree.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                {docs.length === 0 ? '등록된 지식 문서가 없습니다' : '조건에 맞는 문서 없음'}
              </div>
            ) : (
              <ul className="py-1">
                {tree.map((svc) => {
                  const sKey = serviceKey(svc.serviceId);
                  const sOpen = effectiveExpanded.has(sKey);
                  return (
                    <li key={sKey}>
                      {/* 서비스 헤더 */}
                      <button
                        type="button"
                        onClick={() => toggleKey(sKey)}
                        className="w-full flex items-center gap-1.5 px-3 py-2 text-left text-xs text-slate-100 hover:bg-slate-900/60 transition-colors"
                      >
                        <span className="text-slate-500 w-3 inline-block text-[10px]">{sOpen ? '▼' : '▶'}</span>
                        <ServiceBadge
                          serviceId={svc.serviceId}
                          serviceTitle={svc.serviceTitle}
                          compact
                          className="flex-shrink-0"
                        />
                        <span className="flex-1 truncate font-medium">{svc.serviceTitle}</span>
                        <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">({svc.total})</span>
                      </button>

                      {/* 카테고리 목록 */}
                      {sOpen && (
                        <ul>
                          {svc.categories.map((cat) => {
                            const cKey = categoryKey(svc.serviceId, cat.category);
                            const cOpen = effectiveExpanded.has(cKey);
                            return (
                              <li key={cKey}>
                                <button
                                  type="button"
                                  onClick={() => toggleKey(cKey)}
                                  className="w-full flex items-center gap-1.5 pl-7 pr-3 py-1.5 text-left text-[11px] text-slate-300 hover:bg-slate-900/60 transition-colors"
                                >
                                  <span className="text-slate-500 w-3 inline-block text-[10px]">{cOpen ? '▼' : '▶'}</span>
                                  <span>📂</span>
                                  <span className="flex-1 truncate font-medium">{cat.category}</span>
                                  <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">({cat.docs.length})</span>
                                </button>

                                {/* 페이지 목록 */}
                                {cOpen && (
                                  <ul>
                                    {cat.docs.map((d) => {
                                      const isSelected = selectedId === d.id && mode !== 'create';
                                      return (
                                        <li key={d.id}>
                                          <button
                                            type="button"
                                            onClick={() => tryChangeSelection(d.id, 'view')}
                                            className={`w-full text-left pl-14 pr-3 py-1.5 border-l-2 transition-colors ${
                                              isSelected
                                                ? 'bg-slate-900 border-sky-500 text-slate-100'
                                                : 'border-transparent text-slate-400 hover:bg-slate-900/60 hover:text-slate-200'
                                            }`}
                                          >
                                            <div className="text-[12px] truncate">{d.title}</div>
                                          </button>
                                        </li>
                                      );
                                    })}
                                  </ul>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        {/* ── Detail / Editor ───────────────────────────────────────── */}
        <main className="flex-1 overflow-auto">
          {mode === 'create' ? (
            <EditorPanel
              heading="새 지식문서 등록"
              draft={draft}
              setDraft={setDraft}
              tagInput={tagInput}
              setTagInput={setTagInput}
              commitTagInput={commitTagInput}
              removeTag={removeTag}
              knownCategories={knownCategories}
              saving={saving}
              onSave={handleSave}
              onCancel={() => {
                if (isDirty) {
                  const ok = window.confirm('입력 중인 내용을 폐기할까요?');
                  if (!ok) return;
                }
                setMode('view');
                setDraft(EMPTY_DRAFT);
                setTagInput('');
                if (docs.length > 0 && !selectedId) setSelectedId(docs[0].id);
              }}
              saveLabel="💾 등록"
            />
          ) : mode === 'edit' && selected ? (
            <EditorPanel
              heading={`편집 — ${selected.title}`}
              draft={draft}
              setDraft={setDraft}
              tagInput={tagInput}
              setTagInput={setTagInput}
              commitTagInput={commitTagInput}
              removeTag={removeTag}
              knownCategories={knownCategories}
              saving={saving}
              onSave={handleSave}
              onCancel={() => {
                if (isDirty) {
                  const ok = window.confirm('편집 중인 내용을 폐기할까요?');
                  if (!ok) return;
                }
                cancelEdit();
              }}
              saveLabel="💾 저장"
            />
          ) : selected ? (
            <ViewerPanel
              doc={selected}
              onEdit={enterEdit}
              onDelete={handleDelete}
              busy={saving}
              backlinks={backlinks}
              backlinksLoading={backlinksLoading}
              onNavigateToDoc={(id) => tryChangeSelection(id, 'view')}
            />
          ) : !loading ? (
            <EmptyState
              icon={'∅'}
              title="지식 문서가 없습니다"
              description="좌측 상단의 ＋ 신규 버튼으로 등록하거나, CLI에서 등록하세요."
              hint="curl -X POST http://localhost:8002/api/v1/knowledge"
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 보기 패널
// ─────────────────────────────────────────────────────────────────────────────

interface ViewerPanelProps {
  doc: KnowledgeDocument;
  onEdit: () => void;
  onDelete: () => void;
  busy: boolean;
  backlinks: string[];
  backlinksLoading: boolean;
  onNavigateToDoc: (id: string) => void;
}

function ViewerPanel({
  doc,
  onEdit,
  onDelete,
  busy,
  backlinks,
  backlinksLoading,
  onNavigateToDoc,
}: ViewerPanelProps) {
  return (
    <div className="w-full px-8 py-8">
      {/* 헤더 영역 */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <div className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
              {doc.category || 'UNCATEGORIZED'}
            </div>
            {/* Phase 3: ServiceBadge */}
            {doc.service && (
              <ServiceBadge serviceId={doc.service} compact={false} />
            )}
            {/* Karpathy v2: page_type 배지 */}
            {doc.pageType && <PageTypeBadge type={doc.pageType} />}
          </div>
          <div className="flex items-baseline gap-2">
            <h2 className="text-2xl font-semibold text-slate-50 mt-1 break-words">{doc.title}</h2>
            {/* Karpathy v2: version */}
            {doc.version !== undefined && (
              <span className="text-[11px] font-mono text-slate-600 flex-shrink-0">
                v{doc.version}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {doc.tags.map((t) => (
              <span
                key={t}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800/60 text-slate-400 border border-slate-700/60"
              >
                #{t}
              </span>
            ))}
          </div>
          <div className="text-[11px] font-mono text-slate-600 mt-2">
            {doc.id} · 수정 {new Date(doc.updatedAt).toLocaleString('ko-KR')}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={onEdit}
            disabled={busy}
            className="px-3 py-1.5 rounded border border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-100 text-xs font-medium transition-colors disabled:opacity-50"
          >
            ✏ 편집
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={busy}
            className="px-3 py-1.5 rounded border border-red-900/60 bg-red-950/40 hover:bg-red-900/40 text-red-200 text-xs font-medium transition-colors disabled:opacity-50"
          >
            🗑 삭제
          </button>
        </div>
      </div>

      {/* 본문 + 링크 패널 — 2 컬럼 */}
      <div className="flex gap-6 items-start">
        {/* 본문 (마크다운 렌더 + [[wikilink]] chip + 호버 툴팁) */}
        <article className="flex-1 min-w-0 rounded-xl bg-slate-900/40 border border-slate-800 p-7">
          <MarkdownView content={doc.content} onNavigate={onNavigateToDoc} />

          {/* 📎 이 페이지가 참조하는 글 — 본문에서 추출된 [[link]] 카드 그리드 */}
          <ReferencedPagesSection
            links={extractWikiLinks(doc.content)}
            onNavigate={onNavigateToDoc}
          />
        </article>

        {/* Karpathy v2: Links / Backlinks 패널 */}
        <aside className="w-56 flex-shrink-0 sticky top-4">
          {backlinksLoading ? (
            <div className="space-y-3">
              <div className="h-24 bg-slate-900/40 rounded-lg border border-slate-800 animate-pulse" />
              <div className="h-24 bg-slate-900/40 rounded-lg border border-slate-800 animate-pulse" />
            </div>
          ) : (
            <LinksPanel
              links={doc.links ?? []}
              backlinks={backlinks}
              onNavigate={onNavigateToDoc}
            />
          )}
        </aside>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 편집/신규 패널
// ─────────────────────────────────────────────────────────────────────────────

interface EditorPanelProps {
  heading: string;
  draft: DraftState;
  setDraft: React.Dispatch<React.SetStateAction<DraftState>>;
  tagInput: string;
  setTagInput: React.Dispatch<React.SetStateAction<string>>;
  commitTagInput: () => void;
  removeTag: (tag: string) => void;
  knownCategories: string[];
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
  saveLabel: string;
}

function EditorPanel({
  heading,
  draft,
  setDraft,
  tagInput,
  setTagInput,
  commitTagInput,
  removeTag,
  knownCategories,
  saving,
  onSave,
  onCancel,
  saveLabel,
}: EditorPanelProps) {
  return (
    <div className="w-full px-8 py-8">
      <div className="flex items-start justify-between gap-4 mb-5">
        <h2 className="text-xl font-semibold text-slate-50 truncate">{heading}</h2>
        <div className="flex gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="px-3 py-1.5 rounded border border-slate-700 bg-slate-900/60 hover:bg-slate-800 text-slate-200 text-xs font-medium transition-colors disabled:opacity-50"
          >
            ↩ 취소
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
          >
            {saving ? '저장 중…' : saveLabel}
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {/* 제목 */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1">
            제목
          </label>
          <input
            type="text"
            value={draft.title}
            onChange={(e) => setDraft((p) => ({ ...p, title: e.target.value }))}
            placeholder="문서 제목"
            className="w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-600"
          />
        </div>

        {/* 카테고리 */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1">
            카테고리
          </label>
          <input
            type="text"
            list="knowledge-category-options"
            value={draft.category}
            onChange={(e) => setDraft((p) => ({ ...p, category: e.target.value }))}
            placeholder="예: 서비스사용문서 (자유 입력 가능)"
            className="w-full px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-600"
          />
          <datalist id="knowledge-category-options">
            {knownCategories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>

        {/* 태그 */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1">
            태그
          </label>
          <div className="flex flex-wrap gap-1.5 items-center px-2 py-2 rounded-lg bg-slate-900/60 border border-slate-800 focus-within:border-sky-600">
            {draft.tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700"
              >
                #{t}
                <button
                  type="button"
                  onClick={() => removeTag(t)}
                  className="text-slate-400 hover:text-red-400 ml-0.5 leading-none"
                  aria-label={`태그 ${t} 제거`}
                >
                  ×
                </button>
              </span>
            ))}
            <input
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ',') {
                  e.preventDefault();
                  commitTagInput();
                } else if (e.key === 'Backspace' && tagInput === '' && draft.tags.length > 0) {
                  // 빠른 삭제: 입력 비어있을 때 백스페이스 → 마지막 태그 제거
                  removeTag(draft.tags[draft.tags.length - 1]);
                }
              }}
              onBlur={() => {
                if (tagInput.trim()) commitTagInput();
              }}
              placeholder={draft.tags.length === 0 ? '+태그추가 (Enter/콤마)' : '+추가'}
              className="flex-1 min-w-[8rem] bg-transparent text-xs text-slate-100 placeholder-slate-600 focus:outline-none px-1 py-0.5"
            />
          </div>
        </div>

        {/* 본문 */}
        <div>
          <label className="block text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-1">
            본문
          </label>
          <textarea
            value={draft.content}
            onChange={(e) => setDraft((p) => ({ ...p, content: e.target.value }))}
            placeholder="마크다운 본문…"
            spellCheck={false}
            className="w-full min-h-[400px] px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-[13px] text-slate-100 placeholder-slate-600 font-mono leading-relaxed focus:outline-none focus:border-sky-600 resize-y"
          />
        </div>
      </div>
    </div>
  );
}
