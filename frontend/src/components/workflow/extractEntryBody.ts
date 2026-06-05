/**
 * extractEntryBody — warehouse entry 의 본문 추출 헬퍼.
 *
 * backend `warehouse.py _entry_body()` (warehouse.py:427-458) 의 우선순위와 정확히 일치:
 *   1순위: data.data
 *   2순위: data.markdown
 *   3순위: data.response
 *   4순위: data.output
 *   fallback: data 전체 (JSON.stringify)
 *
 * §7.2 B-2 정정 — v1 의 `markdown → data` 순서 오류를 수정.
 *
 * displayKey 지원 (markdown-viewer 전용):
 *   resolveByDisplayKey(data, displayKey) — 점-경로 우선 탐색, 비어있으면 undefined 반환
 */

export type EntryBodyKind = 'text' | 'json';

export interface EntryBody {
  kind: EntryBodyKind;
  content: string;
}

/**
 * displayKey 가 지정된 경우 data 객체에서 해당 필드를 우선 탐색한다.
 * - 점-경로 지원 (예: "a.b.c")
 * - 값이 non-empty string → {kind:'text', content}
 * - 값이 object/array → {kind:'json', content}
 * - 필드 없음 / null / 빈 문자열 → undefined (caller 가 fallback)
 */
export function resolveByDisplayKey(
  data: unknown,
  displayKey: string,
): EntryBody | undefined {
  if (!displayKey || typeof data !== 'object' || data === null || Array.isArray(data)) {
    return undefined;
  }
  const parts = displayKey.split('.');
  let cursor: unknown = data;
  for (const part of parts) {
    if (typeof cursor !== 'object' || cursor === null || Array.isArray(cursor)) {
      return undefined;
    }
    cursor = (cursor as Record<string, unknown>)[part];
  }
  if (cursor === undefined || cursor === null) return undefined;
  if (typeof cursor === 'string') {
    return cursor.length > 0 ? { kind: 'text', content: cursor } : undefined;
  }
  if (typeof cursor === 'object') {
    return { kind: 'json', content: JSON.stringify(cursor, null, 2) };
  }
  // number / boolean
  return { kind: 'text', content: String(cursor) };
}

/**
 * warehouse entry 의 data 객체에서 본문을 추출한다.
 * - string 이면 kind='text'
 * - object/array 이면 kind='json', content 는 JSON.stringify 한 값
 * - number/boolean 이면 kind='text', content 는 String()
 */
export function extractEntryBody(data: unknown): EntryBody {
  if (data === null || data === undefined) {
    return { kind: 'text', content: '' };
  }

  // data 가 object 인 경우에만 키 우선순위 탐색
  if (typeof data === 'object' && !Array.isArray(data)) {
    const obj = data as Record<string, unknown>;

    // 1순위: data.data
    if (obj.data !== undefined) {
      return extractBodyFromValue(obj.data);
    }
    // 2순위: data.markdown
    if (obj.markdown !== undefined) {
      return extractBodyFromValue(obj.markdown);
    }
    // 3순위: data.response
    if (obj.response !== undefined) {
      return extractBodyFromValue(obj.response);
    }
    // 4순위: data.output
    if (obj.output !== undefined) {
      return extractBodyFromValue(obj.output);
    }
    // fallback: 전체 JSON
    return { kind: 'json', content: JSON.stringify(obj, null, 2) };
  }

  // data 자체가 배열인 경우 JSON 직렬화
  if (Array.isArray(data)) {
    return { kind: 'json', content: JSON.stringify(data, null, 2) };
  }

  // primitive
  return { kind: 'text', content: String(data) };
}

function extractBodyFromValue(value: unknown): EntryBody {
  if (value === null || value === undefined) {
    return { kind: 'text', content: '' };
  }
  if (typeof value === 'string') {
    return { kind: 'text', content: value };
  }
  if (typeof value === 'object') {
    return { kind: 'json', content: JSON.stringify(value, null, 2) };
  }
  return { kind: 'text', content: String(value) };
}
