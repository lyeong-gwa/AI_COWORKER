import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { knowledgeApi } from '../../services/api';
import type { KnowledgeDocument } from '../../types';

interface UpstreamField {
  name: string;
  type: string;
}

interface KnowledgeConfig {
  searchField?: string;
  category?: string;
  tags?: string[];
  maxResults?: number;
  matchCount?: number;
}

interface KnowledgeConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: KnowledgeConfig;
  upstreamFields: UpstreamField[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: KnowledgeConfig) => void;
  onDelete: () => void;
  onClose: () => void;
}

export function KnowledgeConfigPanel({
  nodeId,
  nodeName,
  config,
  upstreamFields,
  onUpdateName,
  onUpdateConfig,
  onDelete,
  onClose,
}: KnowledgeConfigPanelProps) {
  const searchField = config.searchField || '';
  const category = config.category || '';
  const selectedTags = config.tags || [];
  const maxResults = config.maxResults ?? 5;

  // Suppress unused var lint
  void nodeId;

  // --- Dynamic metadata ---
  const [categories, setCategories] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [metaLoading, setMetaLoading] = useState(true);

  // --- Tag filter search ---
  const [tagSearch, setTagSearch] = useState('');

  // --- Matching documents ---
  const [matchingDocs, setMatchingDocs] = useState<KnowledgeDocument[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsExpanded, setDocsExpanded] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load metadata on mount
  useEffect(() => {
    let cancelled = false;
    setMetaLoading(true);
    knowledgeApi.meta()
      .then((meta) => {
        if (!cancelled) {
          setCategories(meta.categories || []);
          setAllTags(meta.tags || []);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCategories([]);
          setAllTags([]);
        }
      })
      .finally(() => {
        if (!cancelled) setMetaLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Fetch matching documents when category or tags change (debounced)
  const fetchMatchingDocs = useCallback(() => {
    setDocsLoading(true);
    knowledgeApi.list(category || undefined)
      .then((docs) => {
        let filtered = docs;
        if (selectedTags.length > 0) {
          filtered = docs.filter((doc) =>
            doc.tags?.some((t) => selectedTags.includes(t))
          );
        }
        setMatchingDocs(filtered);
        onUpdateConfig({ ...config, matchCount: filtered.length });
      })
      .catch(() => {
        setMatchingDocs([]);
        onUpdateConfig({ ...config, matchCount: 0 });
      })
      .finally(() => {
        setDocsLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, selectedTags.join(',')]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchMatchingDocs();
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [fetchMatchingDocs]);

  // --- Handlers ---
  const handleSearchFieldSelect = (fieldName: string) => {
    const newValue = searchField === fieldName ? '' : fieldName;
    onUpdateConfig({ ...config, searchField: newValue });
  };

  const handleCategoryChange = (newCategory: string) => {
    onUpdateConfig({ ...config, category: newCategory });
  };

  const handleTagToggle = (tag: string) => {
    const newTags = selectedTags.includes(tag)
      ? selectedTags.filter((t) => t !== tag)
      : [...selectedTags, tag];
    onUpdateConfig({ ...config, tags: newTags });
  };

  const handleMaxResultsChange = (value: number) => {
    const clamped = Math.min(7, Math.max(4, value));
    onUpdateConfig({ ...config, maxResults: clamped });
  };

  // --- Filtered tag list ---
  const filteredTags = useMemo(() => {
    if (!tagSearch.trim()) return allTags;
    const q = tagSearch.trim().toLowerCase();
    return allTags.filter((t) => t.toLowerCase().includes(q));
  }, [allTags, tagSearch]);

  const showTagSearch = allTags.length > 8;

  // --- Skeleton loader ---
  const Skeleton = ({ className = '' }: { className?: string }) => (
    <div className={`animate-pulse bg-gray-700 rounded ${className}`} />
  );

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-indigo-900 flex items-center justify-center">
              <svg className="w-5 h-5 text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <div>
              <div className="text-xs text-indigo-300/70 uppercase tracking-wider">지식 검색 설정</div>
              <input
                type="text"
                value={nodeName}
                onChange={(e) => onUpdateName(e.target.value)}
                className="bg-transparent text-white font-semibold text-sm border-none outline-none w-full"
                placeholder="이름 입력..."
              />
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Search field selection */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">검색 쿼리 필드</label>
          <p className="text-[10px] text-gray-500 mb-2">
            이전 노드의 출력에서 검색어로 사용할 필드를 선택합니다.
          </p>
          {upstreamFields.length > 0 ? (
            <div className="space-y-1.5">
              {upstreamFields.map(field => {
                const isSelected = searchField === field.name;
                const isString = field.type === 'string';
                return (
                  <button
                    key={field.name}
                    onClick={() => handleSearchFieldSelect(field.name)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all text-left ${
                      isSelected
                        ? 'bg-indigo-900/50 border-indigo-400 ring-1 ring-indigo-400/50'
                        : isString
                          ? 'bg-gray-900 border-gray-600 hover:border-indigo-500/50 hover:bg-gray-900/80'
                          : 'bg-gray-900/50 border-gray-700 hover:border-gray-500 opacity-60 hover:opacity-80'
                    }`}
                  >
                    {/* Radio indicator */}
                    <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-indigo-400 bg-indigo-400' : 'border-gray-500'
                    }`}>
                      {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                    </div>

                    {/* Field info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-200 font-mono">{field.name}</span>
                        <span className={`px-1.5 py-0.5 text-[9px] rounded border ${
                          field.type === 'string' ? 'bg-indigo-600/40 text-indigo-200 border-indigo-500/50' :
                          'bg-gray-600/40 text-gray-300 border-gray-500/50'
                        }`}>
                          {field.type}
                        </span>
                        {isString && (
                          <span className="text-[9px] text-indigo-400/70">추천</span>
                        )}
                      </div>
                    </div>

                    {/* Check icon */}
                    {isSelected && (
                      <svg className="w-4 h-4 text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="bg-gray-900 rounded-lg p-4 text-center">
              <div className="text-gray-500 text-xs mb-1">상위 노드가 연결되지 않았습니다</div>
              <p className="text-gray-600 text-[10px]">
                컨베이어벨트로 이전 노드를 연결하면 출력 필드가 표시됩니다.
              </p>
            </div>
          )}
        </div>

        {/* Category filter */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">카테고리 필터</label>
          {metaLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : (
            <select
              value={category}
              onChange={(e) => handleCategoryChange(e.target.value)}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">전체 카테고리</option>
              {categories.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          )}
        </div>

        {/* Tags filter - checkbox list */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">태그 필터</label>

          {metaLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-3/4" />
            </div>
          ) : (
            <>
              {/* Selected tags badges */}
              {selectedTags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-2">
                  {selectedTags.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => handleTagToggle(tag)}
                      className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-600/40 text-indigo-200 border border-indigo-500/50 rounded text-[11px] hover:bg-indigo-600/60 transition-colors"
                    >
                      {tag}
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  ))}
                </div>
              )}

              {/* Tag search input (if > 8 tags) */}
              {showTagSearch && (
                <div className="relative mb-2">
                  <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    value={tagSearch}
                    onChange={(e) => setTagSearch(e.target.value)}
                    placeholder="태그 검색..."
                    className="w-full bg-gray-900 border border-gray-600 rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder-gray-500"
                  />
                </div>
              )}

              {/* Tag checkbox list */}
              {allTags.length === 0 ? (
                <div className="bg-gray-900 rounded-lg p-3 text-center">
                  <p className="text-gray-500 text-xs">등록된 태그가 없습니다</p>
                </div>
              ) : (
                <div className="max-h-40 overflow-y-auto bg-gray-900 border border-gray-600 rounded-lg p-2 space-y-0.5 custom-scrollbar">
                  {filteredTags.length === 0 ? (
                    <p className="text-gray-500 text-xs text-center py-2">일치하는 태그 없음</p>
                  ) : (
                    filteredTags.map((tag) => {
                      const isChecked = selectedTags.includes(tag);
                      return (
                        <label
                          key={tag}
                          className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-colors text-xs ${
                            isChecked
                              ? 'bg-indigo-900/30 text-indigo-200'
                              : 'text-gray-300 hover:bg-gray-800'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => handleTagToggle(tag)}
                            className="sr-only"
                          />
                          <div className={`w-3.5 h-3.5 rounded border flex-shrink-0 flex items-center justify-center transition-colors ${
                            isChecked
                              ? 'bg-indigo-500 border-indigo-400'
                              : 'border-gray-500 bg-transparent'
                          }`}>
                            {isChecked && (
                              <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                              </svg>
                            )}
                          </div>
                          <span className="truncate">{tag}</span>
                        </label>
                      );
                    })
                  )}
                </div>
              )}

              <p className="text-[10px] text-gray-500 mt-1">
                선택한 태그에 해당하는 문서만 검색 대상이 됩니다
              </p>
            </>
          )}
        </div>

        {/* Matching documents preview */}
        <div>
          <button
            onClick={() => setDocsExpanded(!docsExpanded)}
            className="flex items-center justify-between w-full text-left"
          >
            <label className="text-xs text-gray-400 cursor-pointer">
              검색 대상 지식
              {!docsLoading && (
                <span className="ml-1.5 px-1.5 py-0.5 bg-indigo-600/30 text-indigo-300 rounded text-[10px]">
                  {matchingDocs.length}건
                </span>
              )}
            </label>
            <svg
              className={`w-4 h-4 text-gray-400 transition-transform ${docsExpanded ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {docsExpanded && (
            <div className="mt-1.5">
              {docsLoading ? (
                <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                  <Skeleton className="h-4 w-4/6" />
                </div>
              ) : matchingDocs.length === 0 ? (
                <div className="bg-gray-900 border border-gray-600 rounded-lg p-3 text-center">
                  <p className="text-gray-500 text-xs">조건에 맞는 문서가 없습니다</p>
                </div>
              ) : (
                <div className="max-h-[200px] overflow-y-auto bg-gray-900 border border-gray-600 rounded-lg p-2 space-y-1 custom-scrollbar">
                  {matchingDocs.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-gray-800/50 transition-colors"
                    >
                      <svg className="w-3 h-3 text-indigo-400 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="4" />
                      </svg>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs text-gray-200 block truncate">{doc.title}</span>
                      </div>
                      <span className="px-1.5 py-0.5 text-[9px] bg-gray-700 text-gray-400 border border-gray-600 rounded flex-shrink-0">
                        {doc.category}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Max results */}
        <div>
          <label className="block text-xs text-gray-400 mb-1.5">최대 결과 수</label>
          <input
            type="number"
            value={maxResults}
            onChange={(e) => handleMaxResultsChange(Number(e.target.value))}
            min={4}
            max={7}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <p className="text-[10px] text-gray-500 mt-1">
            4~7 범위, 기본값 5
          </p>
        </div>

        {/* Output info */}
        <div className="bg-indigo-900/20 border border-indigo-700/40 rounded-lg p-3">
          <div className="text-xs text-indigo-300/70 font-medium mb-1.5">출력 형식</div>
          <p className="text-xs text-indigo-200/80 leading-relaxed">
            입력 데이터에 knowledge 배열을 추가하여 출력합니다.
          </p>
          <pre className="mt-2 text-[10px] text-indigo-300/60 font-mono bg-gray-900 rounded p-2">
{`{ ...input, knowledge: [
  { title, content, score }
] }`}
          </pre>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2 bg-gray-900 rounded-lg p-3">
          <div className={`w-2.5 h-2.5 rounded-full ${searchField ? 'bg-indigo-400' : 'bg-gray-500 animate-pulse'}`} />
          <span className="text-xs text-gray-400">
            {searchField ? (
              <>
                <span className="text-indigo-300 font-mono">{searchField}</span> 필드로 지식을 검색합니다
              </>
            ) : (
              '검색 쿼리 필드를 선택해주세요'
            )}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 flex gap-2">
        <button
          onClick={onDelete}
          className="px-3 py-2 bg-red-600/20 text-red-400 rounded-lg hover:bg-red-600/30 text-sm flex-1 transition-colors"
        >
          삭제
        </button>
      </div>
    </div>
  );
}
