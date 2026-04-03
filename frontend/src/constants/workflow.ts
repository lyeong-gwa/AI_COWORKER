/**
 * 워크플로우 공유 상수
 *
 * 노드 정의 타입, 트리거 타입, 출력 필드, 스타일 등
 * 코드베이스 전반에서 사용되는 상수를 한 곳에 정의합니다.
 */

/**
 * 노드 정의 타입 (프론트엔드에서 실제 참조하는 타입만 포함)
 * 전체 목록은 backend/app/core/constants.py의 NodeDefType 참조
 */
export const DEF_TYPE = {
  // 트리거
  MANUAL: 'manual',
  SCHEDULE: 'schedule',
  WEBHOOK: 'webhook',
  FORM: 'form',
  FORM_START: 'form-start',
  API_START: 'api-start',
  // AI
  AI_CUSTOM: 'ai-custom',
  AI_API_ROUTER: 'ai-api-router',
  // 로직
  SORTER: 'sorter',
  UNPACKER: 'unpacker',
  MAPPER: 'mapper',
  // 액션
  API_CALL: 'api-call',
  KNOWLEDGE: 'knowledge',
  // 출력
  RESULT: 'result',
  MARKDOWN_VIEWER: 'markdown-viewer',
  // 액션 (산출물)
  DELIVERABLE_GENERATOR: 'deliverable-generator',
  // 산출물 파이프라인 (3-step)
  MILESTONE_COLLECTOR: 'milestone-collector',
  DEV_DELIVERABLE_GEN: 'dev-deliverable-gen',
  REVIEW_DELIVERABLE_GEN: 'review-deliverable-gen',
} as const;

export type DefinitionType = (typeof DEF_TYPE)[keyof typeof DEF_TYPE];

/** 트리거(시작) 노드 타입 집합 */
export const TRIGGER_TYPES: ReadonlySet<string> = new Set([
  DEF_TYPE.MANUAL,
  DEF_TYPE.SCHEDULE,
  DEF_TYPE.WEBHOOK,
  DEF_TYPE.FORM,
  DEF_TYPE.FORM_START,
  DEF_TYPE.API_START,
]);

/** 노드 타입별 고정 출력 필드 */
export const STATIC_OUTPUT_FIELDS: Record<string, { name: string; type: string }[]> = {
  [DEF_TYPE.API_CALL]: [
    { name: 'status', type: 'number' },
    { name: 'data', type: 'object' },
  ],
  [DEF_TYPE.API_START]: [
    { name: 'status', type: 'number' },
    { name: 'data', type: 'object' },
  ],
  [DEF_TYPE.KNOWLEDGE]: [{ name: 'knowledge', type: 'array' }],
  [DEF_TYPE.AI_API_ROUTER]: [
    { name: 'api_route', type: 'object' },
  ],
};

/** 벨트 필드 매핑 접두사 */
export const FIELD_MAPPING_PREFIX = '$.';

/** 엣지(컨베이어 벨트) 스타일 */
export const EDGE_STYLE = {
  stroke: '#f59e0b',
  strokeWidth: 2.5,
  strokeDasharray: '8 4',
} as const;

/** 매핑 뱃지 색상 (ConveyorBeltEdge용) */
export const MAPPING_BADGE_COLORS = {
  complete: { bg: 'bg-emerald-500/20', border: 'border-emerald-500/50', text: 'text-emerald-400' },
  partial: { bg: 'bg-amber-500/20', border: 'border-amber-500/50', text: 'text-amber-400' },
  none: { bg: 'bg-red-500/20', border: 'border-red-500/50', text: 'text-red-400' },
  noSchema: { bg: 'bg-gray-500/20', border: 'border-gray-500/50', text: 'text-gray-500' },
} as const;

export type MappingStatus = keyof typeof MAPPING_BADGE_COLORS;

