/**
 * @deprecated 이 페이지는 FactoryPage로 대체되었습니다.
 * 다중 워크플로우 지원이 필요할 경우 FactoryPage를 확장하세요.
 */
import { useState, useCallback, useRef, useMemo, useEffect, createContext, useContext } from 'react';
import type { DragEvent } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
  useReactFlow,
} from '@xyflow/react';
import type { Connection, Node, Edge, NodeTypes, Viewport } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { mockWorkflows, mockAINodes } from '../data/mockData';
import { workflowApi, nodeApi } from '../services/api';
import type { WorkflowSummary, WorkflowExecution } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useChatAssistant } from '../hooks/useChatAssistant';
import { useChatContext } from '../contexts/ChatContext';
import type { Workflow, AINode } from '../types';
import { TriggerConfigModal } from '../components/workflow/TriggerConfigModal';
import { ResultViewModal } from '../components/workflow/ResultViewModal';

// ============================================
// Types
// ============================================

interface CustomNodeData extends Record<string, unknown> {
  nodeId: string;
  instanceName: string;
  inputMapping?: Record<string, string>;
  definitionType?: string;
  aiNodeId?: string;
}

type NodeExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

interface NodeExecutionProgress {
  nodeInstanceId: string;
  status: NodeExecutionStatus;
  output?: unknown;
  error?: string;
  startedAt?: string;
  completedAt?: string;
}

// ============================================
// AINodes Context
// ============================================

const AINodesContext = createContext<AINode[]>([]);

// ============================================
// Custom Node Component (AI Node Instance)
// ============================================

function AINodeComponent({ data, selected }: { data: CustomNodeData; selected: boolean }) {
  const aiNodes = useContext(AINodesContext);
  const aiNode = aiNodes.find(n => n.id === data.nodeId);

  if (!aiNode) {
    return (
      <div className="bg-red-900 border-2 border-red-500 rounded-lg p-3">
        <span className="text-red-300">Unknown Node: {data.nodeId}</span>
      </div>
    );
  }

  const inputFields = Object.keys(aiNode.inputSchema?.properties ?? {});
  const outputFields = Object.keys(aiNode.outputSchema?.properties ?? {});

  return (
    <div
      className={`${aiNode.color} bg-opacity-90 border-2 rounded-lg shadow-xl min-w-[200px] transition-all ${
        selected ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-900' : ''
      }`}
    >
      {/* Input Handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#374151',
          border: '2px solid #9ca3af',
          width: 14,
          height: 14,
          top: '50%',
        }}
        title="input"
      />

      {/* Header */}
      <div className="px-4 py-3 border-b border-white/20">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{aiNode.icon}</span>
          <div>
            <div className="text-white font-semibold">{data.instanceName}</div>
            <div className="text-white/70 text-xs">{aiNode.name}</div>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 bg-black/20">
        <div className="mb-2">
          <div className="text-white/60 text-xs mb-1 flex items-center gap-1">
            <span className="text-green-300">input</span>
          </div>
          <div className="text-white/80 text-xs">
            {inputFields.slice(0, 2).join(', ')}
            {inputFields.length > 2 && ` +${inputFields.length - 2}`}
          </div>
        </div>

        <div>
          <div className="text-white/60 text-xs mb-1 flex items-center gap-1">
            <span className="text-blue-300">output</span>
          </div>
          <div className="text-white/80 text-xs">
            {outputFields.slice(0, 2).join(', ')}
            {outputFields.length > 2 && ` +${outputFields.length - 2}`}
          </div>
        </div>

      </div>

      {/* Output Handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#374151',
          border: '2px solid #9ca3af',
          width: 14,
          height: 14,
          top: '50%',
        }}
        title="output"
      />
    </div>
  );
}

// ============================================
// Trigger Node Component
// ============================================

function TriggerNodeComponent({ data, selected }: { data: CustomNodeData; selected: boolean }) {
  const icon = data.definitionType === 'schedule' ? '⏰' : data.definitionType === 'form' ? '📝' : '▶';
  const label = data.definitionType === 'schedule' ? '스케줄 트리거' : data.definitionType === 'form' ? '폼 트리거' : '수동 트리거';
  const bgColor = data.definitionType === 'schedule' ? 'bg-purple-700' : data.definitionType === 'form' ? 'bg-orange-700' : 'bg-gray-700';

  return (
    <div
      className={`${bgColor} border-2 border-white/30 rounded-2xl shadow-xl min-w-[180px] transition-all ${
        selected ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-900' : ''
      }`}
    >
      {/* Header */}
      <div className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{icon}</span>
          <div>
            <div className="text-white font-semibold text-sm">{data.instanceName}</div>
            <div className="text-white/60 text-xs">{label}</div>
          </div>
        </div>
      </div>

      {/* Hint */}
      <div className="px-4 pb-3">
        <div className="text-white/50 text-[10px]">클릭하여 설정</div>
      </div>

      {/* Output Handle only (triggers are start nodes) */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: '#374151',
          border: '2px solid #9ca3af',
          width: 14,
          height: 14,
          top: '50%',
        }}
        title="output"
      />
    </div>
  );
}

function ResultNodeComponent({ data, selected }: { data: CustomNodeData; selected: boolean }) {
  return (
    <div
      className={`bg-emerald-700 border-2 border-white/30 rounded-2xl shadow-xl min-w-[180px] transition-all ${
        selected ? 'ring-2 ring-emerald-400 ring-offset-2 ring-offset-gray-900' : ''
      }`}
    >
      {/* Input Handle only (result is end node) */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: '#374151',
          border: '2px solid #9ca3af',
          width: 14,
          height: 14,
          top: '50%',
        }}
        title="input"
      />

      {/* Header */}
      <div className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">📊</span>
          <div>
            <div className="text-white font-semibold text-sm">{data.instanceName}</div>
            <div className="text-emerald-200 text-xs">결과 출력</div>
          </div>
        </div>
      </div>

      {/* Hint */}
      <div className="px-4 pb-3">
        <div className="text-emerald-300/60 text-[10px]">클릭하여 결과 확인</div>
      </div>
    </div>
  );
}

const nodeTypes: NodeTypes = {
  aiNode: AINodeComponent,
  triggerNode: TriggerNodeComponent,
  resultNode: ResultNodeComponent,
};

// ============================================
// Spinner Component
// ============================================

function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-6 h-6 border-2',
    lg: 'w-8 h-8 border-3',
  };
  return (
    <div
      className={`${sizeClasses[size]} border-gray-600 border-t-blue-400 rounded-full animate-spin`}
    />
  );
}

// ============================================
// Confirm Dialog
// ============================================

function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
        <p className="text-gray-300 text-sm mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm"
          >
            취소
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm"
          >
            {confirmLabel || '확인'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================
// Workflow List View
// ============================================

function WorkflowListView({
  workflows,
  aiNodes,
  loading,
  onSelectWorkflow,
  onCreateNew,
  onDeleteWorkflow,
}: {
  workflows: Workflow[];
  aiNodes: AINode[];
  loading: boolean;
  onSelectWorkflow: (workflow: Workflow) => void;
  onCreateNew: () => void;
  onDeleteWorkflow: (id: string) => void;
}) {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">워크플로우</h1>
          <p className="text-gray-400 text-sm">AI 노드를 연결하여 자동화 워크플로우를 구성합니다</p>
        </div>
        <button
          onClick={onCreateNew}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <span>+</span>
          <span>새 워크플로우</span>
        </button>
      </header>

      {/* Workflow Grid */}
      <div className="flex-1 overflow-auto p-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Spinner size="lg" />
            <p className="text-gray-400 text-sm">워크플로우 목록을 불러오는 중...</p>
          </div>
        ) : workflows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-4">
              <span className="text-3xl">⚡</span>
            </div>
            <h3 className="text-lg font-medium text-gray-300 mb-2">워크플로우가 없습니다</h3>
            <p className="text-gray-500 text-sm mb-4 max-w-md">워크플로우를 생성하여 AI 노드들을 연결하고 자동화 파이프라인을 구축하세요</p>
            <button
              onClick={onCreateNew}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              + 첫 워크플로우 만들기
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workflows.map((workflow) => (
              <WorkflowCard
                key={workflow.id}
                workflow={workflow}
                aiNodes={aiNodes}
                onClick={() => onSelectWorkflow(workflow)}
                onDelete={(e) => {
                  e.stopPropagation();
                  setDeleteTarget(workflow.id);
                }}
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="워크플로우 삭제"
        message="이 워크플로우를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."
        confirmLabel="삭제"
        onConfirm={() => {
          if (deleteTarget) {
            onDeleteWorkflow(deleteTarget);
            setDeleteTarget(null);
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

function WorkflowCard({
  workflow,
  aiNodes,
  onClick,
  onDelete,
}: {
  workflow: Workflow;
  aiNodes: AINode[];
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const usedNodes = workflow.nodes
    .map((n) => aiNodes.find(node => node.id === n.nodeId))
    .filter(Boolean) as AINode[];

  return (
    <div
      onClick={onClick}
      className="bg-gray-800 border border-gray-700 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-colors group relative"
    >
      {/* Delete button */}
      <button
        onClick={onDelete}
        className="absolute top-3 right-3 p-1.5 rounded bg-gray-700/80 text-gray-400 hover:bg-red-600 hover:text-white opacity-0 group-hover:opacity-100 transition-all text-xs"
        title="삭제"
      >
        X
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-3 pr-8">
        <div className="flex items-center gap-2">
          <span className="text-2xl">⚙️</span>
          <div>
            <h3 className="font-medium text-white">{workflow.name}</h3>
            <p className="text-sm text-gray-400">{workflow.nodes.length}개 노드</p>
          </div>
        </div>
        <span
          className={`px-2 py-1 text-xs rounded ${
            workflow.trigger.type === 'schedule'
              ? 'bg-green-900 text-green-300'
              : workflow.trigger.type === 'webhook'
                ? 'bg-blue-900 text-blue-300'
                : workflow.trigger.type === 'form'
                  ? 'bg-orange-900 text-orange-300'
                  : 'bg-gray-700 text-gray-300'
          }`}
        >
          {workflow.trigger.type === 'schedule'
            ? '스케줄'
            : workflow.trigger.type === 'webhook'
              ? '웹훅'
              : workflow.trigger.type === 'manual'
                ? '수동'
                : workflow.trigger.type === 'form'
                  ? '폼'
                  : '이벤트'}
        </span>
      </div>

      {/* Description */}
      <p className="text-gray-300 text-sm mb-3 line-clamp-2">{workflow.description}</p>

      {/* Used Nodes */}
      <div className="flex flex-wrap gap-1 mb-3">
        {usedNodes.map((node, idx) => (
          <span
            key={idx}
            className={`${node.color} bg-opacity-30 px-2 py-0.5 text-xs rounded flex items-center gap-1`}
          >
            <span>{node.icon}</span>
            <span className="text-white/80">{node.name}</span>
          </span>
        ))}
      </div>

      {/* Trigger + Result badges */}
      <div className="flex flex-wrap gap-1 mb-2">
        {workflow.trigger?.type && (
          <span className="px-2 py-0.5 text-[10px] rounded bg-gray-700/60 text-gray-400 flex items-center gap-1">
            <span>{workflow.trigger.type === 'form' ? '📝' : workflow.trigger.type === 'schedule' ? '⏰' : '▶'}</span>
            <span>트리거</span>
          </span>
        )}
        {workflow.nodes.some(n => n.definitionType === 'result') && (
          <span className="px-2 py-0.5 text-[10px] rounded bg-emerald-900/60 text-emerald-400 flex items-center gap-1">
            <span>📊</span>
            <span>결과</span>
          </span>
        )}
      </div>

      {/* Tags */}
      <div className="flex flex-wrap gap-1 mb-3">
        {workflow.tags.map((tag) => (
          <span key={tag} className="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-400">
            #{tag}
          </span>
        ))}
      </div>

      {/* Dates */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span>수정: {new Date(workflow.updatedAt).toLocaleDateString('ko-KR')}</span>
      </div>
    </div>
  );
}

// ============================================
// Node Palette (AI Nodes)
// ============================================

const SYSTEM_NODE_DEFS = [
  { type: 'trigger' as const, definitionType: 'manual',   icon: '▶',  label: '수동 트리거',    desc: '수동으로 실행 시작',    bg: 'bg-gray-700',   border: 'border-gray-500',   text: 'text-gray-200'   },
  { type: 'trigger' as const, definitionType: 'form',     icon: '📝', label: '폼 트리거',      desc: '입력 폼으로 실행 시작', bg: 'bg-orange-900', border: 'border-orange-600', text: 'text-orange-200' },
  { type: 'trigger' as const, definitionType: 'schedule', icon: '⏰', label: '스케줄 트리거',  desc: '시간 기반 자동 실행',   bg: 'bg-purple-900', border: 'border-purple-600', text: 'text-purple-200' },
  { type: 'trigger' as const, definitionType: 'webhook',  icon: '🔗', label: 'Webhook 트리거', desc: '외부 요청으로 실행 시작',bg: 'bg-blue-900',   border: 'border-blue-600',   text: 'text-blue-200'   },
  { type: 'result'  as const, definitionType: 'result',   icon: '📊', label: '결과 출력',      desc: '워크플로우 최종 출력',  bg: 'bg-emerald-900',border: 'border-emerald-600',text: 'text-emerald-200'},
];

function NodePalette({ aiNodes }: { aiNodes: AINode[] }) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredNodes = searchQuery
    ? aiNodes.filter(
        (n) =>
          n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          n.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
          n.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : aiNodes;

  const onDragStart = (event: DragEvent, aiNode: AINode) => {
    event.dataTransfer.setData('application/ainode', JSON.stringify(aiNode));
    event.dataTransfer.effectAllowed = 'move';
  };

  const onSystemDragStart = (
    event: DragEvent,
    def: (typeof SYSTEM_NODE_DEFS)[number]
  ) => {
    event.dataTransfer.setData(
      'application/systemnode',
      JSON.stringify({ type: def.type, definitionType: def.definitionType })
    );
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <div className="w-72 bg-gray-800 border-r border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-gray-700">
        <h3 className="text-white font-semibold mb-2">노드 팔레트</h3>
        <input
          type="text"
          placeholder="AI 노드 검색..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* Node list */}
      <div className="flex-1 overflow-auto p-2 space-y-2">
        {/* System nodes section */}
        <div>
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-1 mb-1">
            시스템 노드
          </div>
          <div className="border-b border-gray-700 mb-2" />
          {SYSTEM_NODE_DEFS.map((def) => (
            <div
              key={def.definitionType}
              draggable
              onDragStart={(e) => onSystemDragStart(e, def)}
              className={`${def.bg} border ${def.border} hover:brightness-125 rounded-lg p-3 cursor-grab active:cursor-grabbing transition-all mb-2`}
            >
              <div className="flex items-center gap-2">
                <span className="text-xl">{def.icon}</span>
                <div>
                  <div className={`font-medium text-sm ${def.text}`}>{def.label}</div>
                  <div className="text-gray-400 text-xs">{def.desc}</div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* AI nodes section */}
        <div>
          <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-1 mb-1">
            AI 노드
          </div>
          <div className="border-b border-gray-700 mb-2" />
          {filteredNodes.map((node) => (
            <div
              key={node.id}
              draggable
              onDragStart={(e) => onDragStart(e, node)}
              className={`${node.color} bg-opacity-20 border border-gray-600 hover:border-gray-500 rounded-lg p-3 cursor-grab active:cursor-grabbing transition-colors mb-2`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xl p-1 rounded ${node.color}`}>{node.icon}</span>
                <div>
                  <div className="text-white font-medium text-sm">{node.name}</div>
                  <div className="text-gray-400 text-xs">{node.description}</div>
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-gray-700 text-gray-300">
                  {node.llmConfig?.model ?? 'default'}
                </span>
              </div>
            </div>
          ))}
          {filteredNodes.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-4">검색 결과가 없습니다</p>
          )}
        </div>
      </div>

      {/* Help text */}
      <div className="p-3 border-t border-gray-700 text-xs text-gray-500">
        노드를 드래그하여 캔버스에 배치하세요
      </div>
    </div>
  );
}

// ============================================
// Config Panel (Node Instance Settings)
// ============================================

function ConfigPanel({
  node,
  aiNodes,
  onUpdateNode,
  onDeleteNode,
  onClose,
}: {
  node: Node<CustomNodeData>;
  aiNodes: AINode[];
  onUpdateNode: (id: string, data: Partial<CustomNodeData>) => void;
  onDeleteNode: (id: string) => void;
  onClose: () => void;
}) {
  const aiNode = aiNodes.find(n => n.id === node.data.nodeId);

  if (!aiNode) return null;

  const inputFields = Object.entries(aiNode.inputSchema.properties);
  const outputFields = Object.entries(aiNode.outputSchema.properties);

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`text-xl p-2 rounded ${aiNode.color}`}>{aiNode.icon}</span>
          <div>
            <h3 className="text-white font-semibold">{node.data.instanceName}</h3>
            <p className="text-gray-400 text-xs">{aiNode.name}</p>
          </div>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">
          x
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-6">
        {/* Instance Name */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">인스턴스 이름</label>
          <input
            type="text"
            value={node.data.instanceName}
            onChange={(e) => onUpdateNode(node.id, { instanceName: e.target.value })}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Input Schema */}
        <div>
          <h4 className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-2">
            <span className="text-green-400">Input Schema</span>
          </h4>
          <div className="bg-gray-900 rounded-lg p-3 space-y-2">
            {inputFields.map(([key, prop]) => (
              <div key={key} className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{key}</span>
                <span className="text-gray-500 text-xs">{prop.type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Input Mapping */}
        <div>
          <h4 className="text-sm font-medium text-gray-300 mb-2">입력 매핑</h4>
          <div className="space-y-2">
            {inputFields.map(([key]) => (
              <div key={key}>
                <label className="block text-xs text-gray-500 mb-1">{key}</label>
                <input
                  type="text"
                  value={node.data.inputMapping?.[key] || ''}
                  onChange={(e) =>
                    onUpdateNode(node.id, {
                      inputMapping: {
                        ...node.data.inputMapping,
                        [key]: e.target.value,
                      },
                    })
                  }
                  placeholder={`{{prev.${key}}} 또는 값`}
                  className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 font-mono"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Output Schema */}
        <div>
          <h4 className="text-sm font-medium text-gray-300 mb-2 flex items-center gap-2">
            <span className="text-blue-400">Output Schema</span>
          </h4>
          <div className="bg-gray-900 rounded-lg p-3 space-y-2">
            {outputFields.map(([key, prop]) => (
              <div key={key} className="flex items-center justify-between text-sm">
                <span className="text-gray-300">{key}</span>
                <span className="text-gray-500 text-xs">{prop.type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Node Info */}
        <div className="pt-4 border-t border-gray-700">
          <h4 className="text-sm font-medium text-gray-300 mb-2">노드 정보</h4>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">LLM 모델</span>
              <span className="text-gray-300">{aiNode.llmConfig.model}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Temperature</span>
              <span className="text-gray-300">{aiNode.llmConfig.temperature}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Max Tokens</span>
              <span className="text-gray-300">{aiNode.llmConfig.maxTokens}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="p-4 border-t border-gray-700 flex gap-2">
        <button className="flex-1 px-3 py-2 bg-gray-700 text-gray-200 rounded hover:bg-gray-600 text-sm">
          복제
        </button>
        <button
          onClick={() => onDeleteNode(node.id)}
          className="flex-1 px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 text-sm"
        >
          삭제
        </button>
      </div>
    </div>
  );
}

// ============================================
// Execution Status Panel
// ============================================

function ExecutionStatusPanel({
  execution,
  nodeProgress,
  onClose,
}: {
  execution: WorkflowExecution | null;
  nodeProgress: NodeExecutionProgress[];
  onClose: () => void;
}) {
  if (!execution) return null;

  const statusColors: Record<string, string> = {
    pending: 'bg-gray-600 text-gray-300',
    running: 'bg-blue-600 text-blue-100',
    completed: 'bg-green-600 text-green-100',
    failed: 'bg-red-600 text-red-100',
    cancelled: 'bg-yellow-600 text-yellow-100',
    skipped: 'bg-gray-500 text-gray-300',
  };

  const statusLabels: Record<string, string> = {
    pending: '대기중',
    running: '실행중',
    completed: '완료',
    failed: '실패',
    cancelled: '취소됨',
    skipped: '건너뜀',
  };

  return (
    <div className="border-t border-gray-700 bg-gray-850 bg-gray-900">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <h4 className="text-sm font-semibold text-white">실행 상태</h4>
          <span
            className={`px-2 py-0.5 text-xs rounded ${statusColors[execution.status] || 'bg-gray-600 text-gray-300'}`}
          >
            {statusLabels[execution.status] || execution.status}
          </span>
          {execution.status === 'running' && <Spinner size="sm" />}
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-sm px-2">
          x
        </button>
      </div>

      {/* Node progress */}
      <div className="px-4 py-3 flex gap-3 overflow-x-auto">
        {nodeProgress.length === 0 ? (
          <p className="text-gray-500 text-sm">노드 실행 정보가 없습니다</p>
        ) : (
          nodeProgress.map((np) => (
            <div
              key={np.nodeInstanceId}
              className="flex-shrink-0 bg-gray-800 border border-gray-700 rounded-lg p-3 min-w-[180px] max-w-[300px]"
            >
              <div className="flex items-center gap-2 mb-2">
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    np.status === 'running'
                      ? 'bg-blue-400 animate-pulse'
                      : np.status === 'completed'
                        ? 'bg-green-400'
                        : np.status === 'failed'
                          ? 'bg-red-400'
                          : 'bg-gray-500'
                  }`}
                />
                <span className="text-white text-sm font-medium truncate">
                  {np.nodeInstanceId}
                </span>
              </div>
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={`px-2 py-0.5 text-xs rounded ${statusColors[np.status] || 'bg-gray-600 text-gray-300'}`}
                >
                  {statusLabels[np.status] || np.status}
                </span>
                {np.startedAt && np.completedAt && (
                  <span className="text-gray-500 text-[10px]">
                    {((new Date(np.completedAt).getTime() - new Date(np.startedAt).getTime()) / 1000).toFixed(1)}s
                  </span>
                )}
              </div>
              {np.error && <p className="text-red-400 text-xs mt-1 break-words">{np.error}</p>}
              {!!np.output && (
                <details className="mt-2">
                  <summary className="text-gray-400 text-xs cursor-pointer hover:text-gray-300">출력 데이터</summary>
                  <pre className="mt-1 text-[10px] text-gray-400 bg-gray-900 rounded p-2 overflow-auto max-h-32 whitespace-pre-wrap break-words">
                    {typeof np.output === 'string' ? np.output : JSON.stringify(np.output, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))
        )}
      </div>

      {/* Error message */}
      {execution.errorMessage && (
        <div className="px-4 pb-3">
          <div className="bg-red-900/30 border border-red-700 rounded p-2 text-red-300 text-xs">
            {execution.errorMessage}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================
// Execution History Panel
// ============================================

function ExecutionHistoryPanel({
  executions,
  loading,
  onClose,
  onSelectExecution,
}: {
  executions: WorkflowExecution[];
  loading: boolean;
  onClose: () => void;
  onSelectExecution: (exec: WorkflowExecution) => void;
}) {
  const statusColors: Record<string, string> = {
    pending: 'bg-gray-600 text-gray-300',
    running: 'bg-blue-600 text-blue-100',
    completed: 'bg-green-600 text-green-100',
    failed: 'bg-red-600 text-red-100',
    cancelled: 'bg-yellow-600 text-yellow-100',
  };

  const statusLabels: Record<string, string> = {
    pending: '대기중',
    running: '실행중',
    completed: '완료',
    failed: '실패',
    cancelled: '취소됨',
  };

  const getDuration = (exec: WorkflowExecution): string => {
    if (!exec.startedAt) return '-';
    const start = new Date(exec.startedAt).getTime();
    const end = exec.completedAt ? new Date(exec.completedAt).getTime() : Date.now();
    const diffMs = end - start;
    if (diffMs < 1000) return `${diffMs}ms`;
    if (diffMs < 60000) return `${(diffMs / 1000).toFixed(1)}s`;
    return `${Math.floor(diffMs / 60000)}m ${Math.floor((diffMs % 60000) / 1000)}s`;
  };

  return (
    <div className="w-80 bg-gray-800 border-l border-gray-700 flex flex-col">
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <h3 className="text-white font-semibold text-sm">실행 히스토리</h3>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-sm">
          x
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : executions.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-8">실행 기록이 없습니다</p>
        ) : (
          <div className="divide-y divide-gray-700">
            {executions.map((exec) => (
              <button
                key={exec.id}
                onClick={() => onSelectExecution(exec)}
                className="w-full text-left p-3 hover:bg-gray-750 hover:bg-gray-700/50 transition-colors"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-300 text-xs font-mono">
                    {exec.id.slice(0, 8)}...
                  </span>
                  <span
                    className={`px-2 py-0.5 text-[10px] rounded ${statusColors[exec.status] || 'bg-gray-600 text-gray-300'}`}
                  >
                    {statusLabels[exec.status] || exec.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span>
                    {exec.createdAt
                      ? new Date(exec.createdAt).toLocaleString('ko-KR', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '-'}
                  </span>
                  <span>{getDuration(exec)}</span>
                </div>
                {exec.errorMessage && (
                  <p className="text-red-400 text-xs mt-1 line-clamp-1">{exec.errorMessage}</p>
                )}
                {exec.nodeResults && Object.keys(exec.nodeResults).length > 0 && (
                  <div className="text-xs text-gray-500 mt-1">
                    {Object.keys(exec.nodeResults).length}개 노드 실행됨
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// Convert workflow to ReactFlow format
// ============================================

function workflowToReactFlow(workflow: Workflow): {
  nodes: Node<CustomNodeData>[];
  edges: Edge[];
} {
  const nodes: Node<CustomNodeData>[] = workflow.nodes.map((inst) => {
    const isTrigger = inst.definitionType && ['manual', 'schedule', 'webhook', 'form'].includes(inst.definitionType);
    const isResult = inst.definitionType === 'result';
    return {
      id: inst.id,
      type: isTrigger ? 'triggerNode' : isResult ? 'resultNode' : 'aiNode',
      position: inst.position,
      data: {
        nodeId: inst.nodeId,
        instanceName: inst.name,
        inputMapping: inst.inputMapping,
        definitionType: inst.definitionType,
        aiNodeId: inst.aiNodeId,
      },
    };
  });

  const edges: Edge[] = workflow.connections.map((conn) => ({
    id: conn.id,
    source: conn.sourceNodeId,
    sourceHandle: 'output',
    target: conn.targetNodeId,
    targetHandle: 'input',
    animated: true,
    style: { stroke: '#3b82f6', strokeWidth: 2 },
  }));

  return { nodes, edges };
}

// ============================================
// Convert ReactFlow back to Workflow format
// ============================================

function reactFlowToWorkflowData(
  nodes: Node<CustomNodeData>[],
  edges: Edge[]
): {
  nodes: Workflow['nodes'];
  connections: Workflow['connections'];
} {
  const workflowNodes = nodes.map((n) => ({
    id: n.id,
    nodeId: n.data.nodeId,
    definitionType: n.data.definitionType || 'ai-custom',
    aiNodeId: n.data.aiNodeId,
    name: n.data.instanceName,
    position: { x: n.position.x, y: n.position.y },
    inputMapping: n.data.inputMapping,
  }));

  const connections = edges.map((e) => ({
    id: e.id,
    sourceNodeId: e.source,
    targetNodeId: e.target,
  }));

  return { nodes: workflowNodes, connections };
}

// ============================================
// Workflow Editor
// ============================================

function WorkflowEditor({
  workflow,
  aiNodes,
  onBack,
  onWorkflowUpdated,
  onWorkflowDeleted,
}: {
  workflow: Workflow | null;
  aiNodes: AINode[];
  onBack: () => void;
  onWorkflowUpdated: (wf: Workflow) => void;
  onWorkflowDeleted: (id: string) => void;
}) {
  const { toast } = useToast();
  const { setWorkflowContext, clearContext } = useChatAssistant();
  const [workflowId] = useState(workflow?.id || '');
  const [workflowName, setWorkflowName] = useState(workflow?.name || '새 워크플로우');
  const [workflowDesc, setWorkflowDesc] = useState(workflow?.description || '');
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Execution state
  const [currentExecution, setCurrentExecution] = useState<WorkflowExecution | null>(null);
  const [nodeProgress, setNodeProgress] = useState<NodeExecutionProgress[]>([]);
  const [showExecutionPanel, setShowExecutionPanel] = useState(false);

  // Execution history
  const [showHistory, setShowHistory] = useState(false);
  const [executions, setExecutions] = useState<WorkflowExecution[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Trigger modal state
  const [triggerModalOpen, setTriggerModalOpen] = useState(false);
  const [selectedTriggerNode, setSelectedTriggerNode] = useState<Node<CustomNodeData> | null>(null);
  const [triggerConfig, setTriggerConfig] = useState(workflow?.trigger || { type: 'manual', config: {} });

  // Result modal state
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [selectedResultNode, setSelectedResultNode] = useState<Node<CustomNodeData> | null>(null);

  // SSE ref for cleanup
  const sseRef = useRef<EventSource | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Refs for getting current canvas state from child
  const getCanvasStateRef = useRef<
    (() => { nodes: Node<CustomNodeData>[]; edges: Edge[]; viewport: Viewport }) | null
  >(null);

  // Mark unsaved on name/desc changes
  useEffect(() => {
    if (workflow) {
      if (workflowName !== workflow.name || workflowDesc !== workflow.description) {
        setHasUnsavedChanges(true);
      }
    }
  }, [workflowName, workflowDesc, workflow]);

  // Cleanup SSE and poll timer on unmount
  useEffect(() => {
    return () => {
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  // ── Set chat context when workflow is being edited ──────────────

  useEffect(() => {
    if (workflow) {
      setWorkflowContext(workflow);
    }
    return () => {
      clearContext();
    };
  }, [workflow, setWorkflowContext, clearContext]);

  // Load execution history
  const loadHistory = useCallback(async () => {
    if (!workflowId) return;
    setLoadingHistory(true);
    try {
      const result = await workflowApi.listExecutions(workflowId);
      setExecutions(result);
    } catch {
      // API not available - show empty
      setExecutions([]);
    } finally {
      setLoadingHistory(false);
    }
  }, [workflowId]);

  // Toggle history panel
  const handleToggleHistory = useCallback(() => {
    if (!showHistory) {
      loadHistory();
    }
    setShowHistory((prev) => !prev);
  }, [showHistory, loadHistory]);

  // Save handler
  const handleSave = useCallback(async () => {
    if (!workflowId || !getCanvasStateRef.current) {
      toast.warning('저장할 워크플로우가 없습니다');
      return;
    }

    setSaving(true);
    try {
      const canvasState = getCanvasStateRef.current();
      const { nodes, connections } = reactFlowToWorkflowData(canvasState.nodes, canvasState.edges);

      const updatedWorkflow = await workflowApi.update(workflowId, {
        name: workflowName,
        description: workflowDesc,
        status: 'active',
        trigger: triggerConfig,
        nodes: nodes.map((n) => ({
          id: n.id,
          nodeId: n.nodeId,
          definitionType: n.definitionType,
          aiNodeId: n.aiNodeId,
          name: n.name,
          position: n.position,
          inputMapping: n.inputMapping,
        })),
        connections: connections.map((c) => ({
          id: c.id,
          sourceNodeId: c.sourceNodeId,
          targetNodeId: c.targetNodeId,
        })),
        viewport: canvasState.viewport,
      });

      onWorkflowUpdated(updatedWorkflow);
      setHasUnsavedChanges(false);
      toast.success('워크플로우가 저장되었습니다');
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`저장에 실패했습니다${detail ? `: ${detail}` : ''}. 백엔드 연결을 확인하세요.`);
    } finally {
      setSaving(false);
    }
  }, [workflowId, workflowName, workflowDesc, triggerConfig, toast, onWorkflowUpdated]);

  // Save trigger config handler
  const handleSaveTriggerConfig = useCallback((newTriggerConfig: { type: string; config: Record<string, unknown> }) => {
    setTriggerConfig(newTriggerConfig);
    setHasUnsavedChanges(true);
    toast.success('트리거 설정이 변경되었습니다. 저장 버튼을 눌러 적용하세요.');
    setTriggerModalOpen(false);
  }, [toast]);

  // Execute handler
  const handleExecute = useCallback(async (inputData?: Record<string, unknown>) => {
    if (!workflowId) {
      toast.warning('실행할 워크플로우가 없습니다');
      return;
    }

    setExecuting(true);
    setShowExecutionPanel(true);
    setNodeProgress([]);
    setCurrentExecution(null);

    try {
      const execution = await workflowApi.execute(workflowId, inputData || {});
      setCurrentExecution(execution);

      // Initialize node progress from workflow nodes
      if (workflow?.nodes) {
        setNodeProgress(
          workflow.nodes.map((n) => ({
            nodeInstanceId: n.id,
            status: 'pending' as NodeExecutionStatus,
          }))
        );
      }

      // Try SSE streaming for live updates
      try {
        const es = workflowApi.streamExecution(execution.id);
        sseRef.current = es;

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            // Update execution status (backend sends "status", not "executionStatus")
            if (data.status) {
              setCurrentExecution((prev) =>
                prev
                  ? {
                      ...prev,
                      status: data.status,
                      completedAt: data.completedAt,
                      errorMessage: data.error,
                    }
                  : prev
              );
            }

            // Update node progress from nodeResults dictionary
            if (data.nodeResults && typeof data.nodeResults === 'object') {
              setNodeProgress((prev) =>
                prev.map((np) => {
                  const result = (data.nodeResults as Record<string, Record<string, unknown>>)[
                    np.nodeInstanceId
                  ];
                  if (result) {
                    return {
                      ...np,
                      status: (result.status as NodeExecutionStatus) || np.status,
                      output: result.outputData,
                      error: result.error as string | undefined,
                      startedAt: (result.startTime as string) || np.startedAt,
                      completedAt: (result.endTime as string) || np.completedAt,
                    };
                  }
                  return np;
                })
              );
            }

            // Check if execution is done
            if (
              data.status === 'completed' ||
              data.status === 'failed' ||
              data.status === 'cancelled'
            ) {
              es.close();
              sseRef.current = null;
              setExecuting(false);

              if (data.status === 'completed') {
                toast.success('워크플로우 실행이 완료되었습니다');
              } else if (data.status === 'failed') {
                toast.error(`실행 실패: ${data.error || '알 수 없는 오류'}`);
              }
            }
          } catch {
            // Ignore parse errors from SSE
          }
        };

        es.onerror = () => {
          es.close();
          sseRef.current = null;
          // Fall back to polling if SSE fails
          pollExecutionStatus(execution.id);
        };
      } catch {
        // SSE not available, fall back to polling
        pollExecutionStatus(execution.id);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`워크플로우 실행에 실패했습니다${detail ? `: ${detail}` : ''}. 백엔드 연결을 확인하세요.`);
      setExecuting(false);
    }
  }, [workflowId, workflow, toast]);

  // Polling fallback for execution status
  const pollExecutionStatus = useCallback(
    async (executionId: string) => {
      const poll = async () => {
        try {
          const exec = await workflowApi.getExecution(executionId);
          setCurrentExecution(exec);

          // Update node progress from exec.nodeResults
          if (exec.nodeResults && typeof exec.nodeResults === 'object') {
            setNodeProgress((prev) =>
              prev.map((np) => {
                const result = (exec.nodeResults as Record<string, Record<string, unknown>>)[
                  np.nodeInstanceId
                ];
                if (result) {
                  return {
                    ...np,
                    status: (result.status as NodeExecutionStatus) || np.status,
                    output: result.outputData,
                    error: result.error as string | undefined,
                    startedAt: (result.startTime as string) || np.startedAt,
                    completedAt: (result.endTime as string) || np.completedAt,
                  };
                }
                return np;
              })
            );
          }

          if (
            exec.status === 'completed' ||
            exec.status === 'failed' ||
            exec.status === 'cancelled'
          ) {
            setExecuting(false);
            if (exec.status === 'completed') {
              toast.success('워크플로우 실행이 완료되었습니다');
            } else if (exec.status === 'failed') {
              toast.error(`실행 실패: ${exec.errorMessage || '알 수 없는 오류'}`);
            }
            return; // Stop polling
          }

          // Continue polling
          pollTimerRef.current = setTimeout(poll, 2000);
        } catch {
          setExecuting(false);
          pollTimerRef.current = null;
          // Stop polling on error
        }
      };

      pollTimerRef.current = setTimeout(poll, 1000);
    },
    [toast]
  );

  // Delete handler
  const handleDelete = useCallback(async () => {
    if (!workflowId) return;
    try {
      await workflowApi.delete(workflowId);
      onWorkflowDeleted(workflowId);
      toast.success('워크플로우가 삭제되었습니다');
      onBack();
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast.error(`삭제에 실패했습니다${detail ? `: ${detail}` : ''}. 백엔드 연결을 확인하세요.`);
    }
    setShowDeleteConfirm(false);
  }, [workflowId, onBack, onWorkflowDeleted, toast]);

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="px-3 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm"
          >
            &lt;- 목록
          </button>
          <div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={workflowName}
                onChange={(e) => {
                  setWorkflowName(e.target.value);
                  setHasUnsavedChanges(true);
                }}
                className="text-xl font-bold text-white bg-transparent border-b border-transparent hover:border-gray-600 focus:border-blue-500 focus:outline-none px-1"
              />
              {hasUnsavedChanges && (
                <span className="px-2 py-0.5 text-[10px] rounded bg-yellow-900 text-yellow-300">
                  미저장
                </span>
              )}
            </div>
            <input
              type="text"
              value={workflowDesc}
              onChange={(e) => {
                setWorkflowDesc(e.target.value);
                setHasUnsavedChanges(true);
              }}
              placeholder="워크플로우 설명..."
              className="block text-gray-400 text-sm bg-transparent border-b border-transparent hover:border-gray-600 focus:border-blue-500 focus:outline-none px-1 mt-1 w-96"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleHistory}
            className={`px-3 py-2 rounded-lg transition-colors text-sm ${
              showHistory
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700 text-gray-200 hover:bg-gray-600'
            }`}
          >
            히스토리
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="px-3 py-2 bg-gray-700 text-red-400 rounded-lg hover:bg-red-900 hover:text-red-200 transition-colors text-sm"
          >
            삭제
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-gray-700 text-gray-200 rounded-lg hover:bg-gray-600 transition-colors text-sm flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? <Spinner size="sm" /> : null}
            <span>저장</span>
          </button>
          <button
            onClick={() => handleExecute()}
            disabled={executing}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm flex items-center gap-2 disabled:opacity-50"
          >
            {executing ? <Spinner size="sm" /> : null}
            <span>실행</span>
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        <ReactFlowProvider>
          <NodePalette aiNodes={aiNodes} />
          <div className="flex-1 flex flex-col">
            <WorkflowCanvas
              initialWorkflow={workflow}
              aiNodes={aiNodes}
              onCanvasChange={() => setHasUnsavedChanges(true)}
              getCanvasStateRef={getCanvasStateRef}
              onTriggerNodeClick={(node) => {
                setSelectedTriggerNode(node);
                setTriggerModalOpen(true);
              }}
              onResultNodeClick={(node) => {
                setSelectedResultNode(node);
                setResultModalOpen(true);
              }}
            />
            {/* Execution Status Panel (bottom) */}
            {showExecutionPanel && (
              <ExecutionStatusPanel
                execution={currentExecution}
                nodeProgress={nodeProgress}
                onClose={() => setShowExecutionPanel(false)}
              />
            )}
          </div>
        </ReactFlowProvider>

        {/* Execution History Panel (right side) */}
        {showHistory && (
          <ExecutionHistoryPanel
            executions={executions}
            loading={loadingHistory}
            onClose={() => setShowHistory(false)}
            onSelectExecution={(exec) => {
              setCurrentExecution(exec);
              // Populate node progress from execution results
              if (exec.nodeResults && typeof exec.nodeResults === 'object') {
                const progress: NodeExecutionProgress[] = Object.entries(
                  exec.nodeResults as Record<string, Record<string, unknown>>
                ).map(([nodeId, result]) => ({
                  nodeInstanceId: nodeId,
                  status: (result.status as NodeExecutionStatus) || 'completed',
                  output: result.output,
                  error: result.error as string | undefined,
                }));
                setNodeProgress(progress);
              }
              setShowExecutionPanel(true);
            }}
          />
        )}
      </div>

      {/* Trigger Config Modal */}
      {triggerModalOpen && selectedTriggerNode && workflow && (
        <TriggerConfigModal
          isOpen={triggerModalOpen}
          onClose={() => {
            setTriggerModalOpen(false);
            setSelectedTriggerNode(null);
          }}
          triggerConfig={triggerConfig}
          triggerNode={selectedTriggerNode as any}
          triggerNodeId={selectedTriggerNode?.id ?? ''}
          allNodes={(getCanvasStateRef.current?.().nodes || []) as any[]}
          edges={getCanvasStateRef.current?.().edges || []}
          aiNodes={aiNodes}
          onSaveTrigger={handleSaveTriggerConfig}
          onExecute={(data) => {
            setTriggerModalOpen(false);
            handleExecute(data);
          }}
          executing={executing}
        />
      )}

      {/* Result View Modal */}
      {resultModalOpen && selectedResultNode && workflowId && (
        <ResultViewModal
          isOpen={resultModalOpen}
          onClose={() => {
            setResultModalOpen(false);
            setSelectedResultNode(null);
          }}
          resultNodeId={selectedResultNode.id}
          resultNodeName={selectedResultNode.data.instanceName}
          onReExecute={() => {
            setResultModalOpen(false);
            setSelectedResultNode(null);
            // Find trigger node and open trigger modal, or execute directly
            const triggerNode = getCanvasStateRef.current?.().nodes.find(
              n => n.type === 'triggerNode'
            );
            if (triggerNode) {
              setSelectedTriggerNode(triggerNode);
              setTriggerModalOpen(true);
            } else {
              handleExecute();
            }
          }}
        />
      )}

      <ConfirmDialog
        open={showDeleteConfirm}
        title="워크플로우 삭제"
        message="이 워크플로우를 삭제하시겠습니까? 모든 실행 기록도 함께 삭제됩니다."
        confirmLabel="삭제"
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
}

// ============================================
// Workflow Canvas
// ============================================

function WorkflowCanvas({
  initialWorkflow,
  aiNodes,
  onCanvasChange,
  getCanvasStateRef,
  onTriggerNodeClick,
  onResultNodeClick,
}: {
  initialWorkflow: Workflow | null;
  aiNodes: AINode[];
  onCanvasChange: () => void;
  getCanvasStateRef: React.MutableRefObject<
    (() => { nodes: Node<CustomNodeData>[]; edges: Edge[]; viewport: Viewport }) | null
  >;
  onTriggerNodeClick?: (node: Node<CustomNodeData>) => void;
  onResultNodeClick?: (node: Node<CustomNodeData>) => void;
}) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);

  const initialData = useMemo(() => {
    if (initialWorkflow) {
      return workflowToReactFlow(initialWorkflow);
    }
    return { nodes: [], edges: [] };
  }, [initialWorkflow]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CustomNodeData>>(initialData.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialData.edges);
  const [selectedNode, setSelectedNode] = useState<Node<CustomNodeData> | null>(null);
  const { screenToFlowPosition, getViewport } = useReactFlow();

  // Expose canvas state to parent
  useEffect(() => {
    getCanvasStateRef.current = () => ({
      nodes,
      edges,
      viewport: getViewport(),
    });
  }, [nodes, edges, getViewport, getCanvasStateRef]);

  const onConnect = useCallback(
    (params: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...params,
            animated: true,
            style: { stroke: '#3b82f6', strokeWidth: 2 },
          },
          eds
        )
      );
      onCanvasChange();
    },
    [setEdges, onCanvasChange]
  );

  const handleNodesChange: typeof onNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      // Mark as changed for position moves, additions, removals
      const hasSignificantChange = changes.some(
        (c) => c.type === 'position' || c.type === 'remove' || c.type === 'add'
      );
      if (hasSignificantChange) {
        onCanvasChange();
      }
    },
    [onNodesChange, onCanvasChange]
  );

  const handleEdgesChange: typeof onEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      if (changes.some((c) => c.type === 'remove' || c.type === 'add')) {
        onCanvasChange();
      }
    },
    [onEdgesChange, onCanvasChange]
  );

  const onDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      // Check for system node first
      const systemData = event.dataTransfer.getData('application/systemnode');
      if (systemData) {
        const { type, definitionType } = JSON.parse(systemData) as {
          type: 'trigger' | 'result';
          definitionType: string;
        };
        const position = screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });

        const instanceName =
          definitionType === 'manual'   ? '수동 트리거'    :
          definitionType === 'form'     ? '폼 트리거'      :
          definitionType === 'schedule' ? '스케줄 트리거'  :
          definitionType === 'webhook'  ? 'Webhook 트리거' :
          '결과 출력';

        const newNode: Node<CustomNodeData> = {
          id: `inst-${Date.now()}`,
          type: type === 'result' ? 'resultNode' : 'triggerNode',
          position,
          data: {
            nodeId: `system-${definitionType}`,
            instanceName,
            definitionType,
          },
        };

        setNodes((nds) => nds.concat(newNode));
        onCanvasChange();
        return;
      }

      // Then check for AI node
      const data = event.dataTransfer.getData('application/ainode');
      if (!data) return;

      const aiNode: AINode = JSON.parse(data);
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode: Node<CustomNodeData> = {
        id: `inst-${Date.now()}`,
        type: 'aiNode',
        position,
        data: {
          nodeId: aiNode.id,
          instanceName: aiNode.name,
          inputMapping: {},
        },
      };

      setNodes((nds) => nds.concat(newNode));
      setSelectedNode(newNode);
      onCanvasChange();
    },
    [screenToFlowPosition, setNodes, onCanvasChange]
  );

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node<CustomNodeData>) => {
    if (node.type === 'triggerNode' && onTriggerNodeClick) {
      onTriggerNodeClick(node);
    } else if (node.type === 'resultNode' && onResultNodeClick) {
      onResultNodeClick(node);
    } else {
      setSelectedNode(node);
    }
  }, [onTriggerNodeClick, onResultNodeClick]);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, []);

  const onUpdateNode = useCallback(
    (id: string, data: Partial<CustomNodeData>) => {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === id ? { ...node, data: { ...node.data, ...data } } : node
        )
      );
      setSelectedNode((prev) =>
        prev?.id === id ? { ...prev, data: { ...prev.data, ...data } } : prev
      );
      onCanvasChange();
    },
    [setNodes, onCanvasChange]
  );

  const onDeleteNode = useCallback(
    (id: string) => {
      setNodes((nds) => nds.filter((node) => node.id !== id));
      setEdges((eds) => eds.filter((edge) => edge.source !== id && edge.target !== id));
      setSelectedNode(null);
      onCanvasChange();
    },
    [setNodes, setEdges, onCanvasChange]
  );

  return (
    <div className="flex-1 flex">
      <div className="flex-1" ref={reactFlowWrapper}>
        <AINodesContext.Provider value={aiNodes}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            deleteKeyCode={['Delete', 'Backspace']}
            fitView
            snapToGrid
            snapGrid={[20, 20]}
            defaultEdgeOptions={{
              animated: true,
              style: { stroke: '#3b82f6', strokeWidth: 2 },
            }}
            connectionLineStyle={{ stroke: '#3b82f6', strokeWidth: 2 }}
            style={{ background: '#111827' }}
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
            <Controls className="bg-gray-800 border-gray-700" />
            <MiniMap
              nodeColor={(node) => {
                if (node.type === 'triggerNode') return '#6b21a8';
                if (node.type === 'resultNode') return '#047857';
                const nodeData = node.data as CustomNodeData;
                const aiNode = aiNodes.find(n => n.id === nodeData?.nodeId);
                if (!aiNode) return '#6b7280';
                const colorMap: Record<string, string> = {
                  'bg-blue-600': '#2563eb',
                  'bg-green-600': '#16a34a',
                  'bg-purple-600': '#9333ea',
                  'bg-pink-600': '#db2777',
                  'bg-yellow-600': '#ca8a04',
                  'bg-red-600': '#dc2626',
                  'bg-orange-600': '#ea580c',
                };
                return colorMap[aiNode.color] || '#6b7280';
              }}
              style={{ background: '#1f2937' }}
            />
          </ReactFlow>
        </AINodesContext.Provider>
      </div>

      {selectedNode && (
        <ConfigPanel
          node={selectedNode}
          aiNodes={aiNodes}
          onUpdateNode={onUpdateNode}
          onDeleteNode={onDeleteNode}
          onClose={() => setSelectedNode(null)}
        />
      )}
    </div>
  );
}

// ============================================
// Main Page
// ============================================

export function WorkflowPage() {
  const { toast } = useToast();
  const { onDataChange, setMode } = useChatContext();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [aiNodes, setAINodes] = useState<AINode[]>(mockAINodes);
  const [editingWorkflow, setEditingWorkflow] = useState<Workflow | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    document.title = '워크플로우 | AI 업무도우미';
  }, []);

  useEffect(() => {
    setMode('workflow');
    return () => setMode('general');
  }, [setMode]);

  // Load workflows and AI nodes on mount
  const loadData = useCallback(async () => {
    setLoading(true);

    // Load workflows
    let loadedWorkflows: Workflow[] = [];
    let usedMockWorkflows = false;
    try {
      const summaries: WorkflowSummary[] = await workflowApi.list();
      // Fetch full workflow details for each summary
      const fullWorkflows = await Promise.all(
        summaries.map(async (s) => {
          try {
            return await workflowApi.get(s.id);
          } catch {
            return null;
          }
        })
      );
      loadedWorkflows = fullWorkflows.filter((w): w is Workflow => w !== null);
    } catch {
      loadedWorkflows = [...mockWorkflows];
      usedMockWorkflows = true;
    }

    // Load AI nodes
    let loadedNodes: AINode[] = [];
    let usedMockNodes = false;
    try {
      loadedNodes = await nodeApi.list();
    } catch {
      loadedNodes = [...mockAINodes];
      usedMockNodes = true;
    }

    setWorkflows(loadedWorkflows);
    setAINodes(loadedNodes);
    setLoading(false);

    if (usedMockWorkflows || usedMockNodes) {
      toast.info(
        '백엔드 서버에 연결할 수 없어 샘플 데이터를 사용합니다. API 서버를 시작하면 실제 데이터를 사용할 수 있습니다.'
      );
    }
  }, [toast]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    return onDataChange((target) => {
      if (target.includes('workflow')) loadData();
    });
  }, [onDataChange, loadData]);

  // Create new workflow
  const handleCreateNew = useCallback(async () => {
    setCreating(true);
    try {
      const newWorkflow = await workflowApi.create({
        name: '새 워크플로우',
        description: '',
        tags: [],
        trigger: { type: 'manual', config: {} },
        variables: {},
        nodes: [],
        connections: [],
      });
      setWorkflows((prev) => [newWorkflow, ...prev]);
      setEditingWorkflow(newWorkflow);
      setIsEditorOpen(true);
      toast.success('새 워크플로우가 생성되었습니다');
    } catch {
      // API not available - create a local-only workflow
      const localWorkflow: Workflow = {
        id: `wf-local-${Date.now()}`,
        name: '새 워크플로우',
        description: '',
        nodes: [],
        connections: [],
        variables: {},
        trigger: { type: 'manual', config: {} },
        tags: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      setWorkflows((prev) => [localWorkflow, ...prev]);
      setEditingWorkflow(localWorkflow);
      setIsEditorOpen(true);
      toast.warning(
        '오프라인 모드: 로컬에서만 워크플로우가 생성되었습니다. 저장/실행은 백엔드 서버가 필요합니다.'
      );
    } finally {
      setCreating(false);
    }
  }, [toast]);

  // ── Keyboard shortcuts ────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) {
        if (e.key === 'Escape') {
          target.blur();
        }
        return;
      }

      if (e.key === 'Escape') {
        if (isEditorOpen) {
          setIsEditorOpen(false);
          setEditingWorkflow(null);
        }
      }

      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        if (!isEditorOpen && !creating) {
          handleCreateNew();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isEditorOpen, creating, handleCreateNew]);

  // Select workflow for editing
  const handleSelectWorkflow = useCallback(
    async (workflow: Workflow) => {
      // Try to get the latest version from API
      try {
        const latest = await workflowApi.get(workflow.id);
        setEditingWorkflow(latest);
      } catch {
        // Use the local version
        setEditingWorkflow(workflow);
      }
      setIsEditorOpen(true);
    },
    []
  );

  // Delete workflow
  const handleDeleteWorkflow = useCallback(
    async (id: string) => {
      try {
        await workflowApi.delete(id);
        toast.success('워크플로우가 삭제되었습니다');
      } catch {
        toast.info('서버에서 삭제할 수 없어 로컬에서만 제거합니다');
      }
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
    },
    [toast]
  );

  // Handle workflow updated from editor
  const handleWorkflowUpdated = useCallback((updatedWf: Workflow) => {
    setWorkflows((prev) => prev.map((w) => (w.id === updatedWf.id ? updatedWf : w)));
    setEditingWorkflow(updatedWf);
  }, []);

  // Handle workflow deleted from editor
  const handleWorkflowDeleted = useCallback((id: string) => {
    setWorkflows((prev) => prev.filter((w) => w.id !== id));
  }, []);

  const handleBack = useCallback(() => {
    setIsEditorOpen(false);
    setEditingWorkflow(null);
  }, []);

  if (isEditorOpen) {
    return (
      <WorkflowEditor
        workflow={editingWorkflow}
        aiNodes={aiNodes}
        onBack={handleBack}
        onWorkflowUpdated={handleWorkflowUpdated}
        onWorkflowDeleted={handleWorkflowDeleted}
      />
    );
  }

  return (
    <WorkflowListView
      workflows={workflows}
      aiNodes={aiNodes}
      loading={loading || creating}
      onSelectWorkflow={handleSelectWorkflow}
      onCreateNew={handleCreateNew}
      onDeleteWorkflow={handleDeleteWorkflow}
    />
  );
}
