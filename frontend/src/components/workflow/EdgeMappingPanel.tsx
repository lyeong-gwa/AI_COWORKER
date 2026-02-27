import { useState } from 'react';
import { FIELD_MAPPING_PREFIX } from '../../constants/workflow';

interface FieldDef {
  name: string;
  type: string;
}

interface EdgeMappingPanelProps {
  edgeId: string;
  sourceNodeId: string;
  targetNodeId: string;
  sourceNodeName: string;
  targetNodeName: string;
  sourceOutputFields: FieldDef[];
  passthroughFields: FieldDef[];
  targetInputFields: FieldDef[];
  currentMapping: Record<string, string>;
  onUpdateMapping: (mapping: Record<string, string>) => void;
  onClose: () => void;
}

function typeBadgeClass(type: string): string {
  switch (type) {
    case 'string':
      return 'bg-blue-900 text-blue-300';
    case 'number':
      return 'bg-green-900 text-green-300';
    case 'boolean':
      return 'bg-purple-900 text-purple-300';
    case 'object':
      return 'bg-amber-900 text-amber-300';
    case 'array':
      return 'bg-pink-900 text-pink-300';
    default:
      return 'bg-gray-700 text-gray-300';
  }
}

function parseMappingValue(raw: string): string {
  if (!raw) return '';
  if (raw.startsWith(FIELD_MAPPING_PREFIX)) return raw.slice(FIELD_MAPPING_PREFIX.length);
  return raw;
}

export function EdgeMappingPanel({
  edgeId: _edgeId,
  sourceNodeId: _sourceNodeId,
  targetNodeId: _targetNodeId,
  sourceNodeName,
  targetNodeName,
  sourceOutputFields,
  passthroughFields,
  targetInputFields,
  currentMapping,
  onUpdateMapping,
  onClose,
}: EdgeMappingPanelProps) {
  const [mapping, setMapping] = useState<Record<string, string>>(() => ({ ...currentMapping }));
  const [passthroughOpen, setPassthroughOpen] = useState(false);

  function handleSelectChange(targetField: string, selectedValue: string) {
    const next = { ...mapping };
    if (!selectedValue) {
      delete next[targetField];
    } else {
      next[targetField] = `${FIELD_MAPPING_PREFIX}${selectedValue}`;
    }
    setMapping(next);
    onUpdateMapping(next);
  }

  function handleAutoMap() {
    const sourceNames = new Set(sourceOutputFields.map((f) => f.name));
    const next = { ...mapping };
    for (const tf of targetInputFields) {
      if (sourceNames.has(tf.name)) {
        next[tf.name] = `${FIELD_MAPPING_PREFIX}${tf.name}`;
      }
    }
    setMapping(next);
    onUpdateMapping(next);
  }

  function handleReset() {
    const next: Record<string, string> = {};
    setMapping(next);
    onUpdateMapping(next);
  }

  return (
    <div className="w-80 bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between flex-shrink-0">
        <span className="text-sm font-semibold text-white">컨베이어 벨트 매핑</span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white transition-colors p-0.5 rounded hover:bg-gray-700"
          aria-label="닫기"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Source → Target label */}
      <div className="px-4 py-2 border-b border-gray-700 flex-shrink-0">
        <div className="flex items-center gap-1 text-xs">
          <span className="text-blue-300 font-medium truncate max-w-[100px]" title={sourceNodeName}>
            {sourceNodeName}
          </span>
          <svg className="w-4 h-4 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
          <span className="text-green-300 font-medium truncate max-w-[100px]" title={targetNodeName}>
            {targetNodeName}
          </span>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-5">

        {/* 소스 출력 (OWN) */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            소스 출력 (OWN)
          </h3>
          {sourceOutputFields.length === 0 ? (
            <p className="text-xs text-gray-500 italic">출력 필드 없음</p>
          ) : (
            <ul className="space-y-1">
              {sourceOutputFields.map((field) => (
                <li key={field.name} className="flex items-center gap-2 py-1">
                  <span className="text-xs text-gray-300 flex-1 truncate">{field.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeBadgeClass(field.type)}`}>
                    {field.type}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 타겟 입력 매핑 */}
        <section>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            타겟 입력 매핑
          </h3>
          {targetInputFields.length === 0 ? (
            <p className="text-xs text-gray-500 italic">입력 필드 없음</p>
          ) : (
            <ul className="space-y-2">
              {targetInputFields.map((field) => {
                const rawVal = mapping[field.name] ?? '';
                const selectVal = parseMappingValue(rawVal);
                const isMapped = !!selectVal;

                return (
                  <li key={field.name} className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`w-2 h-2 rounded-full flex-shrink-0 ${isMapped ? 'bg-green-500' : 'bg-red-500'}`}
                        title={isMapped ? '매핑됨' : '매핑 없음'}
                      />
                      <span className="text-xs text-gray-300 flex-1 truncate">{field.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeBadgeClass(field.type)}`}>
                        {field.type}
                      </span>
                    </div>
                    <select
                      value={selectVal}
                      onChange={(e) => handleSelectChange(field.name, e.target.value)}
                      className="w-full bg-gray-900 border border-gray-600 rounded px-2 py-1 text-xs text-gray-300 focus:outline-none focus:border-blue-500"
                    >
                      <option value="">(매핑 없음)</option>
                      {sourceOutputFields.length > 0 && (
                        <optgroup label="── 소스 출력 ──">
                          {sourceOutputFields.map((sf) => (
                            <option key={sf.name} value={sf.name}>
                              {sf.name} ({sf.type})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {passthroughFields.length > 0 && (
                        <optgroup label="── 패스스루 ──">
                          {passthroughFields.map((pf) => (
                            <option key={pf.name} value={pf.name}>
                              {pf.name} ({pf.type})
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* 패스스루 데이터 (참고용) - collapsed by default */}
        <section>
          <button
            onClick={() => setPassthroughOpen((prev) => !prev)}
            className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wide w-full text-left hover:text-gray-200 transition-colors"
          >
            <svg
              className={`w-3 h-3 transition-transform flex-shrink-0 ${passthroughOpen ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            패스스루 데이터 (참고용)
            <span className="ml-auto text-gray-600 normal-case tracking-normal font-normal">
              {passthroughFields.length}개
            </span>
          </button>
          {passthroughOpen && (
            <div className="mt-2">
              {passthroughFields.length === 0 ? (
                <p className="text-xs text-gray-500 italic">패스스루 필드 없음</p>
              ) : (
                <ul className="space-y-1">
                  {passthroughFields.map((field) => (
                    <li key={field.name} className="flex items-center gap-2 py-1 opacity-70">
                      <span className="text-xs text-gray-400 flex-1 truncate">{field.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${typeBadgeClass(field.type)}`}>
                        {field.type}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Buttons row */}
      <div className="px-4 py-3 border-t border-gray-700 flex gap-2 flex-shrink-0">
        <button
          onClick={handleAutoMap}
          className="flex-1 px-3 py-1.5 text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
        >
          자동매핑
        </button>
        <button
          onClick={handleReset}
          className="flex-1 px-3 py-1.5 text-xs font-medium bg-gray-600 hover:bg-gray-500 text-gray-200 rounded transition-colors"
        >
          초기화
        </button>
      </div>
    </div>
  );
}
