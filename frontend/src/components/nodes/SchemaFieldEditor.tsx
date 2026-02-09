import type { JsonSchemaProperty } from '../../types';

// ============================================
// Internal: a single editable field row
// ============================================

const TYPES: { value: JsonSchemaProperty['type']; label: string; icon: string }[] = [
  { value: 'string', label: 'String', icon: 'Aa' },
  { value: 'number', label: 'Number', icon: '##' },
  { value: 'boolean', label: 'Boolean', icon: 'T/F' },
  { value: 'object', label: 'Object', icon: '{}' },
  { value: 'array', label: 'Array', icon: '[]' },
];

/**
 * Flat representation of one schema field used during editing.
 * Converted to / from JsonSchemaProperty on mount / save.
 */
export interface SchemaFieldRow {
  /** Stable key within the editor list */
  id: string;
  /** The property name in the parent object */
  name: string;
  type: JsonSchemaProperty['type'];
  description: string;
  required: boolean;
  /** Serialised default value (empty string = none) */
  defaultValue: string;
  /** Comma-separated enum options (only meaningful for string) */
  enumOptions: string;
}

// ─── Converters ──────────────────────────────────────────────────────────────

let _uid = 0;
function uid() {
  return `field-${Date.now()}-${++_uid}`;
}

/**
 * Convert a JsonSchema `properties` + `required` array into a flat list
 * suitable for the form editor.
 */
export function schemaToRows(
  properties: Record<string, JsonSchemaProperty>,
  required: string[] | undefined
): SchemaFieldRow[] {
  return Object.entries(properties).map(([name, prop]) => ({
    id: uid(),
    name,
    type: prop.type,
    description: prop.description || '',
    required: required?.includes(name) ?? false,
    defaultValue: prop.default !== undefined ? JSON.stringify(prop.default) : '',
    enumOptions: prop.enum ? prop.enum.join(', ') : '',
  }));
}

/**
 * Convert the editor rows back into a JsonSchema-compatible shape.
 */
export function rowsToSchema(rows: SchemaFieldRow[]): {
  properties: Record<string, JsonSchemaProperty>;
  required: string[];
} {
  const properties: Record<string, JsonSchemaProperty> = {};
  const required: string[] = [];

  rows.forEach((row) => {
    if (!row.name.trim()) return; // skip nameless rows

    const prop: JsonSchemaProperty = { type: row.type };
    if (row.description.trim()) prop.description = row.description.trim();
    if (row.defaultValue.trim()) {
      try {
        prop.default = JSON.parse(row.defaultValue);
      } catch {
        prop.default = row.defaultValue; // keep as string if not valid JSON
      }
    }
    if (row.enumOptions.trim()) {
      prop.enum = row.enumOptions.split(',').map((s) => s.trim()).filter(Boolean);
    }
    if (row.type === 'array') {
      prop.items = { type: 'string' }; // default items schema
    }
    if (row.type === 'object') {
      prop.properties = {};
    }

    properties[row.name.trim()] = prop;
    if (row.required) required.push(row.name.trim());
  });

  return { properties, required };
}

// ─── Single field row component ──────────────────────────────────────────────

function FieldRow({
  row,
  index,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  isFirst,
  isLast,
}: {
  row: SchemaFieldRow;
  index: number;
  onChange: (updated: SchemaFieldRow) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  isFirst: boolean;
  isLast: boolean;
}) {
  const set = <K extends keyof SchemaFieldRow>(key: K, val: SchemaFieldRow[K]) =>
    onChange({ ...row, [key]: val });

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
      {/* Row header: index badge + move buttons + delete */}
      <div className="flex items-center justify-between px-3 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-gray-500 bg-gray-700 px-2 py-0.5 rounded">
            #{index + 1}
          </span>
          <span
            className={`text-xs px-2 py-0.5 rounded ${
              row.required ? 'bg-red-900 text-red-300' : 'bg-gray-700 text-gray-400'
            }`}
          >
            {row.required ? '필수' : '선택'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onMoveUp}
            disabled={isFirst}
            className="p-1 text-gray-500 hover:text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="위로 이동"
          >
            ▲
          </button>
          <button
            onClick={onMoveDown}
            disabled={isLast}
            className="p-1 text-gray-500 hover:text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="아래로 이동"
          >
            ▼
          </button>
          <button
            onClick={onRemove}
            className="p-1 text-gray-500 hover:text-red-400 transition-colors ml-2"
            title="필드 삭제"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Field form grid */}
      <div className="p-3 grid grid-cols-12 gap-3">
        {/* 필드명 (col 4) */}
        <div className="col-span-4">
          <label className="block text-xs text-gray-500 mb-1">필드명 *</label>
          <input
            type="text"
            value={row.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="예: userId"
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* 타입 (col 3) */}
        <div className="col-span-3">
          <label className="block text-xs text-gray-500 mb-1">타입</label>
          <select
            value={row.type}
            onChange={(e) => set('type', e.target.value as JsonSchemaProperty['type'])}
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.icon} {t.label}
              </option>
            ))}
          </select>
        </div>

        {/* 필수 여부 (col 2) */}
        <div className="col-span-2 flex flex-col justify-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={row.required}
              onChange={(e) => set('required', e.target.checked)}
              className="w-4 h-4 accent-blue-500"
            />
            <span className="text-xs text-gray-400">필수</span>
          </label>
        </div>

        {/* 기본값 (col 3) */}
        <div className="col-span-3">
          <label className="block text-xs text-gray-500 mb-1">기본값</label>
          <input
            type="text"
            value={row.defaultValue}
            onChange={(e) => set('defaultValue', e.target.value)}
            placeholder={row.type === 'number' ? '0' : row.type === 'boolean' ? 'true/false' : '"값"'}
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* 설명 (col 7) */}
        <div className="col-span-7">
          <label className="block text-xs text-gray-500 mb-1">설명</label>
          <input
            type="text"
            value={row.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="이 필드의 역할을 설명하세요"
            className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        {/* Enum 옵션 (col 5) -- string 타입일 때만 활성 */}
        <div className="col-span-5">
          <label className="block text-xs text-gray-500 mb-1">
            Enum 옵션
            <span className={`ml-2 text-xs ${row.type === 'string' ? 'text-gray-600' : 'text-red-500'}`}>
              {row.type === 'string' ? '(쉼표로 구분)' : '(string 타입일 때만)'}
            </span>
          </label>
          <input
            type="text"
            value={row.enumOptions}
            onChange={(e) => set('enumOptions', e.target.value)}
            disabled={row.type !== 'string'}
            placeholder="예: active, inactive, pending"
            className={`w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 ${
              row.type !== 'string' ? 'opacity-40 cursor-not-allowed' : ''
            }`}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Public: SchemaFieldEditor ───────────────────────────────────────────────

/**
 * Props:
 *   rows      – current field list (managed by parent via schemaToRows)
 *   onChange  – called with updated list whenever user edits
 */
export function SchemaFieldEditor({
  title,
  badge,
  rows,
  onChange,
}: {
  title: string;
  badge: string;
  rows: SchemaFieldRow[];
  onChange: (rows: SchemaFieldRow[]) => void;
}) {
  const addField = () => {
    onChange([
      ...rows,
      {
        id: uid(),
        name: '',
        type: 'string',
        description: '',
        required: false,
        defaultValue: '',
        enumOptions: '',
      },
    ]);
  };

  const removeField = (idx: number) => {
    onChange(rows.filter((_, i) => i !== idx));
  };

  const updateField = (idx: number, updated: SchemaFieldRow) => {
    onChange(rows.map((r, i) => (i === idx ? updated : r)));
  };

  const moveField = (idx: number, dir: -1 | 1) => {
    const next = idx + dir;
    if (next < 0 || next >= rows.length) return;
    const copy = [...rows];
    [copy[idx], copy[next]] = [copy[next], copy[idx]];
    onChange(copy);
  };

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Panel header */}
      <div className="flex items-center justify-between mb-3 sticky top-0 bg-gray-800 -mx-1 px-1 py-2 z-10">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${badge}`}>{title}</span>
          <span className="text-xs text-gray-500 bg-gray-700 px-2 py-0.5 rounded-full">
            {rows.length}개 필드
          </span>
        </div>
        <button
          onClick={addField}
          className="flex items-center gap-1 px-3 py-1 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-xs transition-colors"
        >
          <span className="text-base leading-none">+</span>
          필드 추가
        </button>
      </div>

      {/* Field list */}
      <div className="space-y-2 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="border-2 border-dashed border-gray-700 rounded-lg py-6 text-center">
            <p className="text-gray-500 text-sm">필드가 없습니다</p>
            <button
              onClick={addField}
              className="mt-2 text-blue-400 hover:text-blue-300 text-sm transition-colors"
            >
              + 첫 번째 필드 추가
            </button>
          </div>
        ) : (
          rows.map((row, idx) => (
            <FieldRow
              key={row.id}
              row={row}
              index={idx}
              onChange={(updated) => updateField(idx, updated)}
              onRemove={() => removeField(idx)}
              onMoveUp={() => moveField(idx, -1)}
              onMoveDown={() => moveField(idx, 1)}
              isFirst={idx === 0}
              isLast={idx === rows.length - 1}
            />
          ))
        )}
      </div>
    </div>
  );
}
