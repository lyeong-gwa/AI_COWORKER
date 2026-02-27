import { useState, useMemo, useEffect, useCallback } from 'react';
import type { AINode } from '../types';
import { SchemaFieldEditor, schemaToRows, rowsToSchema } from '../components/nodes/SchemaFieldEditor';
import type { SchemaFieldRow } from '../components/nodes/SchemaFieldEditor';
import { PromptEditor, defaultOutputEnforcement } from '../components/nodes/PromptEditor';
import type { OutputEnforcementConfig } from '../components/nodes/PromptEditor';
import { nodeApi } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useChatAssistant } from '../hooks/useChatAssistant';
import { useChatContext } from '../contexts/ChatContext';

// ============================================
// Node Card Component
// ============================================

function NodeCard({
  node,
  onEdit,
  onDelete,
}: {
  node: AINode;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const inputFields = Object.keys(node.inputSchema.properties);
  const outputFields = Object.keys(node.outputSchema.properties);

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-blue-500 transition-colors">
      {/* Header */}
      <div className={`p-4 ${node.color} bg-opacity-20 border-b border-gray-700`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`text-3xl p-2 rounded-lg ${node.color}`}>{node.icon}</span>
            <div>
              <h3 className="font-bold text-white text-lg">{node.name}</h3>
              <p className="text-gray-400 text-sm">{node.description}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="p-4 space-y-4">
        {/* Tags */}
        <div className="flex flex-wrap gap-1">
          {node.tags.map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300"
            >
              #{tag}
            </span>
          ))}
        </div>

        {/* Input/Output Schema */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-900 rounded p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-green-400">📥</span>
              <span className="text-xs font-medium text-gray-400">INPUT</span>
            </div>
            <div className="space-y-1">
              {inputFields.slice(0, 3).map((field) => (
                <div key={field} className="text-xs text-gray-300 truncate">
                  • {field}
                </div>
              ))}
              {inputFields.length > 3 && (
                <div className="text-xs text-gray-500">+{inputFields.length - 3} more</div>
              )}
            </div>
          </div>
          <div className="bg-gray-900 rounded p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-blue-400">📤</span>
              <span className="text-xs font-medium text-gray-400">OUTPUT</span>
            </div>
            <div className="space-y-1">
              {outputFields.slice(0, 3).map((field) => (
                <div key={field} className="text-xs text-gray-300 truncate">
                  • {field}
                </div>
              ))}
              {outputFields.length > 3 && (
                <div className="text-xs text-gray-500">+{outputFields.length - 3} more</div>
              )}
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="flex flex-wrap gap-2">
          <span className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-gray-700 text-gray-300">
            🤖 {node.llmConfig.model}
          </span>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-gray-700">
          <button
            onClick={onEdit}
            className="flex-1 px-3 py-2 bg-gray-700 text-gray-200 rounded hover:bg-gray-600 text-sm transition-colors"
          >
            ✏️ 편집
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-2 bg-gray-700 text-red-400 rounded hover:bg-red-900 text-sm transition-colors"
          >
            🗑️
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Node Editor Modal
// ============================================

const TABS = [
  { key: 'basic', label: '기본 정보', icon: '📋' },
  { key: 'schema', label: 'Input/Output', icon: '📐' },
  { key: 'prompt', label: '프롬프트', icon: '💬' },
] as const;

type TabKey = typeof TABS[number]['key'];

function NodeEditorModal({
  node,
  onSave,
  onClose,
}: {
  node: AINode | null;
  onSave: (node: AINode) => Promise<void>;
  onClose: () => void;
}) {
  const isNew = node === null;
  const [activeTab, setActiveTab] = useState<TabKey>('basic');
  const [saving, setSaving] = useState(false);

  // ── Basic fields ─────────────────────────────────────────────────────────
  const [name, setName] = useState(node?.name || '');
  const [description, setDescription] = useState(node?.description || '');
  const [icon, setIcon] = useState(node?.icon || '🔷');
  const [color, setColor] = useState(node?.color || 'bg-blue-600');
  const [tags, setTags] = useState(node?.tags.join(', ') || '');

  // ── Schema (form-based) ──────────────────────────────────────────────────
  const [inputRows, setInputRows] = useState<SchemaFieldRow[]>(() =>
    schemaToRows(
      node?.inputSchema.properties || {},
      node?.inputSchema.required
    )
  );
  const [outputRows, setOutputRows] = useState<SchemaFieldRow[]>(() =>
    schemaToRows(
      node?.outputSchema.properties || {},
      node?.outputSchema.required
    )
  );

  // ── Prompt ───────────────────────────────────────────────────────────────
  const [systemPrompt, setSystemPrompt] = useState(node?.systemPrompt || '');
  const [userPromptTemplate, setUserPromptTemplate] = useState(node?.userPromptTemplate || '');
  const [model, setModel] = useState(node?.llmConfig.model || 'gpt-4o-mini');
  const [temperature, setTemperature] = useState(node?.llmConfig.temperature || 0.7);
  const [maxTokens, setMaxTokens] = useState(node?.llmConfig.maxTokens || 2000);

  // ── 출력 규격 강제 ──────────────────────────────────────────────────────────
  const [outputEnforcement, setOutputEnforcement] = useState<OutputEnforcementConfig>(
    node?.outputEnforcement || defaultOutputEnforcement
  );

  // ── Derived schemas ──────────────────────────────────────────────────────
  const currentInputSchema = useMemo(() => {
    const { properties, required } = rowsToSchema(inputRows);
    return { type: 'object' as const, properties, required };
  }, [inputRows]);

  const currentOutputSchema = useMemo(() => {
    const { properties, required } = rowsToSchema(outputRows);
    return { type: 'object' as const, properties, required };
  }, [outputRows]);

  // ─────────────────────────────────────────────────────────────────────────
  const colors = [
    'bg-blue-600', 'bg-green-600', 'bg-purple-600', 'bg-pink-600',
    'bg-yellow-600', 'bg-red-600', 'bg-indigo-600', 'bg-orange-600',
  ];

  const icons = ['🔷', '📥', '📤', '💬', '🔄', '📧', '🔧', '📚', '🤖', '⚡', '🎯', '📊'];

  // ── Save ─────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    const inputSchema = {
      type: 'object' as const,
      ...rowsToSchema(inputRows),
    };
    const outputSchema = {
      type: 'object' as const,
      ...rowsToSchema(outputRows),
    };

    const newNode: AINode = {
      id: node?.id || `node-${Date.now()}`,
      name,
      description,
      icon,
      color,
      tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
      inputSchema,
      outputSchema,
      systemPrompt,
      userPromptTemplate,
      llmConfig: {
        model,
        temperature,
        maxTokens,
        responseFormat: 'json',
      },
      outputEnforcement,
      createdAt: node?.createdAt || new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    setSaving(true);
    try {
      await onSave(newNode);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
      <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">
            {isNew ? '새 노드 만들기' : `노드 편집: ${node.name}`}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl leading-none">×</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700 overflow-x-auto">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-700/50'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {/* ─── BASIC ──────────────────────────────────────────────────── */}
          {activeTab === 'basic' && (
            <div className="space-y-6 max-w-2xl">
              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm text-gray-400">노드 이름 *</label>
                  <span className={`text-xs ${name.length > 90 ? 'text-red-400' : name.length > 75 ? 'text-yellow-400' : 'text-gray-500'}`}>
                    {name.length}/100
                  </span>
                </div>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={100}
                  placeholder="예: 문의글 조회"
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-3 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <div className="flex justify-between items-center mb-2">
                  <label className="block text-sm text-gray-400">설명</label>
                  <span className={`text-xs ${description.length > 450 ? 'text-red-400' : description.length > 375 ? 'text-yellow-400' : 'text-gray-500'}`}>
                    {description.length}/500
                  </span>
                </div>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  placeholder="이 노드가 하는 일을 설명하세요"
                  rows={3}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-3 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">아이콘</label>
                  <div className="flex flex-wrap gap-2">
                    {icons.map((i) => (
                      <button
                        key={i}
                        onClick={() => setIcon(i)}
                        className={`w-10 h-10 text-xl rounded-lg flex items-center justify-center transition-all ${
                          icon === i ? 'bg-blue-600 ring-2 ring-blue-400' : 'bg-gray-700 hover:bg-gray-600'
                        }`}
                      >
                        {i}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-2">색상</label>
                  <div className="flex flex-wrap gap-2">
                    {colors.map((c) => (
                      <button
                        key={c}
                        onClick={() => setColor(c)}
                        className={`w-10 h-10 rounded-lg ${c} transition-all ${
                          color === c ? 'ring-2 ring-white ring-offset-2 ring-offset-gray-800' : ''
                        }`}
                      />
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">태그 (쉼표로 구분)</label>
                <input
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="예: api, service-desk, fetch"
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-4 py-3 text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
          )}

          {/* ─── SCHEMA ─────────────────────────────────────────────────── */}
          {activeTab === 'schema' && (
            <div className="flex gap-6 h-full">
              <SchemaFieldEditor
                title="📥 Input Schema"
                badge="text-green-400"
                rows={inputRows}
                onChange={setInputRows}
              />
              <SchemaFieldEditor
                title="📤 Output Schema"
                badge="text-blue-400"
                rows={outputRows}
                onChange={setOutputRows}
              />
            </div>
          )}

          {/* ─── PROMPT ─────────────────────────────────────────────────── */}
          {activeTab === 'prompt' && (
            <PromptEditor
              systemPrompt={systemPrompt}
              userPromptTemplate={userPromptTemplate}
              onSystemPromptChange={setSystemPrompt}
              onUserPromptTemplateChange={setUserPromptTemplate}
              inputSchema={currentInputSchema}
              outputSchema={currentOutputSchema}
              model={model}
              temperature={temperature}
              maxTokens={maxTokens}
              onModelChange={setModel}
              onTemperatureChange={setTemperature}
              onMaxTokensChange={setMaxTokens}
              outputEnforcement={outputEnforcement}
              onOutputEnforcementChange={setOutputEnforcement}
            />
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div className="text-xs text-gray-600">
            {`${Object.keys(currentInputSchema.properties).length}개 입력 / ${Object.keys(currentOutputSchema.properties).length}개 출력`}
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-6 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors"
            >
              취소
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {saving ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {isNew ? '생성 중...' : '저장 중...'}
                </>
              ) : (isNew ? '생성' : '저장')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Main Page
// ============================================

export function NodeManagementPage() {
  const [nodes, setNodes] = useState<AINode[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOnline, setIsOnline] = useState(true);
  const { toast } = useToast();
  const { setNodeContext, clearContext } = useChatAssistant();
  const { onDataChange, setMode } = useChatContext();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [editingNode, setEditingNode] = useState<AINode | null | 'new'>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    document.title = 'AI 노드 관리 | AI 업무도우미';
  }, []);

  useEffect(() => {
    setMode('node');
    return () => setMode('general');
  }, [setMode]);

  const loadNodes = useCallback(async () => {
    setLoading(true);
    try {
      const data = await nodeApi.list();
      setNodes(data);
      setIsOnline(true);
    } catch {
      const { mockAINodes } = await import('../data/mockData');
      setNodes(mockAINodes);
      setIsOnline(false);
      toast.info('오프라인 모드로 실행 중입니다');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadNodes();
  }, [loadNodes]);

  useEffect(() => {
    return onDataChange((target) => {
      if (target.includes('node')) loadNodes();
    });
  }, [onDataChange, loadNodes]);

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
        if (editingNode) {
          setEditingNode(null);
        } else if (confirmDelete) {
          setConfirmDelete(null);
        }
      }

      // Ctrl+N or Cmd+N: open create modal
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        if (!editingNode) {
          setEditingNode('new');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [editingNode, confirmDelete]);

  // ── Set chat context when node is being edited ──────────────────

  useEffect(() => {
    if (editingNode && editingNode !== 'new') {
      setNodeContext(editingNode);
    } else {
      clearContext();
    }
  }, [editingNode, setNodeContext, clearContext]);

  // 모든 태그 수집
  const allTags = Array.from(new Set(nodes.flatMap(n => n.tags)));

  // 필터링
  const filteredNodes = nodes.filter(node => {
    const matchesSearch = !searchQuery ||
      node.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      node.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesTag = !selectedTag || node.tags.includes(selectedTag);
    return matchesSearch && matchesTag;
  });

  const handleSaveNode = async (node: AINode) => {
    try {
      if (isOnline) {
        const exists = nodes.find(n => n.id === node.id);
        if (exists) {
          const updated = await nodeApi.update(node.id, {
            name: node.name,
            description: node.description,
            icon: node.icon,
            color: node.color,
            tags: node.tags,
            systemPrompt: node.systemPrompt,
            userPromptTemplate: node.userPromptTemplate,
            inputSchema: node.inputSchema as unknown as Record<string, unknown>,
            outputSchema: node.outputSchema as unknown as Record<string, unknown>,
            outputEnforcement: node.outputEnforcement,
            llmConfig: node.llmConfig,
          });
          setNodes(prev => prev.map(n => n.id === updated.id ? updated : n));
        } else {
          const created = await nodeApi.create({
            name: node.name,
            description: node.description,
            icon: node.icon,
            color: node.color,
            tags: node.tags,
            systemPrompt: node.systemPrompt,
            userPromptTemplate: node.userPromptTemplate,
            inputSchema: node.inputSchema as unknown as Record<string, unknown>,
            outputSchema: node.outputSchema as unknown as Record<string, unknown>,
            outputEnforcement: node.outputEnforcement,
            llmConfig: node.llmConfig,
          });
          setNodes(prev => [...prev, created]);
        }
        toast.success(exists ? '노드가 수정되었습니다' : '노드가 생성되었습니다');
      } else {
        setNodes(prev => {
          const exists = prev.find(n => n.id === node.id);
          return exists ? prev.map(n => n.id === node.id ? node : n) : [...prev, node];
        });
        toast.info('오프라인: 로컬에만 저장되었습니다');
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`저장에 실패했습니다${detail ? `: ${detail}` : ''}`);
    }
    setEditingNode(null);
  };

  const handleDeleteNode = (nodeId: string) => {
    setConfirmDelete(nodeId);
  };

  const confirmDeleteAction = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      if (isOnline) {
        await nodeApi.delete(confirmDelete);
        toast.success('노드가 삭제되었습니다');
      }
      setNodes(prev => prev.filter(n => n.id !== confirmDelete));
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`삭제에 실패했습니다${detail ? `: ${detail}` : ''}`);
    } finally {
      setDeleting(false);
      setConfirmDelete(null);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400 text-sm">노드 목록 불러오는 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white">노드 관리</h1>
            <p className="text-gray-400 text-sm">
              재사용 가능한 AI 노드를 생성하고 관리합니다
            </p>
          </div>
          <button
            onClick={() => setEditingNode('new')}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <span>+</span>
            <span>새 노드</span>
          </button>
        </div>

        {/* Search & Filter */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              placeholder="노드 검색..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 pl-10 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">태그:</span>
            <button
              onClick={() => setSelectedTag(null)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${
                !selectedTag ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              전체
            </button>
            {allTags.slice(0, 5).map(tag => (
              <button
                key={tag}
                onClick={() => setSelectedTag(tag === selectedTag ? null : tag)}
                className={`px-3 py-1 rounded-full text-sm transition-colors ${
                  selectedTag === tag ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                }`}
              >
                {tag}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="p-4 border-b border-gray-700 bg-gray-800/50">
        <div className="flex items-center gap-6 text-sm">
          <span className="text-gray-400">
            전체 노드: <span className="text-white font-medium">{nodes.length}</span>
          </span>
        </div>
      </div>

      {/* Node Grid */}
      <div className="flex-1 overflow-auto p-4">
        {filteredNodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-4">
              <span className="text-3xl">🤖</span>
            </div>
            <h3 className="text-lg font-medium text-gray-300 mb-2">AI 노드가 없습니다</h3>
            <p className="text-gray-500 text-sm mb-4 max-w-md">프롬프트와 스키마를 조합하여 AI 노드를 만드세요. 워크플로우에서 연결하여 사용할 수 있습니다</p>
            <button
              onClick={() => setEditingNode('new')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              + 첫 번째 AI 노드 만들기
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredNodes.map(node => (
              <NodeCard
                key={node.id}
                node={node}
                onEdit={() => setEditingNode(node)}
                onDelete={() => handleDeleteNode(node.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Editor Modal */}
      {editingNode && (
        <NodeEditorModal
          node={editingNode === 'new' ? null : editingNode}
          onSave={handleSaveNode}
          onClose={() => setEditingNode(null)}
        />
      )}

      {/* Confirm Delete Dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-2 sm:p-4">
          <div className="bg-gray-800 rounded-xl p-6 max-w-sm w-full">
            <h3 className="text-lg font-bold text-white mb-2">삭제 확인</h3>
            <p className="text-gray-400 text-sm mb-6">
              정말 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmDelete(null)}
                disabled={deleting}
                className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                취소
              </button>
              <button
                onClick={confirmDeleteAction}
                disabled={deleting}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    삭제 중...
                  </>
                ) : '삭제'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
