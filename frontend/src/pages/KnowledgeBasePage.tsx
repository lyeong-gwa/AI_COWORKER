import { useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { mockDocuments } from '../data/mockData';
import { knowledgeApi } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useChatAssistant } from '../hooks/useChatAssistant';
import { useChatContext } from '../contexts/ChatContext';
import type { KnowledgeDocument } from '../types';
import type { KnowledgeSearchResult } from '../services/api';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const CATEGORY_OPTIONS = [
  { value: '', label: '전체 카테고리' },
  { value: 'technical', label: '기술 문서' },
  { value: 'support', label: '고객 지원' },
  { value: 'product', label: '제품 정보' },
  { value: 'internal', label: '내부 문서' },
  { value: 'guide', label: '가이드' },
  { value: '도구-API', label: '도구-API' },
  { value: 'etc', label: '기타' },
];

const syncStatusConfig: Record<string, { label: string; color: string; icon: string }> = {
  synced: { label: '동기화됨', color: 'bg-green-500', icon: '\u2713' },
  modified: { label: '수정됨', color: 'bg-yellow-500', icon: '\u23F3' },
  not_synced: { label: '미동기화', color: 'bg-gray-500', icon: '\u25CB' },
};

// ─────────────────────────────────────────────────────────────────────────────
// Loading Spinner
// ─────────────────────────────────────────────────────────────────────────────

function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClass = { sm: 'w-5 h-5', md: 'w-8 h-8', lg: 'w-12 h-12' }[size];
  return (
    <div className="flex items-center justify-center py-12">
      <div
        className={`${sizeClass} border-2 border-gray-600 border-t-blue-500 rounded-full animate-spin`}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Confirmation Dialog
// ─────────────────────────────────────────────────────────────────────────────

function ConfirmDialog({
  title,
  message,
  confirmLabel = '삭제',
  onConfirm,
  onCancel,
  deleting = false,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  deleting?: boolean;
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-md p-6">
        <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
        <p className="text-gray-300 text-sm mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {deleting ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                {confirmLabel} 중...
              </>
            ) : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Document Card
// ─────────────────────────────────────────────────────────────────────────────

function DocumentCard({
  doc,
  onClick,
}: {
  doc: KnowledgeDocument;
  onClick: () => void;
}) {
  const status = syncStatusConfig[doc.syncStatus] || syncStatusConfig.not_synced;

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 border border-gray-700 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-colors"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-2xl flex-shrink-0">{'\uD83D\uDCC4'}</span>
          <div className="min-w-0">
            <h3 className="font-medium text-white truncate">{doc.title}</h3>
            <p className="text-sm text-gray-400 truncate">{doc.id}.md</p>
          </div>
        </div>
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded text-xs text-white flex-shrink-0 ${status.color}`}
        >
          <span>{status.icon}</span>
          <span>{status.label}</span>
        </div>
      </div>

      {/* Category badge */}
      {doc.category && (
        <div className="mb-2">
          <span className="px-2 py-0.5 text-xs rounded bg-blue-900/50 text-blue-300 border border-blue-700/50">
            {CATEGORY_OPTIONS.find((c) => c.value === doc.category)?.label || doc.category}
          </span>
        </div>
      )}

      {/* Document info */}
      <div className="flex items-center gap-4 text-sm text-gray-400 mb-3">
        {doc.contentHash && <span>#{doc.contentHash.slice(0, 8)}</span>}
      </div>

      {/* Tags */}
      <div className="flex flex-wrap gap-1">
        {doc.tags.map((tag) => (
          <span
            key={tag}
            className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300"
          >
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Search Result Card (vector search)
// ─────────────────────────────────────────────────────────────────────────────

function SearchResultCard({
  result,
  onClick,
}: {
  result: KnowledgeSearchResult;
  onClick: () => void;
}) {
  const scorePercent = Math.round(result.score * 100);
  const scoreColor =
    scorePercent >= 80
      ? 'text-green-400'
      : scorePercent >= 50
        ? 'text-yellow-400'
        : 'text-red-400';

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 border border-gray-700 rounded-lg p-4 cursor-pointer hover:border-purple-500 transition-colors"
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-2xl flex-shrink-0">{'\uD83D\uDD0D'}</span>
          <div className="min-w-0">
            <h3 className="font-medium text-white truncate">{result.document.title}</h3>
            <p className="text-sm text-gray-400 truncate">{result.document.id}.md</p>
          </div>
        </div>
        <div className={`flex-shrink-0 text-sm font-mono font-bold ${scoreColor}`}>
          {scorePercent}%
        </div>
      </div>
      <p className="text-sm text-gray-400 line-clamp-2 mb-2">
        {result.document.content.slice(0, 150)}...
      </p>
      <div className="flex flex-wrap gap-1">
        {result.document.tags.map((tag) => (
          <span
            key={tag}
            className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300"
          >
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Document Creation Modal
// ─────────────────────────────────────────────────────────────────────────────

interface CreateFormData {
  title: string;
  content: string;
  category: string;
  tags: string;
  source: string;
}

const emptyCreateForm: CreateFormData = {
  title: '',
  content: '',
  category: '',
  tags: '',
  source: '',
};

function DocumentCreateModal({
  onClose,
  onCreated,
  isApiMode,
}: {
  onClose: () => void;
  onCreated: (doc: KnowledgeDocument) => void;
  isApiMode: boolean;
}) {
  const { toast } = useToast();
  const [form, setForm] = useState<CreateFormData>(emptyCreateForm);
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async () => {
    if (!form.title.trim()) {
      toast.warning('제목을 입력해주세요.');
      return;
    }
    if (!form.content.trim()) {
      toast.warning('내용을 입력해주세요.');
      return;
    }

    setSubmitting(true);
    const tags = form.tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      if (isApiMode) {
        const created = await knowledgeApi.create({
          title: form.title.trim(),
          content: form.content,
          category: form.category || 'etc',
          tags,
          source: form.source.trim() || undefined,
        });
        onCreated(created);
        toast.success('문서가 생성되었습니다.');
      } else {
        // Local fallback: generate a fake document
        const now = new Date().toISOString();
        const localDoc: KnowledgeDocument = {
          id: `doc-local-${Date.now()}`,
          title: form.title.trim(),
          content: form.content,
          category: form.category || 'etc',
          tags,
          source: form.source.trim() || undefined,
          syncStatus: 'not_synced',
          createdAt: now,
          updatedAt: now,
        };
        onCreated(localDoc);
        toast.success('문서가 로컬에 추가되었습니다.');
      }
      onClose();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`문서 생성에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">문서 추가</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            {'\u00D7'}
          </button>
        </div>

        {/* Form */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              제목 <span className="text-red-400">*</span>
            </label>
            <input
              name="title"
              value={form.title}
              onChange={handleChange}
              placeholder="문서 제목을 입력하세요"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>


          {/* Category */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              카테고리
            </label>
            <select
              name="category"
              value={form.category}
              onChange={handleChange}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">선택하세요</option>
              {CATEGORY_OPTIONS.filter((c) => c.value !== '').map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Source */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              출처
            </label>
            <input
              name="source"
              value={form.source}
              onChange={handleChange}
              placeholder="예: 개발팀, 외부 문서"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              태그 (쉼표로 구분)
            </label>
            <input
              name="tags"
              value={form.tags}
              onChange={handleChange}
              placeholder="예: api, documentation, guide"
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* Content */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              내용 <span className="text-red-400">*</span>
            </label>
            <textarea
              name="content"
              value={form.content}
              onChange={handleChange}
              rows={12}
              placeholder="마크다운 형식으로 문서 내용을 입력하세요..."
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-sm resize-y"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="p-4 border-t border-gray-700 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm"
          >
            취소
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {submitting && (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {submitting ? '생성 중...' : '문서 추가'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Document Detail / Edit Modal
// ─────────────────────────────────────────────────────────────────────────────

function DocumentDetailModal({
  doc,
  onClose,
  onUpdated,
  onDeleted,
  isApiMode,
}: {
  doc: KnowledgeDocument;
  onClose: () => void;
  onUpdated: (doc: KnowledgeDocument) => void;
  onDeleted: (id: string) => void;
  isApiMode: boolean;
}) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<'content' | 'vector' | 'api'>('content');
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Edit form state
  const [editTitle, setEditTitle] = useState(doc.title);
  const [editContent, setEditContent] = useState(doc.content);
  const [editCategory, setEditCategory] = useState(doc.category);
  const [editTags, setEditTags] = useState(doc.tags.join(', '));

  // API metadata state
  const [editApiMethod, setEditApiMethod] = useState((doc as any).api?.method || 'GET');
  const [editApiUrl, setEditApiUrl] = useState((doc as any).api?.url || '');
  const [editApiHeaders, setEditApiHeaders] = useState<{key: string; value: string}[]>(
    (doc as any).api?.headers
      ? Object.entries((doc as any).api.headers as Record<string, string>).map(([key, value]) => ({ key, value }))
      : []
  );
  const [editApiBody, setEditApiBody] = useState((doc as any).api?.bodyTemplate || '');

  const status = syncStatusConfig[doc.syncStatus];

  const handleStartEdit = () => {
    setEditTitle(doc.title);
    setEditContent(doc.content);
    setEditCategory(doc.category);
    setEditTags(doc.tags.join(', '));
    // Reset API fields
    setEditApiMethod((doc as any).api?.method || 'GET');
    setEditApiUrl((doc as any).api?.url || '');
    setEditApiHeaders(
      (doc as any).api?.headers
        ? Object.entries((doc as any).api.headers as Record<string, string>).map(([key, value]) => ({ key, value }))
        : []
    );
    setEditApiBody((doc as any).api?.bodyTemplate || '');
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
  };

  const handleSaveEdit = async () => {
    if (!editTitle.trim()) {
      toast.warning('제목을 입력해주세요.');
      return;
    }

    setSaving(true);
    const tags = editTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      if (isApiMode) {
        const apiMeta = editCategory === '\uB3C4\uAD6C-API' && editApiUrl ? {
          method: editApiMethod,
          url: editApiUrl,
          headers: Object.fromEntries(editApiHeaders.filter(h => h.key.trim()).map(h => [h.key, h.value])),
          ...(editApiBody ? { bodyTemplate: editApiBody } : {}),
        } : undefined;

        const updated = await knowledgeApi.update(doc.id, {
          title: editTitle.trim(),
          content: editContent,
          category: editCategory,
          tags,
          ...(apiMeta ? { api: apiMeta } : {}),
        } as any);
        onUpdated(updated);
        toast.success('문서가 수정되었습니다.');
      } else {
        const now = new Date().toISOString();
        const localUpdated: KnowledgeDocument = {
          ...doc,
          title: editTitle.trim(),
          content: editContent,
          category: editCategory,
          tags,
          syncStatus: doc.syncStatus === 'synced' ? 'modified' : doc.syncStatus,
          updatedAt: now,
        };
        onUpdated(localUpdated);
        toast.success('문서가 로컬에서 수정되었습니다.');
      }
      setIsEditing(false);
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`문서 수정에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      if (isApiMode) {
        await knowledgeApi.delete(doc.id);
      }
      onDeleted(doc.id);
      toast.success('문서가 삭제되었습니다.');
      onClose();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`문서 삭제에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      if (isApiMode) {
        const result = await knowledgeApi.sync(doc.id);
        if (result.document) {
          onUpdated(result.document);
          toast.success('벡터 DB 동기화가 완료되었습니다.');
        } else {
          // If document is not returned, update syncStatus locally
          const now = new Date().toISOString();
          onUpdated({ ...doc, syncStatus: 'synced', updatedAt: now });
          toast.success('벡터 DB 동기화가 완료되었습니다.');
        }
      } else {
        // Simulate sync for local mode
        await new Promise((r) => setTimeout(r, 1500));
        const now = new Date().toISOString();
        const localSynced: KnowledgeDocument = {
          ...doc,
          syncStatus: 'synced',
          updatedAt: now,
        };
        onUpdated(localSynced);
        toast.success('벡터 DB 동기화 시뮬레이션이 완료되었습니다.');
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`동기화에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
        <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
          {/* Header */}
          <div className="p-4 border-b border-gray-700 flex items-start justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-3xl flex-shrink-0">{'\uD83D\uDCC4'}</span>
              <div className="min-w-0">
                {isEditing ? (
                  <input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="text-xl font-bold text-white bg-gray-900 border border-gray-600 rounded px-2 py-1 w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                ) : (
                  <h2 className="text-xl font-bold text-white truncate">{doc.title}</h2>
                )}
                <p className="text-gray-400 text-sm">{doc.id}.md</p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <div
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs text-white ${status.color}`}
              >
                <span>{status.icon}</span>
                <span>{status.label}</span>
              </div>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white text-2xl leading-none ml-2"
              >
                {'\u00D7'}
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-700">
            <button
              onClick={() => setActiveTab('content')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'content'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {'\uD83D\uDCDD'} 내용
            </button>
            {doc.category === '\uB3C4\uAD6C-API' && (
              <button
                onClick={() => setActiveTab('api')}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === 'api'
                    ? 'text-cyan-400 border-b-2 border-cyan-400'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {'\uD83C\uDF10'} API 설정
              </button>
            )}
            <button
              onClick={() => setActiveTab('vector')}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === 'vector'
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {'\uD83D\uDD17'} 벡터 DB
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto p-4">
            {activeTab === 'content' && (
              <div className="space-y-4">
                {/* Edit: category & tags */}
                {isEditing && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">
                        카테고리
                      </label>
                      <select
                        value={editCategory}
                        onChange={(e) => setEditCategory(e.target.value)}
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        {CATEGORY_OPTIONS.filter((c) => c.value !== '').map((c) => (
                          <option key={c.value} value={c.value}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">
                        태그 (쉼표 구분)
                      </label>
                      <input
                        value={editTags}
                        onChange={(e) => setEditTags(e.target.value)}
                        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                )}

                {/* Content preview or editor */}
                {isEditing ? (
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      내용
                    </label>
                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      rows={16}
                      className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 resize-y"
                    />
                  </div>
                ) : (
                  <div className="bg-gray-900 rounded-lg p-4 font-mono text-sm">
                    <pre className="whitespace-pre-wrap text-gray-300">
                      {doc.content}
                    </pre>
                  </div>
                )}

                {/* Meta info (read-only) */}
                {!isEditing && (
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">카테고리: </span>
                      <span className="text-gray-200">
                        {CATEGORY_OPTIONS.find((c) => c.value === doc.category)?.label || doc.category || '-'}
                      </span>
                    </div>
                    {doc.source && (
                      <div>
                        <span className="text-gray-400">출처: </span>
                        <span className="text-gray-200">{doc.source}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-gray-400">생성일: </span>
                      <span className="text-gray-200">
                        {new Date(doc.createdAt).toLocaleString('ko-KR')}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">수정일: </span>
                      <span className="text-gray-200">
                        {new Date(doc.updatedAt).toLocaleString('ko-KR')}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'api' && (
              <div className="p-4 space-y-4">
                {isEditing ? (
                  <>
                    {/* Method + URL */}
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">요청</label>
                      <div className="flex gap-2">
                        <select
                          value={editApiMethod}
                          onChange={(e) => setEditApiMethod(e.target.value)}
                          className="px-3 py-2 rounded-lg text-sm font-bold bg-gray-700 text-white border-none"
                        >
                          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                        <input
                          value={editApiUrl}
                          onChange={(e) => setEditApiUrl(e.target.value)}
                          placeholder="https://api.example.com/v1/{{resource}}"
                          className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
                        />
                      </div>
                      {editApiUrl && !editApiUrl.startsWith('http') && (
                        <p className="text-red-400 text-[10px] mt-1">URL은 http:// 또는 https://로 시작해야 합니다</p>
                      )}
                    </div>

                    {/* Headers */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="text-xs text-gray-400">헤더</label>
                        <button
                          onClick={() => setEditApiHeaders(prev => [...prev, { key: '', value: '' }])}
                          className="text-xs text-cyan-400 hover:text-cyan-300"
                        >+ 추가</button>
                      </div>
                      <div className="space-y-1.5">
                        {editApiHeaders.map((h, i) => (
                          <div key={i} className="flex gap-2">
                            <input
                              value={h.key}
                              onChange={(e) => setEditApiHeaders(prev => prev.map((hh, idx) => idx === i ? { ...hh, key: e.target.value } : hh))}
                              placeholder="Header-Name"
                              className="w-1/3 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
                            />
                            <input
                              value={h.value}
                              onChange={(e) => setEditApiHeaders(prev => prev.map((hh, idx) => idx === i ? { ...hh, value: e.target.value } : hh))}
                              placeholder="value or {{variable}}"
                              className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-cyan-500"
                            />
                            <button
                              onClick={() => setEditApiHeaders(prev => prev.filter((_, idx) => idx !== i))}
                              className="text-gray-500 hover:text-red-400 text-xs px-1"
                            >{'\u2715'}</button>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Body template */}
                    {['POST', 'PUT', 'PATCH'].includes(editApiMethod) && (
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">바디 템플릿</label>
                        <textarea
                          value={editApiBody}
                          onChange={(e) => setEditApiBody(e.target.value)}
                          rows={5}
                          placeholder='{ "field": "{{variable}}" }'
                          className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono resize-y focus:outline-none focus:ring-1 focus:ring-cyan-500"
                        />
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    {/* Read-only API display */}
                    {(doc as any).api ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-1 text-xs rounded font-bold ${
                            (doc as any).api.method === 'GET' ? 'bg-green-600/40 text-green-300' :
                            (doc as any).api.method === 'POST' ? 'bg-blue-600/40 text-blue-300' :
                            (doc as any).api.method === 'PUT' ? 'bg-amber-600/40 text-amber-300' :
                            (doc as any).api.method === 'DELETE' ? 'bg-red-600/40 text-red-300' :
                            'bg-gray-600/40 text-gray-300'
                          }`}>
                            {(doc as any).api.method}
                          </span>
                        </div>
                        <div>
                          <label className="block text-xs text-gray-500 mb-1">URL</label>
                          <div className="bg-gray-900 rounded-lg p-2.5 text-xs text-gray-300 font-mono break-all">
                            {(doc as any).api.url}
                          </div>
                        </div>
                        {(doc as any).api.headers && Object.keys((doc as any).api.headers).length > 0 && (
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">헤더</label>
                            <div className="bg-gray-900 rounded-lg p-2.5 space-y-1">
                              {Object.entries((doc as any).api.headers as Record<string, string>).map(([k, v]) => (
                                <div key={k} className="flex gap-2 text-xs">
                                  <span className="text-cyan-300 font-mono">{k}:</span>
                                  <span className="text-gray-400 font-mono">{v}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {(doc as any).api.bodyTemplate && (
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">바디 템플릿</label>
                            <pre className="bg-gray-900 rounded-lg p-2.5 text-xs text-gray-300 font-mono whitespace-pre-wrap">
                              {(doc as any).api.bodyTemplate}
                            </pre>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <p className="text-gray-500 text-sm">API 설정이 없습니다</p>
                        <p className="text-gray-600 text-xs mt-1">편집 모드에서 API 설정을 추가할 수 있습니다</p>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {activeTab === 'vector' && (
              <div className="space-y-4">
                {/* Vector DB Info */}
                <div className="bg-gray-700 rounded-lg p-4 border-l-4 border-blue-500">
                  <h4 className="text-white font-medium mb-3">벡터 DB 정보</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">문서 ID</span>
                      <span className="text-gray-200 font-mono">
                        {doc.id}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Content Hash</span>
                      <span className="text-gray-200 font-mono">
                        {doc.contentHash ? doc.contentHash.slice(0, 16) : '-'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">동기화 상태</span>
                      <span
                        className={`${status.color} px-2 py-0.5 rounded text-xs text-white`}
                      >
                        {status.label}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">문서 길이</span>
                      <span className="text-gray-200">
                        {doc.content.length} characters
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sync Status Message */}
                {doc.syncStatus === 'modified' && (
                  <div className="bg-yellow-900/30 border border-yellow-600 rounded-lg p-3 text-yellow-200 text-sm">
                    {'\u23F3'} 문서가 수정되어 재동기화가 필요합니다.
                  </div>
                )}
                {doc.syncStatus === 'not_synced' && (
                  <div className="bg-gray-900/30 border border-gray-600 rounded-lg p-3 text-gray-200 text-sm">
                    {'\u25CB'} 벡터 DB에 동기화되지 않았습니다. 동기화를 실행하세요.
                  </div>
                )}
                {doc.syncStatus === 'synced' && (
                  <div className="bg-green-900/30 border border-green-600 rounded-lg p-3 text-green-200 text-sm">
                    {'\u2713'} 벡터 DB와 정상적으로 동기화되어 있습니다.
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="p-4 border-t border-gray-700 flex justify-between">
            <div className="flex gap-2">
              {isEditing ? (
                <>
                  <button
                    onClick={handleCancelEdit}
                    className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleSaveEdit}
                    disabled={saving}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm disabled:opacity-50 flex items-center gap-2"
                  >
                    {saving && (
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    )}
                    {saving ? '저장 중...' : '저장'}
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={handleStartEdit}
                    className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm"
                  >
                    {'\u270F\uFE0F'} 편집
                  </button>
                  <button
                    onClick={() => setShowDeleteConfirm(true)}
                    className="px-4 py-2 bg-gray-700 text-red-400 rounded-lg hover:bg-red-900/50 transition-colors text-sm"
                  >
                    {'\uD83D\uDDD1\uFE0F'} 삭제
                  </button>
                </>
              )}
            </div>
            {!isEditing && (
              <button
                onClick={handleSync}
                disabled={syncing}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 flex items-center gap-2"
              >
                {syncing ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <span>{'\uD83D\uDD04'}</span>
                )}
                {syncing ? '동기화 중...' : '동기화 실행'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Delete Confirmation */}
      {showDeleteConfirm && (
        <ConfirmDialog
          title="문서 삭제"
          message={`"${doc.title}" 문서를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
          confirmLabel="삭제"
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
          deleting={deleting}
        />
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export function KnowledgeBasePage() {
  const { toast } = useToast();
  const { setDocumentContext, clearContext } = useChatAssistant();
  const { onDataChange, setMode, setKnowledgeFilter } = useChatContext();
  const [searchParams, setSearchParams] = useSearchParams();

  // Data state
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [isApiMode, setIsApiMode] = useState(false);

  // UI state
  const [selectedDoc, setSelectedDoc] = useState<KnowledgeDocument | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchMode, setSearchMode] = useState<'normal' | 'vector'>('normal');

  // Vector search state
  const [vectorResults, setVectorResults] = useState<KnowledgeSearchResult[]>([]);
  const [vectorSearching, setVectorSearching] = useState(false);

  useEffect(() => {
    document.title = '지식 베이스 | AI 업무도우미';
  }, []);

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await knowledgeApi.list(categoryFilter || undefined);
      setDocuments(data);
      setIsApiMode(true);
    } catch {
      // Fallback to mock data
      setDocuments(mockDocuments);
      setIsApiMode(false);
      toast.info('API 연결 실패. 로컬 데이터를 사용합니다.');
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, toast]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    return onDataChange((target) => {
      if (target.includes('knowledge') || target.includes('document')) loadDocuments();
    });
  }, [onDataChange, loadDocuments]);

  // ── Auto-open document from URL query param ──────────────────────
  useEffect(() => {
    const docId = searchParams.get('doc');
    if (docId && documents.length > 0 && !loading) {
      const found = documents.find(d => d.id === docId);
      if (found) {
        setSelectedDoc(found);
        // Remove the query param to keep URL clean
        searchParams.delete('doc');
        setSearchParams(searchParams, { replace: true });
      }
    }
  }, [searchParams, documents, loading, setSearchParams]);

  // ── Keyboard shortcuts ────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input/textarea
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) {
        // Only handle Escape in input fields
        if (e.key === 'Escape') {
          target.blur();
        }
        return;
      }

      // Escape: close any open modal
      if (e.key === 'Escape') {
        if (selectedDoc) {
          setSelectedDoc(null);
        } else if (showCreateModal) {
          setShowCreateModal(false);
        }
      }

      // Ctrl+N or Cmd+N: open create modal
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        setShowCreateModal(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedDoc, showCreateModal]);

  // ── Set chat context when document is selected ──────────────────

  useEffect(() => {
    if (selectedDoc) {
      setDocumentContext(selectedDoc);
    } else {
      clearContext();
    }
  }, [selectedDoc, setDocumentContext, clearContext]);

  // ── Local filtering (normal search) ────────────────────────────────────────

  const filteredDocs = useMemo(() => {
    if (searchMode === 'vector') return documents; // not used in vector mode
    let result = documents;

    // Category filter (already applied server-side if API mode, but do local too for safety)
    if (categoryFilter) {
      result = result.filter((doc) => doc.category === categoryFilter);
    }

    // Tag filter (OR logic)
    if (selectedTags.length > 0) {
      result = result.filter((doc) =>
        selectedTags.some((tag) => doc.tags.includes(tag))
      );
    }

    // Text search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (doc) =>
          doc.title.toLowerCase().includes(q) ||
          doc.id.toLowerCase().includes(q) ||
          doc.content.toLowerCase().includes(q) ||
          doc.tags.some((tag) => tag.toLowerCase().includes(q))
      );
    }

    return result;
  }, [documents, searchQuery, categoryFilter, selectedTags, searchMode]);

  // ── Auto-set chat mode on mount/unmount ──────────────────────────
  useEffect(() => {
    setMode('knowledge');
    return () => setMode('general');
  }, [setMode]);

  // ── Push knowledge filter to chat context ────────────────────────
  useEffect(() => {
    setKnowledgeFilter({
      category: categoryFilter || undefined,
      tags: selectedTags.length > 0 ? selectedTags : undefined,
      visibleDocIds: filteredDocs.map(d => d.id),
    });
    return () => setKnowledgeFilter(null);
  }, [categoryFilter, selectedTags, filteredDocs, setKnowledgeFilter]);

  // ── Vector search ──────────────────────────────────────────────────────────

  const handleVectorSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setVectorResults([]);
      return;
    }

    setVectorSearching(true);
    try {
      const results = await knowledgeApi.search({
        query: searchQuery.trim(),
        topK: 10,
        category: categoryFilter || undefined,
      });
      setVectorResults(results);
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`유사도 검색에 실패했습니다${detail ? `: ${detail}` : ''}. 일반 검색으로 전환합니다.`);
      setSearchMode('normal');
    } finally {
      setVectorSearching(false);
    }
  }, [searchQuery, categoryFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (searchMode === 'vector' && searchQuery.trim()) {
      const debounce = setTimeout(handleVectorSearch, 500);
      return () => clearTimeout(debounce);
    } else {
      setVectorResults([]);
    }
  }, [searchQuery, searchMode, handleVectorSearch]);

  // ── Sync stats ─────────────────────────────────────────────────────────────

  const syncStats = useMemo(
    () => ({
      total: documents.length,
      synced: documents.filter((d) => d.syncStatus === 'synced').length,
      pending: documents.filter((d) => d.syncStatus === 'modified').length,
      notSynced: documents.filter((d) => d.syncStatus === 'not_synced').length,
    }),
    [documents]
  );

  // ── CRUD callbacks ─────────────────────────────────────────────────────────

  const handleDocCreated = (newDoc: KnowledgeDocument) => {
    setDocuments((prev) => [newDoc, ...prev]);
  };

  const handleDocUpdated = (updated: KnowledgeDocument) => {
    setDocuments((prev) =>
      prev.map((d) => (d.id === updated.id ? updated : d))
    );
    setSelectedDoc(updated);
  };

  const handleDocDeleted = (id: string) => {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    setSelectedDoc(null);
  };

  // ── Unique tags from documents ───────────────────────────────────────────

  const availableTags = useMemo(() => {
    const tagSet = new Set<string>();
    documents.forEach(d => d.tags.forEach(t => tagSet.add(t)));
    return Array.from(tagSet).sort();
  }, [documents]);

  // ── Unique categories from documents ───────────────────────────────────────

  const availableCategories = useMemo(() => {
    const cats = new Set(documents.map((d) => d.category).filter(Boolean));
    const base = CATEGORY_OPTIONS.filter(
      (c) => c.value === '' || cats.has(c.value)
    );
    // Add any unknown categories from documents
    cats.forEach((cat) => {
      if (!CATEGORY_OPTIONS.find((c) => c.value === cat)) {
        base.push({ value: cat, label: cat });
      }
    });
    return base;
  }, [documents]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white">지식 베이스</h1>
            <p className="text-gray-400 text-sm">
              벡터 DB에 동기화되는 마크다운 문서를 관리합니다 (1문서 = 1청크)
              {!isApiMode && (
                <span className="ml-2 text-yellow-400">[로컬 모드]</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2 text-sm"
            >
              <span>+</span>
              <span>문서 추가</span>
            </button>
          </div>
        </div>

        {/* Stats, Category Filter & Search */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          {/* Sync Stats */}
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-400">
              전체: <span className="text-white">{syncStats.total}</span>
            </span>
            <span className="text-green-400">{'\u2713'} 동기화: {syncStats.synced}</span>
            <span className="text-yellow-400">{'\u23F3'} 대기: {syncStats.pending}</span>
            <span className="text-gray-400">{'\u25CB'} 미동기화: {syncStats.notSynced}</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Category Filter */}
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {availableCategories.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>

            {/* Tag Filter Chips */}
            {availableTags.length > 0 && (
              <div className="flex items-center gap-1 max-w-[300px] overflow-x-auto">
                {availableTags.slice(0, 8).map(tag => (
                  <button
                    key={tag}
                    onClick={() => setSelectedTags(prev =>
                      prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]
                    )}
                    className={`px-2 py-0.5 rounded text-xs whitespace-nowrap transition-colors ${
                      selectedTags.includes(tag)
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-400 hover:text-white hover:bg-gray-600'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
                {selectedTags.length > 0 && (
                  <button
                    onClick={() => setSelectedTags([])}
                    className="px-1.5 py-0.5 text-xs text-gray-500 hover:text-white"
                    title="태그 필터 초기화"
                  >
                    {'\u00D7'}
                  </button>
                )}
              </div>
            )}

            {/* Search Mode Toggle */}
            <div className="flex bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
              <button
                onClick={() => setSearchMode('normal')}
                className={`px-3 py-2 text-xs font-medium transition-colors ${
                  searchMode === 'normal'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                일반 검색
              </button>
              <button
                onClick={() => {
                  if (!isApiMode) {
                    toast.warning('유사도 검색은 API 모드에서만 사용 가능합니다.');
                    return;
                  }
                  setSearchMode('vector');
                }}
                className={`px-3 py-2 text-xs font-medium transition-colors ${
                  searchMode === 'vector'
                    ? 'bg-purple-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                유사도 검색
              </button>
            </div>

            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                placeholder={
                  searchMode === 'vector'
                    ? '유사도 검색어 입력...'
                    : '문서 검색...'
                }
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-64 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 pl-10 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                {searchMode === 'vector' ? '\uD83E\uDDE0' : '\uD83D\uDD0D'}
              </span>
              {vectorSearching && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <div className="w-4 h-4 border-2 border-gray-600 border-t-purple-500 rounded-full animate-spin" />
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Content Area */}
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <Spinner size="lg" />
        ) : searchMode === 'vector' ? (
          /* ── Vector search results ─────────────────────────────────── */
          <>
            {!searchQuery.trim() ? (
              <div className="text-center py-12 text-gray-400">
                <span className="text-4xl mb-4 block">{'\uD83E\uDDE0'}</span>
                <p>검색어를 입력하면 유사도 기반으로 문서를 찾습니다.</p>
              </div>
            ) : vectorSearching ? (
              <Spinner />
            ) : vectorResults.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <span className="text-4xl mb-4 block">{'\uD83D\uDCED'}</span>
                <p>유사한 문서를 찾지 못했습니다.</p>
              </div>
            ) : (
              <div className="space-y-1 mb-4">
                <p className="text-sm text-gray-400 mb-3">
                  {vectorResults.length}개의 유사 문서를 찾았습니다.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {vectorResults.map((result) => (
                    <SearchResultCard
                      key={result.document.id}
                      result={result}
                      onClick={() => setSelectedDoc(result.document)}
                    />
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          /* ── Normal document grid ──────────────────────────────────── */
          <>
            {filteredDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-4">
                  <span className="text-3xl">📄</span>
                </div>
                {documents.length === 0 ? (
                  <>
                    <h3 className="text-lg font-medium text-gray-300 mb-2">등록된 문서가 없습니다</h3>
                    <p className="text-gray-500 text-sm mb-4 max-w-md">문서를 추가하여 AI 어시스턴트가 참조할 수 있는 지식 베이스를 구축하세요</p>
                    <button
                      onClick={() => setShowCreateModal(true)}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      + 첫 번째 문서 추가
                    </button>
                  </>
                ) : (
                  <p className="text-gray-400">검색 결과가 없습니다</p>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredDocs.map((doc) => (
                  <DocumentCard
                    key={doc.id}
                    doc={doc}
                    onClick={() => setSelectedDoc(doc)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Modals */}
      {selectedDoc && (
        <DocumentDetailModal
          doc={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onUpdated={handleDocUpdated}
          onDeleted={handleDocDeleted}
          isApiMode={isApiMode}
        />
      )}

      {showCreateModal && (
        <DocumentCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={handleDocCreated}
          isApiMode={isApiMode}
        />
      )}

    </div>
  );
}
