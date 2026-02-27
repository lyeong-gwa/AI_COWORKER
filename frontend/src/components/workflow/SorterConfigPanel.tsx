import { useState, useEffect, useCallback } from 'react';
import { factoryApi } from '../../services/api';
import type { SorterRule, WarehouseEntry } from '../../types';

interface SorterConfigPanelProps {
  nodeId: string;
  nodeName: string;
  rules: SorterRule[];
  handleTargets: Record<string, string>;  // handleId -> targetNodeName
  onUpdateName: (name: string) => void;
  onUpdateRules: (rules: SorterRule[]) => void;
  onClose: () => void;
}

type Tab = 'rules' | 'warehouse';

const OPERATOR_LABELS: Record<string, string> = {
  equals: '같음 (==)',
  notEquals: '같지 않음 (!=)',
  contains: '포함',
  startsWith: '시작',
  endsWith: '끝남',
  greaterThan: '초과 (>)',
  lessThan: '미만 (<)',
  exists: '존재함',
  notExists: '존재하지 않음',
  regex: '정규식',
};

const OPERATORS = Object.keys(OPERATOR_LABELS) as SorterRule['operator'][];

const VALUE_HIDDEN_OPERATORS: SorterRule['operator'][] = ['exists', 'notExists'];

export function SorterConfigPanel({
  nodeId,
  nodeName,
  rules,
  handleTargets,
  onUpdateName,
  onUpdateRules,
  onClose,
}: SorterConfigPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('rules');
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);

  // Warehouse tab state
  const [warehouseEntries, setWarehouseEntries] = useState<WarehouseEntry[]>([]);
  const [warehouseTotal, setWarehouseTotal] = useState(0);
  const [warehouseLoading, setWarehouseLoading] = useState(false);
  const [warehouseExpandedId, setWarehouseExpandedId] = useState<string | null>(null);

  const fetchWarehouse = useCallback(async () => {
    setWarehouseLoading(true);
    try {
      const result = await factoryApi.getWarehouse(nodeId, 50);
      setWarehouseEntries(result.items);
      setWarehouseTotal(result.total);
    } catch {
      // ignore
    } finally {
      setWarehouseLoading(false);
    }
  }, [nodeId]);

  useEffect(() => {
    if (activeTab === 'warehouse') {
      fetchWarehouse();
    }
  }, [activeTab, fetchWarehouse]);

  // ── Rule helpers ──────────────────────────────────────────────────────────

  const handleAddRule = () => {
    const newRule: SorterRule = {
      id: `rule-${Date.now()}`,
      field: '',
      operator: 'equals',
      value: '',
      label: `규칙 ${rules.length + 1}`,
    };
    const updated = [...rules, newRule];
    onUpdateRules(updated);
    setExpandedRuleId(newRule.id);
  };

  const handleDeleteRule = (id: string) => {
    onUpdateRules(rules.filter((r) => r.id !== id));
    if (expandedRuleId === id) setExpandedRuleId(null);
  };

  const handleUpdateRule = (id: string, patch: Partial<SorterRule>) => {
    onUpdateRules(rules.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;
    const updated = [...rules];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    onUpdateRules(updated);
  };

  const handleMoveDown = (index: number) => {
    if (index === rules.length - 1) return;
    const updated = [...rules];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    onUpdateRules(updated);
  };

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'rules', label: '규칙', icon: '⚙️' },
    { key: 'warehouse', label: '창고', icon: '📦' },
  ];

  return (
    <div className="w-96 bg-gray-800 border-l border-gray-700 flex flex-col animate-slide-in-right">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-violet-900 flex items-center justify-center text-xl">
              🔀
            </div>
            <div>
              <div className="text-xs text-violet-300/70 uppercase tracking-wider">정렬기 설정</div>
              <div className="text-white font-semibold">{nodeName}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl p-1">
            ✕
          </button>
        </div>

        {/* Name input */}
        <div className="mb-3">
          <label className="block text-xs text-gray-400 mb-1">이름</label>
          <input
            type="text"
            value={nodeName}
            onChange={(e) => onUpdateName(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-1 ${
                activeTab === tab.key
                  ? 'bg-violet-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-gray-200'
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {/* ── Rules Tab ─────────────────────────────────────────────────── */}
        {activeTab === 'rules' && (
          <div className="p-4 space-y-2">
            {rules.length === 0 && (
              <div className="text-center py-8">
                <div className="text-3xl mb-2">⚙️</div>
                <p className="text-gray-500 text-sm">규칙이 없습니다</p>
                <p className="text-gray-600 text-xs mt-1">
                  아래 버튼으로 새 규칙을 추가하세요
                </p>
              </div>
            )}

            {rules.map((rule, index) => {
              const isExpanded = expandedRuleId === rule.id;
              const hideValue = VALUE_HIDDEN_OPERATORS.includes(rule.operator);

              return (
                <div
                  key={rule.id}
                  className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden"
                >
                  {/* Rule header row */}
                  <div className="flex items-center gap-1 px-3 py-2">
                    {/* Up / Down */}
                    <div className="flex flex-col gap-0.5">
                      <button
                        onClick={() => handleMoveUp(index)}
                        disabled={index === 0}
                        className="text-gray-600 hover:text-violet-400 disabled:opacity-20 text-[10px] leading-none"
                        title="위로"
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => handleMoveDown(index)}
                        disabled={index === rules.length - 1}
                        className="text-gray-600 hover:text-violet-400 disabled:opacity-20 text-[10px] leading-none"
                        title="아래로"
                      >
                        ▼
                      </button>
                    </div>

                    {/* Violet accent bar */}
                    <div className="w-1 h-8 rounded-full bg-violet-600/70 flex-shrink-0" />

                    {/* Summary */}
                    <button
                      onClick={() =>
                        setExpandedRuleId(isExpanded ? null : rule.id)
                      }
                      className="flex-1 text-left min-w-0"
                    >
                      <div className="text-gray-200 text-xs font-medium truncate">
                        {rule.label || '(이름 없음)'}
                      </div>
                      <div className="text-gray-500 text-[10px] truncate">
                        {rule.field
                          ? `${rule.field} ${OPERATOR_LABELS[rule.operator] ?? rule.operator}${
                              !hideValue && rule.value ? ` "${rule.value}"` : ''
                            }`
                          : '(필드 미설정)'}
                      </div>
                      {/* Target node indicator */}
                      <div className="mt-0.5">
                        {handleTargets[`rule-${rule.id}`] ? (
                          <span className="inline-flex items-center gap-1 text-[9px] text-amber-300/80 bg-amber-900/30 px-1.5 py-0.5 rounded">
                            → {handleTargets[`rule-${rule.id}`]}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[9px] text-red-400/70 bg-red-900/20 px-1.5 py-0.5 rounded">
                            ⚠ 미연결
                          </span>
                        )}
                      </div>
                    </button>

                    <div className="flex items-center gap-1 flex-shrink-0">
                      <span className="text-gray-600 text-xs">
                        {isExpanded ? '▲' : '▼'}
                      </span>
                      <button
                        onClick={() => handleDeleteRule(rule.id)}
                        className="text-gray-600 hover:text-red-400 transition-colors px-1"
                        title="규칙 삭제"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  {/* Expanded edit form */}
                  {isExpanded && (
                    <div className="px-4 pb-4 pt-2 border-t border-gray-700/60 space-y-3">
                      {/* Label */}
                      <div>
                        <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">
                          규칙 이름
                        </label>
                        <input
                          type="text"
                          value={rule.label}
                          onChange={(e) =>
                            handleUpdateRule(rule.id, { label: e.target.value })
                          }
                          placeholder="규칙 이름"
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
                        />
                      </div>

                      {/* Field */}
                      <div>
                        <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">
                          필드
                        </label>
                        <input
                          type="text"
                          value={rule.field}
                          onChange={(e) =>
                            handleUpdateRule(rule.id, { field: e.target.value })
                          }
                          placeholder="예: data.status"
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 font-mono focus:outline-none focus:ring-1 focus:ring-violet-500"
                        />
                      </div>

                      {/* Operator */}
                      <div>
                        <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">
                          연산자
                        </label>
                        <select
                          value={rule.operator}
                          onChange={(e) =>
                            handleUpdateRule(rule.id, {
                              operator: e.target.value as SorterRule['operator'],
                            })
                          }
                          className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
                        >
                          {OPERATORS.map((op) => (
                            <option key={op} value={op}>
                              {OPERATOR_LABELS[op]}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Value — hidden for exists/notExists */}
                      {!hideValue && (
                        <div>
                          <label className="block text-[10px] text-gray-400 mb-1 uppercase tracking-wide">
                            값
                          </label>
                          <input
                            type="text"
                            value={rule.value}
                            onChange={(e) =>
                              handleUpdateRule(rule.id, { value: e.target.value })
                            }
                            placeholder="비교할 값"
                            className="w-full bg-gray-800 border border-gray-600 rounded px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
                          />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Default handle target */}
            <div className="bg-gray-900/60 rounded-lg border border-gray-700/50 px-3 py-2 flex items-center justify-between">
              <div>
                <div className="text-gray-400 text-xs font-medium">기타 (기본)</div>
                <div className="text-gray-600 text-[10px]">어느 규칙에도 해당하지 않는 경우</div>
              </div>
              {handleTargets['default'] ? (
                <span className="text-[9px] text-amber-300/80 bg-amber-900/30 px-1.5 py-0.5 rounded">
                  → {handleTargets['default']}
                </span>
              ) : (
                <span className="text-[9px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">
                  미연결
                </span>
              )}
            </div>

            {/* Add rule button */}
            <button
              onClick={handleAddRule}
              className="w-full py-2 border border-dashed border-violet-700/50 text-violet-400 text-xs rounded-lg hover:bg-violet-900/20 hover:border-violet-600 transition-colors"
            >
              + 규칙 추가
            </button>

            {rules.length > 0 && (
              <p className="text-[10px] text-gray-600 text-center pt-1">
                위에서부터 순서대로 평가됩니다. 첫 번째 일치 규칙으로 분류됩니다.
              </p>
            )}
          </div>
        )}

        {/* ── Warehouse Tab ──────────────────────────────────────────────── */}
        {activeTab === 'warehouse' && (
          <div className="flex flex-col h-full">
            {/* Sub-header */}
            <div className="px-4 py-2 border-b border-gray-700/50 flex items-center justify-between">
              <span className="text-gray-400 text-xs">{warehouseTotal}개 데이터 보관중</span>
              <button
                onClick={fetchWarehouse}
                className="text-[10px] text-gray-500 hover:text-gray-300 transition-colors"
              >
                🔄 새로고침
              </button>
            </div>

            <div className="flex-1 overflow-auto p-3 space-y-2">
              {warehouseLoading ? (
                <div className="flex items-center justify-center py-10">
                  <div className="w-6 h-6 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
                </div>
              ) : warehouseEntries.length === 0 ? (
                <div className="text-center py-10">
                  <div className="text-3xl mb-2">📭</div>
                  <p className="text-gray-500 text-sm">아직 데이터가 없습니다</p>
                  <p className="text-gray-600 text-xs mt-1">
                    정렬기를 실행하면 결과가 여기에 쌓입니다
                  </p>
                </div>
              ) : (
                warehouseEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="bg-gray-900 rounded-lg border border-gray-700 overflow-hidden"
                  >
                    <button
                      onClick={() =>
                        setWarehouseExpandedId(
                          warehouseExpandedId === entry.id ? null : entry.id
                        )
                      }
                      className="w-full px-3 py-2 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                        <span className="text-gray-300 text-xs font-mono">{entry.id}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500 text-[10px]">
                          {new Date(entry.createdAt).toLocaleString('ko-KR')}
                        </span>
                        <span className="text-gray-500 text-xs">
                          {warehouseExpandedId === entry.id ? '▲' : '▼'}
                        </span>
                      </div>
                    </button>

                    {warehouseExpandedId === entry.id && (
                      <div className="px-3 pb-3 border-t border-gray-700">
                        <div className="flex justify-end mb-1 pt-1">
                          <button
                            onClick={() =>
                              navigator.clipboard.writeText(
                                JSON.stringify(entry.data, null, 2)
                              )
                            }
                            className="text-[10px] text-gray-500 hover:text-gray-300"
                          >
                            📋 복사
                          </button>
                        </div>
                        <pre className="text-[10px] text-gray-400 bg-gray-950 rounded p-2 overflow-auto max-h-48 whitespace-pre-wrap break-words">
                          {JSON.stringify(entry.data, null, 2)}
                        </pre>
                        {entry.executionId && (
                          <div className="mt-1 text-[10px] text-gray-600">
                            실행: {entry.executionId}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
