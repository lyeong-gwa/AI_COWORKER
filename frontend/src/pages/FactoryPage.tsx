import { useState, useCallback, useRef } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import type { Node } from '@xyflow/react';

import { useFactoryMap } from '../hooks/useFactoryMap';
import { useFactoryExecution } from '../hooks/useFactoryExecution';

import { AINodesContext } from '../components/workflow/FactoryNode';
import { FactoryCanvas, canvasToSaveData } from '../components/workflow/FactoryCanvas';
import type { FactoryCanvasRef } from '../components/workflow/FactoryCanvas';
import { PartsPalette } from '../components/workflow/PartsPalette';
import { FactoryToolbar } from '../components/workflow/FactoryToolbar';
import { NodeDetailPanel } from '../components/workflow/NodeDetailPanel';
import { WarehousePanel } from '../components/workflow/WarehousePanel';
import { FactoryQueuePanel } from '../components/workflow/FactoryQueuePanel';
import { SorterConfigPanel } from '../components/workflow/SorterConfigPanel';
import { ApiCallConfigPanel } from '../components/workflow/ApiCallConfigPanel';
import { UnpackerConfigPanel } from '../components/workflow/UnpackerConfigPanel';
import { FormStartConfigPanel } from '../components/workflow/FormStartConfigPanel';
import { ApiStartConfigPanel } from '../components/workflow/ApiStartConfigPanel';
import { KnowledgeConfigPanel } from '../components/workflow/KnowledgeConfigPanel';
import { EdgeMappingPanel } from '../components/workflow/EdgeMappingPanel';
import { ExecutionPanel } from '../components/workflow/ExecutionPanel';
import { TriggerConfigModal } from '../components/workflow/TriggerConfigModal';
import { ResultViewModal } from '../components/workflow/ResultViewModal';
import { MarkdownViewerModal } from '../components/workflow/MarkdownViewerModal';

import type { Edge } from '@xyflow/react';
import type { AINode, SorterRule } from '../types';
import { DEF_TYPE, TRIGGER_TYPES } from '../constants/workflow';

type RightPanel =
  | { type: 'none' }
  | { type: 'edgeMapping'; edgeId: string; sourceNodeId: string; targetNodeId: string; sourceNodeName: string; targetNodeName: string }
  | { type: 'nodeDetail'; nodeId: string; aiNode: AINode; instanceName: string; inputMapping: Record<string, string> }
  | { type: 'warehouse'; nodeId: string; nodeName: string }
  | { type: 'sorter'; nodeId: string; nodeName: string; rules: SorterRule[]; handleTargets: Record<string, string> }
  | { type: 'factoryQueue'; nodeId: string; nodeName: string }
  | { type: 'apiCallConfig'; nodeId: string; nodeName: string; config: Record<string, any>; inputMapping: Record<string, string> }
  | { type: 'unpackerConfig'; nodeId: string; nodeName: string; config: Record<string, any>; upstreamFields: { name: string; type: string }[] }
  | { type: 'formStartConfig'; nodeId: string; nodeName: string; config: Record<string, any> }
  | { type: 'apiStartConfig'; nodeId: string; nodeName: string; config: Record<string, any> }
  | { type: 'knowledgeConfig'; nodeId: string; nodeName: string; config: Record<string, any>; upstreamFields: { name: string; type: string }[] };

export function FactoryPage() {
  const { factoryMap, aiNodes, loading, saving, lastSaved, saveMap, scheduleAutoSave } = useFactoryMap();
  const { executing, currentExecution, nodeProgress, showExecution, setShowExecution, execute } = useFactoryExecution();

  const canvasRef = useRef<FactoryCanvasRef>(null);
  const [rightPanel, setRightPanel] = useState<RightPanel>({ type: 'none' });

  // Trigger modal
  const [triggerModalOpen, setTriggerModalOpen] = useState(false);
  const [triggerNodeData, setTriggerNodeData] = useState<Node | null>(null);
  const [triggerConfig, setTriggerConfig] = useState({ type: 'manual', config: {} as Record<string, unknown> });

  // Result modal
  const [resultModalOpen, setResultModalOpen] = useState(false);
  const [resultNodeId, setResultNodeId] = useState<string | null>(null);
  const [resultNodeName, setResultNodeName] = useState('');

  // Markdown viewer modal
  const [mdViewerOpen, setMdViewerOpen] = useState(false);
  const [mdViewerNodeId, setMdViewerNodeId] = useState<string | null>(null);
  const [mdViewerNodeName, setMdViewerNodeName] = useState('');

  // Pipeline selection
  const [pipelineSelectOpen, setPipelineSelectOpen] = useState(false);
  const [triggerNodes, setTriggerNodes] = useState<Node[]>([]);

  // Auto-save when canvas changes
  const handleCanvasChange = useCallback(() => {
    if (!canvasRef.current) return;
    const state = canvasRef.current.getState();
    const saveData = canvasToSaveData(state.nodes, state.edges, state.viewport);
    scheduleAutoSave(saveData);
  }, [scheduleAutoSave]);

  // Manual save
  const handleSave = useCallback(async () => {
    if (!canvasRef.current) return;
    const state = canvasRef.current.getState();
    const saveData = canvasToSaveData(state.nodes, state.edges, state.viewport);
    await saveMap(saveData);
  }, [saveMap]);

  // Execute
  const handleExecute = useCallback(async () => {
    if (!canvasRef.current) {
      await execute({});
      return;
    }
    const state = canvasRef.current.getState();
    // Find ALL trigger nodes
    const triggers = state.nodes.filter((n) => {
      const defType = n.data.definitionType as string | undefined;
      return defType != null && TRIGGER_TYPES.has(defType);
    });

    if (triggers.length === 0) {
      await execute({});
      return;
    }

    if (triggers.length === 1) {
      // Single trigger - open its config directly
      const triggerNode = triggers[0];
      setTriggerNodeData(triggerNode);
      setTriggerModalOpen(true);
      return;
    }

    // Multiple triggers - show pipeline selection
    setTriggerNodes(triggers);
    setPipelineSelectOpen(true);
  }, [execute]);

  const handlePipelineSelect = useCallback((triggerNode: Node) => {
    setPipelineSelectOpen(false);
    setTriggerNodeData(triggerNode);
    setTriggerModalOpen(true);
  }, []);

  // Node click handler
  const handleNodeClick = useCallback((node: Node) => {
    const data = node.data as Record<string, unknown>;
    const defType = data.definitionType as string;

    // Sorter node click -> show sorter config panel
    if (defType === DEF_TYPE.SORTER) {
      const config = (data.config as { rules?: SorterRule[] }) || { rules: [] };

      // Build handle → target node name map
      const handleTargets: Record<string, string> = {};
      if (canvasRef.current) {
        const state = canvasRef.current.getState();
        const sorterEdges = state.edges.filter(e => e.source === node.id);
        for (const edge of sorterEdges) {
          const targetNode = state.nodes.find(n => n.id === edge.target);
          if (targetNode && edge.sourceHandle) {
            handleTargets[edge.sourceHandle] = (targetNode.data.instanceName as string) || edge.target;
          }
        }
      }

      setRightPanel({
        type: 'sorter',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '분류기',
        rules: config.rules || [],
        handleTargets,
      });
      return;
    }

    // API Call node click -> show config panel
    if (defType === DEF_TYPE.API_CALL) {
      setRightPanel({
        type: 'apiCallConfig',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || 'API 호출기',
        config: (data.config as Record<string, any>) || {},
        inputMapping: (data.inputMapping as Record<string, string>) || {},
      });
      return;
    }

    // Unpacker node click -> show config panel with upstream output fields
    if (defType === DEF_TYPE.UNPACKER) {
      let upstreamFields: { name: string; type: string }[] = [];

      if (canvasRef.current) {
        const state = canvasRef.current.getState();
        const incomingEdges = state.edges.filter(e => e.target === node.id);
        for (const edge of incomingEdges) {
          const output = canvasRef.current.getOutputFields(edge.source);
          for (const f of [...output.own, ...output.passthrough]) {
            if (!upstreamFields.some(u => u.name === f.name)) {
              upstreamFields.push(f);
            }
          }
        }
      }

      setRightPanel({
        type: 'unpackerConfig',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '언패커',
        config: (data.config as Record<string, any>) || {},
        upstreamFields,
      });
      return;
    }

    // Markdown viewer node click -> open markdown viewer modal directly
    if (defType === DEF_TYPE.MARKDOWN_VIEWER) {
      setMdViewerNodeName((data.instanceName as string) || '마크다운 뷰어');
      setMdViewerNodeId(node.id);
      setMdViewerOpen(true);
      return;
    }

    // Warehouse node click -> show warehouse panel
    if (defType === DEF_TYPE.RESULT) {
      setRightPanel({
        type: 'warehouse',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '창고',
      });
      return;
    }

    // Form start node click -> show form start config panel
    if (defType === DEF_TYPE.FORM_START) {
      setRightPanel({
        type: 'formStartConfig',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '폼 입력 시작',
        config: (data.config as Record<string, any>) || {},
      });
      return;
    }

    // API start node click -> show api start config panel
    if (defType === DEF_TYPE.API_START) {
      setRightPanel({
        type: 'apiStartConfig',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || 'API 호출 시작',
        config: (data.config as Record<string, any>) || {},
      });
      return;
    }

    // Knowledge node click -> show knowledge config panel with upstream fields
    if (defType === DEF_TYPE.KNOWLEDGE) {
      let upstreamFields: { name: string; type: string }[] = [];

      if (canvasRef.current) {
        const state = canvasRef.current.getState();
        const incomingEdges = state.edges.filter(e => e.target === node.id);
        for (const edge of incomingEdges) {
          const output = canvasRef.current.getOutputFields(edge.source);
          for (const f of [...output.own, ...output.passthrough]) {
            if (!upstreamFields.some(u => u.name === f.name)) {
              upstreamFields.push(f);
            }
          }
        }
      }

      setRightPanel({
        type: 'knowledgeConfig',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '지식 검색',
        config: (data.config as Record<string, any>) || {},
        upstreamFields,
      });
      return;
    }

    // Legacy trigger node click -> show trigger config modal
    if ([DEF_TYPE.MANUAL, DEF_TYPE.SCHEDULE, DEF_TYPE.WEBHOOK, DEF_TYPE.FORM].includes(defType as any)) {
      setTriggerNodeData(node);
      setTriggerModalOpen(true);
      return;
    }

    // Factory (AI) node click -> show queue panel
    if (defType === DEF_TYPE.AI_CUSTOM) {
      setRightPanel({
        type: 'factoryQueue',
        nodeId: node.id,
        nodeName: (data.instanceName as string) || '공장',
      });
      return;
    }
  }, []);

  // Node double-click handler -> show detail panel for factory nodes
  const handleNodeDoubleClick = useCallback((node: Node) => {
    const data = node.data as Record<string, unknown>;
    const defType = data.definitionType as string;

    if (defType === DEF_TYPE.AI_CUSTOM) {
      const aiNodeId = (data.aiNodeId as string) || (data.nodeId as string);
      const aiNode = aiNodes.find(n => n.id === aiNodeId);
      if (aiNode) {
        setRightPanel({
          type: 'nodeDetail',
          nodeId: node.id,
          aiNode,
          instanceName: (data.instanceName as string) || aiNode.name,
          inputMapping: (data.inputMapping as Record<string, string>) || {},
        });
      }
    }

    // Sorter double-click -> show warehouse data modal
    if (defType === DEF_TYPE.SORTER) {
      setResultNodeName((data.instanceName as string) || '분류기');
      setResultNodeId(node.id);
      setResultModalOpen(true);
    }

    // API Call double-click -> show result modal (API execution results stored in warehouse)
    if (defType === DEF_TYPE.API_CALL) {
      setResultNodeName((data.instanceName as string) || 'API 호출기');
      setResultNodeId(node.id);
      setResultModalOpen(true);
    }

    // Warehouse double-click -> show result modal for viewing past executions
    if (defType === DEF_TYPE.RESULT) {
      setResultNodeName((data.instanceName as string) || '창고');
      setResultNodeId(node.id);
      setResultModalOpen(true);
    }

    // Markdown viewer double-click -> same as single click (open viewer)
    if (defType === DEF_TYPE.MARKDOWN_VIEWER) {
      setMdViewerNodeName((data.instanceName as string) || '마크다운 뷰어');
      setMdViewerNodeId(node.id);
      setMdViewerOpen(true);
    }
  }, [aiNodes]);

  // Edge click handler -> show edge mapping panel
  const handleEdgeClick = useCallback((_edgeId: string, edge: Edge) => {
    const state = canvasRef.current?.getState();
    if (!state) return;

    const sourceNode = state.nodes.find((n) => n.id === edge.source);
    const targetNode = state.nodes.find((n) => n.id === edge.target);
    if (!sourceNode || !targetNode) return;

    setRightPanel({
      type: 'edgeMapping',
      edgeId: edge.id,
      sourceNodeId: edge.source,
      targetNodeId: edge.target,
      sourceNodeName: (sourceNode.data.instanceName as string) || edge.source,
      targetNodeName: (targetNode.data.instanceName as string) || edge.target,
    });
  }, []);

  // Loading state
  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-gray-600 border-t-amber-500 rounded-full animate-spin" />
          <span className="text-gray-400 text-sm">공장 맵 로딩 중...</span>
        </div>
      </div>
    );
  }

  // No factory map (shouldn't happen - auto-creates)
  if (!factoryMap) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-900">
        <div className="text-center">
          <div className="text-4xl mb-3">🏭</div>
          <h2 className="text-white text-xl font-bold mb-2">공장 맵 초기화 중</h2>
          <p className="text-gray-400 text-sm">백엔드 연결을 확인하세요</p>
        </div>
      </div>
    );
  }

  return (
    <AINodesContext.Provider value={aiNodes}>
      <div className="h-full flex flex-col bg-gray-900">
        {/* Toolbar */}
        <FactoryToolbar
          onSave={handleSave}
          onExecute={handleExecute}
          onToggleHistory={() => setShowExecution(prev => !prev)}
          isSaving={saving}
          isExecuting={executing}
          lastSaved={lastSaved}
        />

        {/* Main area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Parts palette */}
          <PartsPalette aiNodes={aiNodes} />

          {/* Center: Canvas */}
          <ReactFlowProvider>
            <FactoryCanvas
              ref={canvasRef}
              workflow={factoryMap}
              aiNodes={aiNodes}
              onNodesChange={handleCanvasChange}
              onNodeClick={handleNodeClick}
              onNodeDoubleClick={handleNodeDoubleClick}
              onEdgeClick={handleEdgeClick}
            />
          </ReactFlowProvider>

          {/* Right: Detail panels */}
          {rightPanel.type === 'edgeMapping' && canvasRef.current && (() => {
            const state = canvasRef.current!.getState();
            const targetNode = state.nodes.find((n) => n.id === rightPanel.targetNodeId);
            const currentMapping = (targetNode?.data.inputMapping as Record<string, string>) || {};
            const outputFields = canvasRef.current!.getOutputFields(rightPanel.sourceNodeId);
            const inputFields = canvasRef.current!.getInputFields(rightPanel.targetNodeId);

            return (
              <EdgeMappingPanel
                edgeId={rightPanel.edgeId}
                sourceNodeId={rightPanel.sourceNodeId}
                targetNodeId={rightPanel.targetNodeId}
                sourceNodeName={rightPanel.sourceNodeName}
                targetNodeName={rightPanel.targetNodeName}
                sourceOutputFields={outputFields.own}
                passthroughFields={outputFields.passthrough}
                targetInputFields={inputFields}
                currentMapping={currentMapping}
                onUpdateMapping={(mapping) => {
                  canvasRef.current?.updateNodeData(rightPanel.targetNodeId, { inputMapping: mapping } as any);
                  handleCanvasChange();
                }}
                onClose={() => setRightPanel({ type: 'none' })}
              />
            );
          })()}

          {rightPanel.type === 'nodeDetail' && (
            <NodeDetailPanel
              aiNode={rightPanel.aiNode}
              instanceName={rightPanel.instanceName}
              inputMapping={rightPanel.inputMapping}
              onUpdateName={(name) => {
                setRightPanel(prev =>
                  prev.type === 'nodeDetail' ? { ...prev, instanceName: name } : prev
                );
                handleCanvasChange();
              }}
              onDelete={() => {
                // TODO: Delete node from canvas
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'warehouse' && (
            <WarehousePanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'warehouse' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'factoryQueue' && (
            <FactoryQueuePanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'sorter' && (
            <SorterConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              rules={rightPanel.rules}
              handleTargets={rightPanel.handleTargets}
              onUpdateName={(name) => {
                if (canvasRef.current && rightPanel.type === 'sorter') {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'sorter' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateRules={(rules) => {
                if (canvasRef.current && rightPanel.type === 'sorter') {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config: { rules } } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'sorter' ? { ...prev, rules } : prev
                );
                handleCanvasChange();
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'apiCallConfig' && (
            <ApiCallConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              config={rightPanel.config}
              inputMapping={rightPanel.inputMapping}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'apiCallConfig' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateConfig={(config) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'apiCallConfig' ? { ...prev, config } : prev
                );
                handleCanvasChange();
              }}
              onDelete={() => {
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'unpackerConfig' && (
            <UnpackerConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              config={rightPanel.config}
              upstreamFields={rightPanel.upstreamFields}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'unpackerConfig' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateConfig={(config) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'unpackerConfig' ? { ...prev, config } : prev
                );
                handleCanvasChange();
              }}
              onDelete={() => {
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'formStartConfig' && (
            <FormStartConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              config={rightPanel.config}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'formStartConfig' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateConfig={(config) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'formStartConfig' ? { ...prev, config } : prev
                );
                handleCanvasChange();
              }}
              onExecute={(inputData) => execute(inputData, rightPanel.nodeId)}
              executing={executing}
              onDelete={() => {
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'apiStartConfig' && (
            <ApiStartConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              config={rightPanel.config}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'apiStartConfig' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateConfig={(config) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'apiStartConfig' ? { ...prev, config } : prev
                );
                handleCanvasChange();
              }}
              onExecute={() => execute({})}
              executing={executing}
              onDelete={() => {
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}

          {rightPanel.type === 'knowledgeConfig' && (
            <KnowledgeConfigPanel
              nodeId={rightPanel.nodeId}
              nodeName={rightPanel.nodeName}
              config={rightPanel.config}
              upstreamFields={rightPanel.upstreamFields}
              onUpdateName={(name) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'knowledgeConfig' ? { ...prev, nodeName: name } : prev
                );
                handleCanvasChange();
              }}
              onUpdateConfig={(config) => {
                if (canvasRef.current) {
                  canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                }
                setRightPanel(prev =>
                  prev.type === 'knowledgeConfig' ? { ...prev, config } : prev
                );
                handleCanvasChange();
              }}
              onDelete={() => {
                setRightPanel({ type: 'none' });
              }}
              onClose={() => setRightPanel({ type: 'none' })}
            />
          )}
        </div>

        {/* Bottom: Execution panel */}
        {showExecution && (
          <ExecutionPanel
            currentExecution={currentExecution}
            nodeProgress={nodeProgress}
            onClose={() => setShowExecution(false)}
          />
        )}

        {/* Modals */}
        {triggerModalOpen && triggerNodeData && (
          <TriggerConfigModal
            isOpen={triggerModalOpen}
            triggerConfig={triggerConfig}
            triggerNode={triggerNodeData as any}
            triggerNodeId={triggerNodeData.id}
            allNodes={canvasRef.current?.getState().nodes || []}
            edges={canvasRef.current?.getState().edges || []}
            aiNodes={aiNodes}
            onSaveTrigger={(newConfig) => {
              setTriggerConfig(newConfig);
              setTriggerModalOpen(false);
            }}
            onExecute={async (inputData) => {
              if (canvasRef.current) {
                const state = canvasRef.current.getState();
                const saveData = canvasToSaveData(state.nodes, state.edges, state.viewport);
                await saveMap(saveData);
              }
              execute(inputData, triggerNodeData?.id);
            }}
            executing={executing}
            onClose={() => setTriggerModalOpen(false)}
          />
        )}

        {resultModalOpen && resultNodeId && (
          <ResultViewModal
            isOpen={resultModalOpen}
            resultNodeId={resultNodeId}
            resultNodeName={resultNodeName}
            onReExecute={() => execute({})}
            onClose={() => setResultModalOpen(false)}
          />
        )}

        {mdViewerOpen && mdViewerNodeId && (
          <MarkdownViewerModal
            isOpen={mdViewerOpen}
            resultNodeId={mdViewerNodeId}
            resultNodeName={mdViewerNodeName}
            onReExecute={() => execute({})}
            onClose={() => setMdViewerOpen(false)}
          />
        )}

        {/* Pipeline selection modal */}
        {pipelineSelectOpen && triggerNodes.length > 0 && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
            onClick={(e) => { if (e.target === e.currentTarget) setPipelineSelectOpen(false); }}
          >
            <div className="bg-gray-800 border border-gray-700 rounded-xl shadow-2xl w-full max-w-sm mx-4">
              <div className="px-5 py-4 border-b border-gray-700">
                <h2 className="text-lg font-semibold text-white">파이프라인 선택</h2>
                <p className="text-xs text-gray-500 mt-1">실행할 파이프라인을 선택하세요</p>
              </div>
              <div className="p-4 space-y-2">
                {triggerNodes.map((node) => (
                  <button
                    key={node.id}
                    onClick={() => handlePipelineSelect(node)}
                    className="w-full flex items-center gap-3 px-4 py-3 bg-gray-900/40 hover:bg-gray-700 border border-gray-700 rounded-lg transition-colors text-left"
                  >
                    <span className="text-2xl">
                      {(node.data.definitionType as string) === DEF_TYPE.FORM_START ? '\u{1F4CB}' :
                       (node.data.definitionType as string) === DEF_TYPE.API_START ? '\u{1F50C}' : '\u25B6'}
                    </span>
                    <div>
                      <div className="text-sm font-medium text-white">
                        {(node.data.instanceName as string) || node.id}
                      </div>
                      <div className="text-xs text-gray-500">
                        {(node.data.definitionType as string)}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
              <div className="px-5 py-3 border-t border-gray-700">
                <button
                  onClick={() => setPipelineSelectOpen(false)}
                  className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm font-medium rounded-lg transition-colors"
                >
                  취소
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AINodesContext.Provider>
  );
}
