import { nodeRegistry } from './registry';

// 노드 컴포넌트 import
import { FormStartNode } from '../components/workflow/FormStartNode';
import { ApiStartNode } from '../components/workflow/ApiStartNode';
import { FactoryNode } from '../components/workflow/FactoryNode';
import { WarehouseNode } from '../components/workflow/WarehouseNode';
import { SorterNode } from '../components/workflow/SorterNode';
import { ApiCallNode } from '../components/workflow/ApiCallNode';
import { UnpackerNode } from '../components/workflow/UnpackerNode';
import { KnowledgeNode } from '../components/workflow/KnowledgeNode';
import { MarkdownViewerNode } from '../components/workflow/MarkdownViewerNode';

// 설정 패널 컴포넌트 import
import { FormStartConfigPanel } from '../components/workflow/FormStartConfigPanel';
import { ApiStartConfigPanel } from '../components/workflow/ApiStartConfigPanel';
import { SorterConfigPanel } from '../components/workflow/SorterConfigPanel';
import { ApiCallConfigPanel } from '../components/workflow/ApiCallConfigPanel';
import { UnpackerConfigPanel } from '../components/workflow/UnpackerConfigPanel';
import { KnowledgeConfigPanel } from '../components/workflow/KnowledgeConfigPanel';
import { SystemNodePanel } from '../components/workflow/SystemNodePanel';
import { MarkdownViewerConfigPanel } from '../components/workflow/MarkdownViewerConfigPanel';

import { DEF_TYPE } from '../constants/workflow';

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
    dragType: 'application/starternode',
  },
  panelBehavior: { onClick: 'config' },
  configPanel: FormStartConfigPanel as any,
  createNodeData: (id, position) => ({
    id,
    type: 'formStartNode',
    position,
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
    dragType: 'application/starternode',
  },
  panelBehavior: { onClick: 'config' },
  configPanel: ApiStartConfigPanel as any,
  createNodeData: (id, position) => ({
    id,
    type: 'apiStartNode',
    position,
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
  panelBehavior: { onClick: 'queue', onDoubleClick: 'detail' },
  // AI 노드는 팔레트에서 별도 처리 (aiNodes 목록에서 드래그)
  createNodeData: (id, position, extra?: { aiNode: { id: string; name: string } }) => ({
    id,
    type: 'factoryNode',
    position,
    data: {
      nodeId: extra?.aiNode.id || '',
      instanceName: extra?.aiNode.name || 'AI \uB178\uB4DC',
      definitionType: DEF_TYPE.AI_CUSTOM,
      aiNodeId: extra?.aiNode.id || '',
      inputMapping: {},
    },
  }),
});

// --- Logic ---

nodeRegistry.register({
  defType: DEF_TYPE.SORTER,
  category: 'logic',
  reactFlowType: 'sorterNode',
  component: SorterNode,
  minimapColor: '#7c3aed',
  defaultSourceHandle: 'default',
  panelBehavior: { onClick: 'config', onDoubleClick: 'result-modal' },
  configPanel: SorterConfigPanel as any,
  palette: {
    icon: '\u{1F500}',
    label: '\uBD84\uB958\uAE30',
    description: '\uC870\uAC74\uBCC4 \uBD84\uAE30 + \uB370\uC774\uD130 \uBCF4\uAD00',
    bg: 'from-violet-700 to-violet-900',
    border: 'border-violet-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'sorterNode',
    position,
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
  panelBehavior: { onClick: 'config' },
  configPanel: UnpackerConfigPanel as any,
  palette: {
    icon: '\u{1F4E4}',
    label: '\uC5B8\uD328\uCEE4',
    description: '\uBC30\uC5F4\uC744 \uAC1C\uBCC4 \uAC1D\uCCB4\uB85C \uBD84\uBC30',
    bg: 'from-rose-700 to-rose-900',
    border: 'border-rose-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'unpackerNode',
    position,
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

// --- Action ---

nodeRegistry.register({
  defType: DEF_TYPE.API_CALL,
  category: 'action',
  reactFlowType: 'apiCallNode',
  component: ApiCallNode,
  minimapColor: '#0891b2',
  panelBehavior: { onClick: 'config', onDoubleClick: 'result-modal' },
  configPanel: ApiCallConfigPanel as any,
  palette: {
    icon: '\u{1F310}',
    label: 'API \uD638\uCD9C\uAE30',
    description: '\uBB38\uC11C \uAE30\uBC18 API \uC9C1\uC811 \uD638\uCD9C',
    bg: 'from-cyan-700 to-cyan-900',
    border: 'border-cyan-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'apiCallNode',
    position,
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
  panelBehavior: { onClick: 'config' },
  configPanel: KnowledgeConfigPanel as any,
  palette: {
    icon: '\u{1F4DA}',
    label: '\uC9C0\uC2DD \uAC80\uC0C9',
    description: '\uC9C0\uC2DD \uBCA0\uC774\uC2A4\uC5D0\uC11C \uAD00\uB828 \uBB38\uC11C \uAC80\uC0C9',
    bg: 'from-indigo-700 to-indigo-900',
    border: 'border-indigo-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'knowledgeNode',
    position,
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

// --- Output ---

nodeRegistry.register({
  defType: DEF_TYPE.RESULT,
  category: 'output',
  reactFlowType: 'warehouseNode',
  component: WarehouseNode,
  minimapColor: '#059669',
  panelBehavior: { onClick: 'warehouse', onDoubleClick: 'result-modal' },
  palette: {
    icon: '\u{1F4E6}',
    label: '\uCC3D\uACE0',
    description: '\uAC00\uACF5 \uACB0\uACFC\uBB3C \uCD95\uC801',
    bg: 'from-emerald-700 to-emerald-900',
    border: 'border-emerald-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'warehouseNode',
    position,
    data: {
      nodeId: DEF_TYPE.RESULT,
      instanceName: '\uCC3D\uACE0',
      definitionType: DEF_TYPE.RESULT,
    },
  }),
});

nodeRegistry.register({
  defType: DEF_TYPE.DELIVERABLE_GENERATOR,
  category: 'action',
  reactFlowType: 'factoryNode',
  component: FactoryNode,
  minimapColor: '#b45309',
  panelBehavior: { onClick: 'config' },
  configPanel: SystemNodePanel as any,
  palette: {
    icon: '\u{1F4CB}',
    label: '\uC0B0\uCD9C\uBB3C \uC0DD\uC131\uAE30',
    description: 'GitHub \uB9C8\uC77C\uC2A4\uD1A4 \uAE30\uBC18 \uC0B0\uCD9C\uBB3C \uC790\uB3D9 \uC0DD\uC131',
    bg: 'from-amber-700 to-amber-900',
    border: 'border-amber-500',
    textColor: 'text-amber-100',
    descColor: 'text-amber-300/60',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'factoryNode',
    position,
    data: {
      nodeId: DEF_TYPE.DELIVERABLE_GENERATOR,
      instanceName: '\uC0B0\uCD9C\uBB3C \uC0DD\uC131\uAE30',
      definitionType: DEF_TYPE.DELIVERABLE_GENERATOR,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'markdown', type: 'string' },
    { name: 'dev_deliverable', type: 'string' },
    { name: 'review_deliverable', type: 'string' },
    { name: 'milestone_title', type: 'string' },
    { name: 'pr_count', type: 'number' },
    { name: 'total_additions', type: 'number' },
    { name: 'total_deletions', type: 'number' },
    { name: 'review_count', type: 'number' },
  ],
});

// --- 산출물 파이프라인 (3-step) ---

nodeRegistry.register({
  defType: DEF_TYPE.MILESTONE_COLLECTOR,
  category: 'action',
  reactFlowType: 'factoryNode',
  component: FactoryNode,
  minimapColor: '#0891b2',
  panelBehavior: { onClick: 'config' },
  configPanel: SystemNodePanel as any,
  palette: {
    icon: '\uD83D\uDD0D',
    label: '\uB9C8\uC77C\uC2A4\uD1A4 \uC218\uC9D1',
    description: 'GitHub \uB9C8\uC77C\uC2A4\uD1A4 PR/\uD30C\uC77C/\uB9AC\uBDF0 \uC218\uC9D1',
    bg: 'from-cyan-700 to-cyan-900',
    border: 'border-cyan-500',
    textColor: 'text-cyan-100',
    descColor: 'text-cyan-300/60',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'factoryNode',
    position,
    data: {
      nodeId: DEF_TYPE.MILESTONE_COLLECTOR,
      instanceName: '\uB9C8\uC77C\uC2A4\uD1A4 \uC218\uC9D1',
      definitionType: DEF_TYPE.MILESTONE_COLLECTOR,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'owner', type: 'string' },
    { name: 'repo', type: 'string' },
    { name: 'milestone_title', type: 'string' },
    { name: 'milestone_number', type: 'number' },
    { name: 'pr_count', type: 'number' },
    { name: 'prs', type: 'array' },
  ],
});

nodeRegistry.register({
  defType: DEF_TYPE.DEV_DELIVERABLE_GEN,
  category: 'action',
  reactFlowType: 'factoryNode',
  component: FactoryNode,
  minimapColor: '#2563eb',
  panelBehavior: { onClick: 'config' },
  configPanel: SystemNodePanel as any,
  palette: {
    icon: '\uD83D\uDCC4',
    label: '\uAC1C\uBC1C\uC0B0\uCD9C\uBB3C \uC0DD\uC131',
    description: 'PR \uBCC0\uACBD\uB0B4\uC5ED \uAE30\uBC18 \uAC1C\uBC1C\uC0B0\uCD9C\uBB3C \uBB38\uC11C \uC0DD\uC131',
    bg: 'from-blue-700 to-blue-900',
    border: 'border-blue-500',
    textColor: 'text-blue-100',
    descColor: 'text-blue-300/60',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'factoryNode',
    position,
    data: {
      nodeId: DEF_TYPE.DEV_DELIVERABLE_GEN,
      instanceName: '\uAC1C\uBC1C\uC0B0\uCD9C\uBB3C \uC0DD\uC131',
      definitionType: DEF_TYPE.DEV_DELIVERABLE_GEN,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'dev_deliverable', type: 'string' },
    { name: 'total_additions', type: 'number' },
    { name: 'total_deletions', type: 'number' },
    { name: 'total_files', type: 'number' },
    { name: 'owner', type: 'string' },
    { name: 'repo', type: 'string' },
    { name: 'milestone_title', type: 'string' },
    { name: 'milestone_number', type: 'number' },
    { name: 'pr_count', type: 'number' },
    { name: 'prs', type: 'array' },
  ],
});

nodeRegistry.register({
  defType: DEF_TYPE.REVIEW_DELIVERABLE_GEN,
  category: 'action',
  reactFlowType: 'factoryNode',
  component: FactoryNode,
  minimapColor: '#7c3aed',
  panelBehavior: { onClick: 'config' },
  configPanel: SystemNodePanel as any,
  palette: {
    icon: '\uD83D\uDCDD',
    label: '\uCF54\uB4DC\uB9AC\uBDF0\uC0B0\uCD9C\uBB3C \uC0DD\uC131',
    description: '\uB9AC\uBDF0 \uCF54\uBA58\uD2B8 \uBD84\uB958 \uBC0F \uC0B0\uCD9C\uBB3C \uBB38\uC11C \uC0DD\uC131',
    bg: 'from-purple-700 to-purple-900',
    border: 'border-purple-500',
    textColor: 'text-purple-100',
    descColor: 'text-purple-300/60',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'factoryNode',
    position,
    data: {
      nodeId: DEF_TYPE.REVIEW_DELIVERABLE_GEN,
      instanceName: '\uCF54\uB4DC\uB9AC\uBDF0\uC0B0\uCD9C\uBB3C \uC0DD\uC131',
      definitionType: DEF_TYPE.REVIEW_DELIVERABLE_GEN,
      config: {},
      inputMapping: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
  staticOutputFields: [
    { name: 'review_deliverable', type: 'string' },
    { name: 'review_count', type: 'number' },
    { name: 'markdown', type: 'string' },
    { name: 'dev_deliverable', type: 'string' },
    { name: 'total_additions', type: 'number' },
    { name: 'total_deletions', type: 'number' },
    { name: 'total_files', type: 'number' },
    { name: 'owner', type: 'string' },
    { name: 'repo', type: 'string' },
    { name: 'milestone_title', type: 'string' },
    { name: 'milestone_number', type: 'number' },
    { name: 'pr_count', type: 'number' },
    { name: 'prs', type: 'array' },
  ],
});

nodeRegistry.register({
  defType: DEF_TYPE.MARKDOWN_VIEWER,
  category: 'output',
  reactFlowType: 'markdownViewerNode',
  component: MarkdownViewerNode,
  minimapColor: '#6366f1',
  panelBehavior: { onClick: 'config', onDoubleClick: 'markdown-modal' },
  configPanel: MarkdownViewerConfigPanel as any,
  palette: {
    icon: '\u{1F4DD}',
    label: '\uB9C8\uD06C\uB2E4\uC6B4 \uBDF0\uC5B4',
    description: '\uB9C8\uD06C\uB2E4\uC6B4 \uD615\uC2DD\uC73C\uB85C \uACB0\uACFC \uD45C\uC2DC',
    bg: 'from-slate-700 to-slate-900',
    border: 'border-slate-500',
    dragType: 'application/systemnode',
  },
  createNodeData: (id, position) => ({
    id,
    type: 'markdownViewerNode',
    position,
    data: {
      nodeId: DEF_TYPE.MARKDOWN_VIEWER,
      instanceName: '\uB9C8\uD06C\uB2E4\uC6B4 \uBDF0\uC5B4',
      definitionType: DEF_TYPE.MARKDOWN_VIEWER,
      config: {},
    },
  }),
  defaultData: (inst) => ({ config: inst.config || {} }),
});
