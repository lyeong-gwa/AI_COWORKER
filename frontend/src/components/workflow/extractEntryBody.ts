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
 */

export type EntryBodyKind = 'text' | 'json';

export interface EntryBody {
  kind: EntryBodyKind;
  content: string;
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
