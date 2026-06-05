import { nodeRegistry } from './registry';

// 노드 컴포넌트 import
import { FormStartNode } from '../components/workflow/FormStartNode';
import { ApiStartNode } from '../components/workflow/ApiStartNode';
import { FactoryNode } from '../components/workflow/FactoryNode';
import { WarehouseNode } from '../components/workflow/WarehouseNode';
import { SorterNode } from '../components/workflow/SorterNode';
import { ApiCallNode } from '../components/workflow/ApiCallNode';
import { UnpackerNode } from '../components/workflow/UnpackerNode';
import { MapperNode } from '../components/workflow/MapperNode';
import { KnowledgeNode } from '../components/workflow/KnowledgeNode';
import { MarkdownViewerNode } from '../components/workflow/MarkdownViewerNode';
import { AiApiRouterNode } from '../components/workflow/AiApiRouterNode';
import { InstanceDbInsertNode } from '../components/workflow/InstanceDbInsertNode';

import { DEF_TYPE } from '../constants/workflow';

// ReactFlow는 Node 객체에 position 필드를 요구한다. position 데이터는 DB/API에 저장되지 않으며,
// 자동 레이아웃(dagre)로 런타임에만 주입된다. createNodeData 반환값에는 임시 기본값 {x:0,y:0}만 넣는다.
// Phase 3c 정리: 편집 UI가 제거되어 createNodeData 호출부는 현재 없다. 레거시 호환용.
const DEFAULT_POSITION = { x: 0, y: 0 };

// --- Starter ---

nodeRegistry.register({
  defType: DEF_TYPE.FORM_START,
  category: 'starter',
  reactFlowType: 'formStartNode',
  component: FormStartNode,
  minimapColor: '#d97706',
  palette: {
    icon: '\u{1F4CB}',
    label: '\uD3FC \uC785\uB825 \uC2DC\uC791',
    description: '\uD3FC\uC73C\uB85C \uC6D0\uB8CC \uC0DD\uC131',
    bg: 'from-amber-700 to-amber-900',
    border: 'border-amber-500',
    textColor: 'text-amber-100',
    descColor: 'text-amber-300/60',
  },
  createNodeData: (id) => ({
    id,
    type: 'formStartNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.FORM_START,
      instanceName: '\uD3FC \uC785\uB825 \uC2DC\uC791',
      definitionType: DEF_TYPE.FORM_START,
      config: { mode: 'manual' },
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
});

nodeRegistry.register({
  defType: DEF_TYPE.API_START,
  category: 'starter',
  reactFlowType: 'apiStartNode',
  component: ApiStartNode,
  minimapColor: '#0d9488',
  palette: {
    icon: '\u{1F680}',
    label: 'API \uD638\uCD9C \uC2DC\uC791',
    description: 'API \uD638\uCD9C\uB85C \uC6D0\uB8CC \uC0DD\uC131',
    bg: 'from-teal-700 to-teal-900',
    border: 'border-teal-500',
    textColor: 'text-teal-100',
    descColor: 'text-teal-300/60',
  },
  createNodeData: (id) => ({
    id,
    type: 'apiStartNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.API_START,
      instanceName: 'API \uD638\uCD9C \uC2DC\uC791',
      definitionType: DEF_TYPE.API_START,
      config: { mode: 'manual' },
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'status', type: 'number' },
    { name: 'data', type: 'object' },
  ],
});

// --- AI ---

nodeRegistry.register({
  defType: DEF_TYPE.AI_CUSTOM,
  category: 'ai',
  reactFlowType: 'factoryNode',
  component: FactoryNode,
  minimapColor: '#475569',
  palette: {
    icon: '🤖',
    label: 'AI 노드',
    description: '커스텀 AI 노드',
    bg: 'from-blue-700 to-blue-900',
    border: 'border-blue-500',
    textColor: 'text-blue-100',
    descColor: 'text-blue-300/60',
  },
  // AI 노드는 팔레트에서 별도 처리 (aiNodes 목록에서 드래그)
  createNodeData: (id, extra?: { aiNode: { id: string; name: string } }) => ({
    id,
    type: 'factoryNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: extra?.aiNode.id || '',
      instanceName: extra?.aiNode.name || 'AI \uB178\uB4DC',
      definitionType: DEF_TYPE.AI_CUSTOM,
      aiNodeId: extra?.aiNode.id || '',
      inputMapping: {},
    },
  }),
});

nodeRegistry.register({
  defType: DEF_TYPE.AI_API_ROUTER,
  category: 'action',
  reactFlowType: 'aiApiRouterNode',
  component: AiApiRouterNode,
  minimapColor: '#7c3aed',
  palette: {
    icon: '🤖',
    label: 'AI API 라우터',
    description: 'AI가 판단하여 적절한 API 자동 호출',
    bg: 'from-purple-700 to-purple-900',
    border: 'border-purple-500',
    textColor: 'text-purple-100',
    descColor: 'text-purple-300/60',
  },
  createNodeData: (id) => ({
    id,
    type: 'aiApiRouterNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.AI_API_ROUTER,
      instanceName: 'AI API 라우터',
      definitionType: DEF_TYPE.AI_API_ROUTER,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'api_route', type: 'object' },
  ],
});

// --- Logic ---

nodeRegistry.register({
  defType: DEF_TYPE.SORTER,
  category: 'logic',
  reactFlowType: 'sorterNode',
  component: SorterNode,
  minimapColor: '#7c3aed',
  defaultSourceHandle: 'default',
  palette: {
    icon: '\u{1F500}',
    label: '\uBD84\uB958\uAE30',
    description: '\uC870\uAC74\uBCC4 \uBD84\uAE30 + \uB370\uC774\uD130 \uBCF4\uAD00',
    bg: 'from-violet-700 to-violet-900',
    border: 'border-violet-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'sorterNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.SORTER,
      instanceName: '\uBD84\uB958\uAE30',
      definitionType: DEF_TYPE.SORTER,
      config: { rules: [] },
    },
  }),
  defaultData: (inst) => ({ config: inst.config || { rules: [] } }),
});

nodeRegistry.register({
  defType: DEF_TYPE.UNPACKER,
  category: 'logic',
  reactFlowType: 'unpackerNode',
  component: UnpackerNode,
  minimapColor: '#e11d48',
  palette: {
    icon: '\u{1F4E4}',
    label: '\uC5B8\uD328\uCEE4',
    description: '\uBC30\uC5F4\uC744 \uAC1C\uBCC4 \uAC1D\uCCB4\uB85C \uBD84\uBC30',
    bg: 'from-rose-700 to-rose-900',
    border: 'border-rose-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'unpackerNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.UNPACKER,
      instanceName: '\uC5B8\uD328\uCEE4',
      definitionType: DEF_TYPE.UNPACKER,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
});

nodeRegistry.register({
  defType: DEF_TYPE.MAPPER,
  category: 'logic',
  reactFlowType: 'mapperNode',
  component: MapperNode,
  minimapColor: '#6366f1',
  palette: {
    icon: '\u{1F517}',
    label: '\uB9E4\uD37C',
    description: '\uCC3D\uACE0 \uB370\uC774\uD130\uC640 \uD0A4 \uAE30\uBC18 \uBCD1\uD569',
    bg: 'from-indigo-700 to-indigo-900',
    border: 'border-indigo-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'mapperNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.MAPPER,
      instanceName: '\uB9E4\uD37C',
      definitionType: DEF_TYPE.MAPPER,
      config: { outputField: 'matchedItems' },
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || { outputField: 'matchedItems' } }),
  staticOutputFields: [
    { name: 'matchedItems', type: 'array' },
    { name: 'matchedCount', type: 'number' },
  ],
});

// --- Action ---

nodeRegistry.register({
  defType: DEF_TYPE.API_CALL,
  category: 'action',
  reactFlowType: 'apiCallNode',
  component: ApiCallNode,
  minimapColor: '#0891b2',
  palette: {
    icon: '\u{1F310}',
    label: 'API \uD638\uCD9C\uAE30',
    description: '\uBB38\uC11C \uAE30\uBC18 API \uC9C1\uC811 \uD638\uCD9C',
    bg: 'from-cyan-700 to-cyan-900',
    border: 'border-cyan-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'apiCallNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.API_CALL,
      instanceName: 'API \uD638\uCD9C\uAE30',
      definitionType: DEF_TYPE.API_CALL,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'status', type: 'number' },
    { name: 'data', type: 'object' },
  ],
});

nodeRegistry.register({
  defType: DEF_TYPE.KNOWLEDGE,
  category: 'action',
  reactFlowType: 'knowledgeNode',
  component: KnowledgeNode,
  minimapColor: '#6366f1',
  palette: {
    icon: '\u{1F4DA}',
    label: '\uC9C0\uC2DD \uAC80\uC0C9',
    description: '\uC9C0\uC2DD \uBCA0\uC774\uC2A4\uC5D0\uC11C \uAD00\uB828 \uBB38\uC11C \uAC80\uC0C9',
    bg: 'from-indigo-700 to-indigo-900',
    border: 'border-indigo-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'knowledgeNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.KNOWLEDGE,
      instanceName: '\uC9C0\uC2DD \uAC80\uC0C9',
      definitionType: DEF_TYPE.KNOWLEDGE,
      config: { maxResults: 5 },
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [{ name: 'knowledge', type: 'array' }],
});

// --- InstanceDB Action ---

nodeRegistry.register({
  defType: DEF_TYPE.INSTANCE_DB_INSERT,
  category: 'action',
  reactFlowType: 'instanceDbInsertNode',
  component: InstanceDbInsertNode,
  minimapColor: '#0f766e',
  palette: {
    icon: '📥',
    label: '인스턴스DB 적재',
    description: '인스턴스DB에 레코드 적재',
    bg: 'from-teal-700 to-teal-900',
    border: 'border-teal-500',
    textColor: 'text-teal-100',
    descColor: 'text-teal-300/60',
  },
  createNodeData: (id) => ({
    id,
    type: 'instanceDbInsertNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.INSTANCE_DB_INSERT,
      instanceName: '인스턴스DB 적재',
      definitionType: DEF_TYPE.INSTANCE_DB_INSERT,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'record_id', type: 'string' },
    { name: 'inserted', type: 'boolean' },
  ],
});

nodeRegistry.register({
  defType: DEF_TYPE.INSTANCE_DB_LOOKUP,
  category: 'action',
  reactFlowType: 'instanceDbLookupNode',
  component: FactoryNode,
  minimapColor: '#0e7490',
  palette: {
    icon: '🔍',
    label: '인스턴스DB 조회',
    description: '인스턴스DB에서 레코드 조회',
    bg: 'from-cyan-700 to-cyan-900',
    border: 'border-cyan-500',
    textColor: 'text-cyan-100',
    descColor: 'text-cyan-300/60',
  },
  createNodeData: (id) => ({
    id,
    type: 'instanceDbLookupNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.INSTANCE_DB_LOOKUP,
      instanceName: '인스턴스DB 조회',
      definitionType: DEF_TYPE.INSTANCE_DB_LOOKUP,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'records', type: 'array' },
    { name: 'total', type: 'number' },
  ],
});

// --- Output ---

nodeRegistry.register({
  defType: DEF_TYPE.RESULT,
  category: 'output',
  reactFlowType: 'warehouseNode',
  component: WarehouseNode,
  minimapColor: '#059669',
  palette: {
    icon: '\u{1F4E6}',
    label: '\uACB0\uACFC\uCC3D\uACE0',
    description: '\uC2E4\uD589 \uACB0\uACFC\uBB3C \uCD95\uC801',
    bg: 'from-emerald-700 to-emerald-900',
    border: 'border-emerald-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'warehouseNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.RESULT,
      instanceName: '\uACB0\uACFC\uCC3D\uACE0',
      definitionType: DEF_TYPE.RESULT,
    },
  }),
});

nodeRegistry.register({
  defType: DEF_TYPE.MARKDOWN_VIEWER,
  category: 'output',
  reactFlowType: 'markdownViewerNode',
  component: MarkdownViewerNode,
  minimapColor: '#6366f1',
  palette: {
    icon: '\u{1F4DD}',
    label: '\uB9C8\uD06C\uB2E4\uC6B4 \uBDF0\uC5B4',
    description: '\uB9C8\uD06C\uB2E4\uC6B4 \uD615\uC2DD\uC73C\uB85C \uACB0\uACFC \uD45C\uC2DC',
    bg: 'from-slate-700 to-slate-900',
    border: 'border-slate-500',
  },
  createNodeData: (id) => ({
    id,
    type: 'markdownViewerNode',
    position: DEFAULT_POSITION,
    data: {
      nodeId: DEF_TYPE.MARKDOWN_VIEWER,
      instanceName: '\uB9C8\uD06C\uB2E4\uC6B4 \uBDF0\uC5B4',
      definitionType: DEF_TYPE.MARKDOWN_VIEWER,
      config: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
});
