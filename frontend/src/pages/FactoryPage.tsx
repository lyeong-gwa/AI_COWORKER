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
import { EdgeMappingPanel } from '../components/workflow/EdgeMappingPanel';
import { ExecutionPanel } from '../components/workflow/ExecutionPanel';
import { TriggerConfigModal } from '../components/workflow/TriggerConfigModal';
import { ResultViewModal } from '../components/workflow/ResultViewModal';
import { MarkdownViewerModal } from '../components/workflow/MarkdownViewerModal';

import { nodeRegistry } from '../nodes/registry';

import type { Edge } from '@xyflow/react';
import type { AINode, SorterRule } from '../types';
import { DEF_TYPE, TRIGGER_TYPES } from '../constants/workflow';

/* ------------------------------------------------------------------ */
/*  RightPanel union type                                              */
/* ------------------------------------------------------------------ */

type RightPanel =
  | { type: 'none' }
  | { type: 'edgeMapping'; edgeId: string; sourceNodeId: string; targetNodeId: string; sourceNodeName: string; targetNodeName: string }
  | { type: 'nodeDetail'; nodeId: string; aiNode: AINode; instanceName: string; inputMapping: Record<string, string> }
  | { type: 'warehouse'; nodeId: string; nodeName: string }
  | { type: 'factoryQueue'; nodeId: string; nodeName: string }
  | {
      type: 'config';
      nodeId: string;
      nodeName: string;
      defType: string;
      config: Record<string, any>;
      inputMapping: Record<string, string>;
      upstreamFields: { name: string; type: string }[];
    };

/* ------------------------------------------------------------------ */
/*  Helper: upstream fields 수집                                       */
/* ------------------------------------------------------------------ */

function collectUpstreamFields(
  canvasRef: React.RefObject<FactoryCanvasRef | null>,
  nodeId: string,
): { name: string; type: string }[] {
  const fields: { name: string; type: string }[] = [];
  if (!canvasRef.current) return fields;
  const state = canvasRef.current.getState();
  const incomingEdges = state.edges.filter(e => e.target === nodeId);
  for (const edge of incomingEdges) {
    const output = canvasRef.current.getOutputFields(edge.source);
    for (const f of [...output.own, ...output.passthrough]) {
      if (!fields.some(u => u.name === f.name)) {
        fields.push(f);
      }
    }
  }
  return fields;
}

/* ------------------------------------------------------------------ */
/*  FactoryPage                                                        */
/* ------------------------------------------------------------------ */

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
  const [mdViewerDisplayKey, setMdViewerDisplayKey] = useState<string | undefined>();

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

  /* ---------------------------------------------------------------- */
  /*  Node click handler -- registry-based routing                     */
  /* ---------------------------------------------------------------- */

  const handleNodeClick = useCallback((node: Node) => {
    const data = node.data as Record<string, unknown>;
    const defType = (data.definitionType as string) || '';
    const def = nodeRegistry.get(defType);
    const behavior = def?.panelBehavior?.onClick || 'none';

    const nodeId = node.id;
    const nodeName = (data.instanceName as string) || '';
    const config = (data.config as Record<string, any>) || {};
    const inputMapping = (data.inputMapping as Record<string, string>) || {};

    switch (behavior) {
      case 'config': {
        const upstreamFields = collectUpstreamFields(canvasRef, nodeId);
        setRightPanel({
          type: 'config',
          nodeId,
          nodeName,
          defType,
          config,
          inputMapping,
          upstreamFields,
        });
        break;
      }
      case 'queue':
        setRightPanel({ type: 'factoryQueue', nodeId, nodeName });
        break;
      case 'warehouse':
        setRightPanel({ type: 'warehouse', nodeId, nodeName });
        break;
      case 'none':
      default:
        // Legacy trigger nodes -> show trigger config modal
        if ([DEF_TYPE.MANUAL, DEF_TYPE.SCHEDULE, DEF_TYPE.WEBHOOK, DEF_TYPE.FORM].includes(defType as any)) {
          setTriggerNodeData(node);
          setTriggerModalOpen(true);
        }
        break;
    }
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Node double-click handler -- registry-based routing              */
  /* ---------------------------------------------------------------- */

  const handleNodeDoubleClick = useCallback((node: Node) => {
    const data = node.data as Record<string, unknown>;
    const defType = (data.definitionType as string) || '';
    const def = nodeRegistry.get(defType);
    const behavior = def?.panelBehavior?.onDoubleClick;

    const nodeName = (data.instanceName as string) || '';

    switch (behavior) {
      case 'detail': {
        // AI node -> show detail panel
        const aiNodeId = (data.aiNodeId as string) || (data.nodeId as string);
        const aiNode = aiNodes.find(n => n.id === aiNodeId);
        if (aiNode) {
          setRightPanel({
            type: 'nodeDetail',
            nodeId: node.id,
            aiNode,
            instanceName: nodeName || aiNode.name,
            inputMapping: (data.inputMapping as Record<string, string>) || {},
          });
        }
        break;
      }
      case 'result-modal':
        setResultNodeName(nodeName);
        setResultNodeId(node.id);
        setResultModalOpen(true);
        break;
      case 'markdown-modal':
        setMdViewerNodeName(nodeName || '\uB9C8\uD06C\uB2E4\uC6B4 \uBDF0\uC5B4');
        setMdViewerNodeId(node.id);
        setMdViewerDisplayKey((data.config as any)?.displayKey || undefined);
        setMdViewerOpen(true);
        break;
      case 'none':
      default:
        break;
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
          <span className="text-gray-400 text-sm">{'\uACF5\uC7A5 \uB9F5 \uB85C\uB529 \uC911...'}</span>
        </div>
      </div>
    );
  }

  // No factory map (shouldn't happen - auto-creates)
  if (!factoryMap) {
    return (
      <div className="h-full flex items-center justify-center bg-gray-900">
        <div className="text-center">
          <div className="text-4xl mb-3">{'\uD83C\uDFED'}</div>
          <h2 className="text-white text-xl font-bold mb-2">{'\uACF5\uC7A5 \uB9F5 \uCD08\uAE30\uD654 \uC911'}</h2>
          <p className="text-gray-400 text-sm">{'\uBC31\uC5D4\uB4DC \uC5F0\uACB0\uC744 \uD655\uC778\uD558\uC138\uC694'}</p>
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
              nodeProgress={nodeProgress}
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

          {/* Unified config panel -- registry-based */}
          {rightPanel.type === 'config' && (() => {
            const def = nodeRegistry.get(rightPanel.defType);
            if (!def?.configPanel) return null;
            const Panel = def.configPanel;

            // Sorter: handleTargets 계산
            let handleTargets: Record<string, string> = {};
            if (rightPanel.defType === DEF_TYPE.SORTER && canvasRef.current) {
              const state = canvasRef.current.getState();
              const outEdges = state.edges.filter(e => e.source === rightPanel.nodeId);
              for (const e of outEdges) {
                const tgtNode = state.nodes.find(n => n.id === e.target);
                if (e.sourceHandle) {
                  handleTargets[e.sourceHandle] = (tgtNode?.data.instanceName as string) || e.target;
                }
              }
            }

            // Starter 노드: onExecute 콜백
            const isStarter = TRIGGER_TYPES.has(rightPanel.defType);

            return (
              <Panel
                nodeId={rightPanel.nodeId}
                nodeName={rightPanel.nodeName}
                config={rightPanel.config}
                allNodes={canvasRef.current?.getState().nodes || []}
                edges={canvasRef.current?.getState().edges || []}
                aiNodes={aiNodes}
                inputMapping={rightPanel.inputMapping}
                upstreamFields={rightPanel.upstreamFields}
                // Sorter 전용
                rules={rightPanel.config.rules || []}
                handleTargets={handleTargets}
                onUpdateName={(name: string) => {
                  if (canvasRef.current) {
                    canvasRef.current.updateNodeData(rightPanel.nodeId, { instanceName: name } as any);
                  }
                  setRightPanel(prev =>
                    prev.type === 'config' ? { ...prev, nodeName: name } : prev
                  );
                  handleCanvasChange();
                }}
                onUpdateConfig={(config: Record<string, any>) => {
                  if (canvasRef.current) {
                    canvasRef.current.updateNodeData(rightPanel.nodeId, { config } as any);
                  }
                  setRightPanel(prev =>
                    prev.type === 'config' ? { ...prev, config } : prev
                  );
                  handleCanvasChange();
                }}
                onUpdateRules={(rules: SorterRule[]) => {
                  if (canvasRef.current) {
                    canvasRef.current.updateNodeData(rightPanel.nodeId, { config: { ...rightPanel.config, rules } } as any);
                  }
                  setRightPanel(prev =>
                    prev.type === 'config' ? { ...prev, config: { ...prev.config, rules } } : prev
                  );
                  handleCanvasChange();
                }}
                onDelete={() => {
                  setRightPanel({ type: 'none' });
                }}
                onClose={() => setRightPanel({ type: 'none' })}
                onExecute={isStarter
                  ? (inputData?: Record<string, unknown>) => {
                      // onClick={onExecute}로 호출 시 React 이벤트 객체가 전달될 수 있으므로 필터링
                      const data = (inputData && typeof inputData === 'object' && !('nativeEvent' in inputData))
                        ? inputData : {};
                      execute(data, rightPanel.nodeId);
                    }
                  : undefined}
                executing={isStarter ? executing : undefined}
              />
            );
          })()}
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
            displayKey={mdViewerDisplayKey}
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
                <h2 className="text-lg font-semibold text-white">{'\uD30C\uC774\uD504\uB77C\uC778 \uC120\uD0DD'}</h2>
                <p className="text-xs text-gray-500 mt-1">{'\uC2E4\uD589\uD560 \uD30C\uC774\uD504\uB77C\uC778\uC744 \uC120\uD0DD\uD558\uC138\uC694'}</p>
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
                  {'\uCDE8\uC18C'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AINodesContext.Provider>
  );
}
