import type { KnowledgeFilterCondition } from '../../types';

// ─── Operator options ────────────────────────────────────────────────────────

const OPERATORS: { value: KnowledgeFilterCondition['operator']; label: string }[] = [
  { value: 'equals', label: '같은' },
  { value: 'contains', label: '포함' },
  { value: 'in', label: '중 하나' },
  { value: 'not_in', label: '중 아닌' },
];

// ─── Single filter row ───────────────────────────────────────────────────────

function FilterRow({
  filter,
  onChange,
  onRemove,
  index,
}: {
  filter: KnowledgeFilterCondition;
  onChange: (updated: KnowledgeFilterCondition) => void;
  onRemove: () => void;
  index: number;
}) {
  // value is always shown as comma-separated string in the editor
  const valueStr = Array.isArray(filter.value) ? filter.value.join(', ') : filter.value;

  const setValueFromInput = (raw: string) => {
    // "in" / "not_in" operators → array; otherwise string
    if (filter.operator === 'in' || filter.operator === 'not_in') {
      onChange({
        ...filter,
        value: raw.split(',').map((s) => s.trim()).filter(Boolean),
      });
    } else {
      onChange({ ...filter, value: raw });
    }
  };

  return (
    <div className="flex items-center gap-2 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2">
      {/* Index badge */}
      <span className="text-xs text-gray-600 bg-gray-800 px-1.5 py-0.5 rounded font-mono w-5 text-center shrink-0">
        {index + 1}
      </span>

      {/* field 선택 */}
      <select
        value={filter.field}
        onChange={(e) =>
          onChange({ ...filter, field: e.target.value as KnowledgeFilterCondition['field'] })
        }
        className="w-28 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-purple-500"
      >
        <option value="tag">태그</option>
        <option value="metadata">메타데이터</option>
      </select>

      {/* metadata key (only when field === 'metadata') */}
      {filter.field === 'metadata' && (
        <input
          type="text"
          value={filter.key || ''}
          onChange={(e) => onChange({ ...filter, key: e.target.value })}
          placeholder="키명"
          className="w-24 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500"
        />
      )}

      {/* operator 선택 */}
      <select
        value={filter.operator}
        onChange={(e) => {
          const op = e.target.value as KnowledgeFilterCondition['operator'];
          // when switching to in/not_in, wrap value into array
          const val =
            op === 'in' || op === 'not_in'
              ? (Array.isArray(filter.value) ? filter.value : [filter.value as string])
              : (Array.isArray(filter.value) ? filter.value[0] || '' : filter.value);
          onChange({ ...filter, operator: op, value: val });
        }}
        className="w-20 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-purple-300 focus:outline-none focus:ring-1 focus:ring-purple-500"
      >
        {OPERATORS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      {/* value 입력 */}
      <input
        type="text"
        value={valueStr}
        onChange={(e) => setValueFromInput(e.target.value)}
        placeholder={
          filter.operator === 'in' || filter.operator === 'not_in'
            ? 'tag1, tag2, tag3'
            : '값'
        }
        className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1.5 text-xs text-green-300 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500 font-mono"
      />

      {/* Delete */}
      <button
        onClick={onRemove}
        className="text-gray-500 hover:text-red-400 transition-colors text-sm shrink-0"
        title="필터 삭제"
      >
        ✕
      </button>
    </div>
  );
}

// ─── Public: KnowledgeFilterEditor ───────────────────────────────────────────

export function KnowledgeFilterEditor({
  filters,
  onChange,
}: {
  filters: KnowledgeFilterCondition[];
  onChange: (filters: KnowledgeFilterCondition[]) => void;
}) {
  const addFilter = () => {
    onChange([
      ...filters,
      { field: 'tag', operator: 'in', value: [] },
    ]);
  };

  const removeFilter = (idx: number) => {
    onChange(filters.filter((_, i) => i !== idx));
  };

  const updateFilter = (idx: number, updated: KnowledgeFilterCondition) => {
    onChange(filters.map((f, i) => (i === idx ? updated : f)));
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="block text-sm text-gray-400">필터 조건</label>
        <button
          onClick={addFilter}
          className="px-3 py-1 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-xs transition-colors"
        >
          + 필터 추가
        </button>
      </div>

      <div className="space-y-2">
        {filters.length === 0 ? (
          <div className="border border-dashed border-gray-700 rounded-lg py-4 text-center">
            <p className="text-gray-600 text-xs">필터 조건이 없습니다</p>
            <button
              onClick={addFilter}
              className="mt-1 text-purple-400 hover:text-purple-300 text-xs transition-colors"
            >
              + 첫 번째 필터 추가
            </button>
          </div>
        ) : (
          filters.map((filter, idx) => (
            <FilterRow
              key={idx}
              filter={filter}
              index={idx}
              onChange={(updated) => updateFilter(idx, updated)}
              onRemove={() => removeFilter(idx)}
            />
          ))
        )}
      </div>

      {/* Visual summary */}
      {filters.length > 0 && (
        <div className="mt-3 p-2 bg-gray-900 rounded border border-gray-700">
          <p className="text-xs text-gray-500">
            <span className="text-gray-400">검색 조건:</span>{' '}
            {filters.map((f, i) => {
              const valStr = Array.isArray(f.value) ? f.value.join(', ') : f.value;
              return (
                <span key={i}>
                  {i > 0 && <span className="text-blue-400 mx-1">AND</span>}
                  <span className="text-gray-300">{f.field}{f.key ? `.${f.key}` : ''}</span>
                  {' '}
                  <span className="text-purple-400">{f.operator}</span>
                  {' '}
                  <span className="text-green-300">[{valStr}]</span>
                </span>
              );
            })}
          </p>
        </div>
      )}
    </div>
  );
}
