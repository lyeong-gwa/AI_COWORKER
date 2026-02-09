import type { NodeDefinition, NodeCategory } from '../types';

// ============================================
// 노드 정의 (팔레트에 표시되는 노드 템플릿)
// ============================================

export const nodeDefinitions: NodeDefinition[] = [
  // --- TRIGGER 노드들 ---
  {
    type: 'manual-trigger',
    name: '수동 실행',
    description: '버튼 클릭으로 워크플로우 시작',
    category: 'trigger',
    icon: '▶️',
    color: 'bg-green-600',
    inputs: [],
    outputs: [
      { id: 'trigger', name: 'trigger', dataType: 'any', description: '트리거 신호' }
    ],
    configFields: [],
    defaultConfig: {},
  },
  {
    type: 'schedule-trigger',
    name: '스케줄 실행',
    description: 'Cron 표현식으로 주기적 실행',
    category: 'trigger',
    icon: '⏰',
    color: 'bg-green-600',
    inputs: [],
    outputs: [
      { id: 'trigger', name: 'trigger', dataType: 'any' }
    ],
    configFields: [
      {
        key: 'cronExpression',
        label: 'Cron 표현식',
        type: 'text',
        required: true,
        placeholder: '0 9 * * *',
        description: '예: 0 9 * * * (매일 오전 9시)',
      },
      {
        key: 'timezone',
        label: '타임존',
        type: 'select',
        defaultValue: 'Asia/Seoul',
        options: [
          { label: '서울 (KST)', value: 'Asia/Seoul' },
          { label: 'UTC', value: 'UTC' },
          { label: '도쿄 (JST)', value: 'Asia/Tokyo' },
        ],
      },
    ],
    defaultConfig: {
      cronExpression: '0 9 * * *',
      timezone: 'Asia/Seoul',
    },
  },
  {
    type: 'webhook-trigger',
    name: 'Webhook',
    description: 'HTTP 요청을 받아 워크플로우 시작',
    category: 'trigger',
    icon: '🌐',
    color: 'bg-green-600',
    inputs: [],
    outputs: [
      { id: 'body', name: 'body', dataType: 'object', description: '요청 본문' },
      { id: 'headers', name: 'headers', dataType: 'object', description: '요청 헤더' },
    ],
    configFields: [
      {
        key: 'method',
        label: 'HTTP 메서드',
        type: 'select',
        required: true,
        options: [
          { label: 'POST', value: 'POST' },
          { label: 'GET', value: 'GET' },
          { label: 'PUT', value: 'PUT' },
        ],
      },
      {
        key: 'path',
        label: '경로',
        type: 'text',
        required: true,
        placeholder: '/webhook/my-workflow',
      },
    ],
    defaultConfig: {
      method: 'POST',
      path: '/webhook/',
    },
  },

  // --- LOGIC 노드들 ---
  {
    type: 'condition',
    name: '조건 분기 (IF)',
    description: '조건에 따라 다른 경로로 분기',
    category: 'logic',
    icon: '🔀',
    color: 'bg-purple-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any', required: true }
    ],
    outputs: [
      { id: 'true', name: 'true', dataType: 'any', description: '조건 충족 시' },
      { id: 'false', name: 'false', dataType: 'any', description: '조건 미충족 시' },
    ],
    configFields: [
      {
        key: 'conditions',
        label: '조건 설정',
        type: 'condition',
        required: true,
        description: '분기 조건을 정의합니다',
      },
    ],
    defaultConfig: {
      conditions: [],
    },
  },
  {
    type: 'switch',
    name: '다중 분기 (Switch)',
    description: '여러 조건에 따라 다중 분기',
    category: 'logic',
    icon: '🔀',
    color: 'bg-purple-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any', required: true }
    ],
    outputs: [], // 동적으로 생성됨
    configFields: [
      {
        key: 'mode',
        label: '분기 모드',
        type: 'select',
        options: [
          { label: '첫 번째 일치', value: 'first_match' },
          { label: '모든 일치', value: 'all_match' },
        ],
        defaultValue: 'first_match',
      },
      {
        key: 'branches',
        label: '분기 조건들',
        type: 'condition',
        required: true,
      },
    ],
    defaultConfig: {
      mode: 'first_match',
      branches: [],
    },
  },
  {
    type: 'loop',
    name: '반복 (Loop)',
    description: '배열의 각 항목에 대해 반복 실행',
    category: 'logic',
    icon: '🔄',
    color: 'bg-purple-600',
    inputs: [
      { id: 'items', name: 'items', dataType: 'array', required: true }
    ],
    outputs: [
      { id: 'item', name: 'item', dataType: 'any', description: '현재 항목' },
      { id: 'index', name: 'index', dataType: 'number', description: '현재 인덱스' },
      { id: 'done', name: 'done', dataType: 'array', description: '완료 후 결과' },
    ],
    configFields: [
      {
        key: 'batchSize',
        label: '배치 크기',
        type: 'number',
        defaultValue: 1,
        description: '동시 처리할 항목 수',
        validation: { min: 1, max: 100 },
      },
    ],
    defaultConfig: {
      batchSize: 1,
    },
  },
  {
    type: 'merge',
    name: '병합 (Merge)',
    description: '여러 입력을 하나로 병합',
    category: 'logic',
    icon: '🔗',
    color: 'bg-purple-600',
    inputs: [
      { id: 'input1', name: 'input1', dataType: 'any' },
      { id: 'input2', name: 'input2', dataType: 'any' },
    ],
    outputs: [
      { id: 'merged', name: 'merged', dataType: 'any' }
    ],
    configFields: [
      {
        key: 'mode',
        label: '병합 모드',
        type: 'select',
        options: [
          { label: '모두 대기 (Wait All)', value: 'wait_all' },
          { label: '하나라도 (Any)', value: 'any' },
          { label: '배열 합치기', value: 'concat' },
        ],
      },
    ],
    defaultConfig: {
      mode: 'wait_all',
    },
  },

  // --- TRANSFORM 노드들 ---
  {
    type: 'set-variable',
    name: '변수 설정',
    description: '워크플로우 변수 설정',
    category: 'transform',
    icon: '📝',
    color: 'bg-yellow-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any' }
    ],
    outputs: [
      { id: 'output', name: 'output', dataType: 'any' }
    ],
    configFields: [
      {
        key: 'assignments',
        label: '변수 할당',
        type: 'keyvalue',
        required: true,
        description: '변수명과 값을 설정합니다',
      },
    ],
    defaultConfig: {
      assignments: [],
    },
  },
  {
    type: 'code',
    name: '코드 실행',
    description: 'JavaScript 코드 실행',
    category: 'transform',
    icon: '💻',
    color: 'bg-yellow-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any' }
    ],
    outputs: [
      { id: 'output', name: 'output', dataType: 'any' }
    ],
    configFields: [
      {
        key: 'code',
        label: '코드',
        type: 'code',
        required: true,
        codeLanguage: 'javascript',
        placeholder: '// input 변수로 데이터 접근\n// return으로 결과 반환\nreturn { ...input, processed: true };',
      },
    ],
    defaultConfig: {
      code: '// input 변수로 데이터 접근\nreturn input;',
    },
  },
  {
    type: 'json-parse',
    name: 'JSON 파싱',
    description: 'JSON 문자열을 객체로 변환',
    category: 'transform',
    icon: '{}',
    color: 'bg-yellow-600',
    inputs: [
      { id: 'json', name: 'json', dataType: 'string', required: true }
    ],
    outputs: [
      { id: 'object', name: 'object', dataType: 'object' }
    ],
    configFields: [],
    defaultConfig: {},
  },

  // --- ACTION 노드들 ---
  {
    type: 'http-request',
    name: 'HTTP 요청',
    description: '외부 API 호출',
    category: 'action',
    icon: '🌐',
    color: 'bg-blue-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any' }
    ],
    outputs: [
      { id: 'response', name: 'response', dataType: 'object' },
      { id: 'error', name: 'error', dataType: 'object' },
    ],
    configFields: [
      {
        key: 'method',
        label: 'HTTP 메서드',
        type: 'select',
        required: true,
        options: [
          { label: 'GET', value: 'GET' },
          { label: 'POST', value: 'POST' },
          { label: 'PUT', value: 'PUT' },
          { label: 'DELETE', value: 'DELETE' },
          { label: 'PATCH', value: 'PATCH' },
        ],
      },
      {
        key: 'url',
        label: 'URL',
        type: 'text',
        required: true,
        placeholder: 'https://api.example.com/endpoint',
      },
      {
        key: 'headers',
        label: '헤더',
        type: 'keyvalue',
        description: '요청 헤더',
      },
      {
        key: 'body',
        label: '요청 본문',
        type: 'code',
        codeLanguage: 'json',
        description: 'POST/PUT/PATCH 요청 시 본문',
      },
      {
        key: 'timeout',
        label: '타임아웃 (ms)',
        type: 'number',
        defaultValue: 30000,
        validation: { min: 1000, max: 300000 },
      },
    ],
    defaultConfig: {
      method: 'GET',
      url: '',
      headers: [],
      body: '',
      timeout: 30000,
    },
  },
  {
    type: 'send-email',
    name: '이메일 전송',
    description: '이메일 발송',
    category: 'action',
    icon: '📧',
    color: 'bg-blue-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any' }
    ],
    outputs: [
      { id: 'result', name: 'result', dataType: 'object' }
    ],
    configFields: [
      {
        key: 'to',
        label: '받는 사람',
        type: 'text',
        required: true,
        placeholder: 'recipient@example.com',
      },
      {
        key: 'subject',
        label: '제목',
        type: 'text',
        required: true,
      },
      {
        key: 'body',
        label: '본문',
        type: 'textarea',
        required: true,
      },
      {
        key: 'isHtml',
        label: 'HTML 형식',
        type: 'boolean',
        defaultValue: false,
      },
    ],
    defaultConfig: {
      to: '',
      subject: '',
      body: '',
      isHtml: false,
    },
  },

  // --- AI 노드들 ---
  {
    type: 'ai-chat',
    name: 'AI 채팅',
    description: 'LLM과 대화',
    category: 'ai',
    icon: '🤖',
    color: 'bg-pink-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any' },
      { id: 'context', name: 'context', dataType: 'string', description: '추가 컨텍스트' },
    ],
    outputs: [
      { id: 'response', name: 'response', dataType: 'string' },
      { id: 'full', name: 'full', dataType: 'object', description: '전체 응답 객체' },
    ],
    configFields: [
      {
        key: 'model',
        label: '모델',
        type: 'select',
        required: true,
        options: [
          { label: 'GPT-4o', value: 'gpt-4o' },
          { label: 'GPT-4o Mini', value: 'gpt-4o-mini' },
          { label: 'Claude 3.5 Sonnet', value: 'claude-3-5-sonnet' },
          { label: 'Claude 3 Opus', value: 'claude-3-opus' },
        ],
      },
      {
        key: 'systemPrompt',
        label: '시스템 프롬프트',
        type: 'textarea',
        placeholder: 'AI의 역할과 행동 지침을 정의합니다',
      },
      {
        key: 'userPrompt',
        label: '사용자 프롬프트',
        type: 'textarea',
        required: true,
        placeholder: '{{input.data}} 형식으로 입력 데이터 참조 가능',
      },
      {
        key: 'temperature',
        label: '온도 (창의성)',
        type: 'number',
        defaultValue: 0.7,
        validation: { min: 0, max: 2 },
      },
      {
        key: 'maxTokens',
        label: '최대 토큰',
        type: 'number',
        defaultValue: 1000,
        validation: { min: 1, max: 128000 },
      },
    ],
    defaultConfig: {
      model: 'gpt-4o-mini',
      systemPrompt: '',
      userPrompt: '',
      temperature: 0.7,
      maxTokens: 1000,
    },
  },
  {
    type: 'ai-classify',
    name: 'AI 분류',
    description: '텍스트를 카테고리로 분류',
    category: 'ai',
    icon: '🏷️',
    color: 'bg-pink-600',
    inputs: [
      { id: 'text', name: 'text', dataType: 'string', required: true }
    ],
    outputs: [
      { id: 'category', name: 'category', dataType: 'string' },
      { id: 'confidence', name: 'confidence', dataType: 'number' },
      { id: 'all', name: 'all', dataType: 'array', description: '모든 카테고리 점수' },
    ],
    configFields: [
      {
        key: 'categories',
        label: '카테고리 목록',
        type: 'textarea',
        required: true,
        placeholder: '업무\n개인\n스팸\n기타',
        description: '줄바꿈으로 구분',
      },
      {
        key: 'model',
        label: '모델',
        type: 'select',
        options: [
          { label: 'GPT-4o Mini (빠름)', value: 'gpt-4o-mini' },
          { label: 'GPT-4o (정확)', value: 'gpt-4o' },
        ],
        defaultValue: 'gpt-4o-mini',
      },
    ],
    defaultConfig: {
      categories: '',
      model: 'gpt-4o-mini',
    },
  },
  {
    type: 'ai-extract',
    name: 'AI 데이터 추출',
    description: '텍스트에서 구조화된 데이터 추출',
    category: 'ai',
    icon: '📊',
    color: 'bg-pink-600',
    inputs: [
      { id: 'text', name: 'text', dataType: 'string', required: true }
    ],
    outputs: [
      { id: 'data', name: 'data', dataType: 'object' }
    ],
    configFields: [
      {
        key: 'schema',
        label: '추출 스키마 (JSON)',
        type: 'code',
        required: true,
        codeLanguage: 'json',
        placeholder: '{\n  "name": "string",\n  "email": "string",\n  "phone": "string"\n}',
      },
      {
        key: 'model',
        label: '모델',
        type: 'select',
        options: [
          { label: 'GPT-4o Mini', value: 'gpt-4o-mini' },
          { label: 'GPT-4o', value: 'gpt-4o' },
        ],
        defaultValue: 'gpt-4o-mini',
      },
    ],
    defaultConfig: {
      schema: '{}',
      model: 'gpt-4o-mini',
    },
  },

  // --- OUTPUT 노드들 ---
  {
    type: 'output-log',
    name: '로그 출력',
    description: '실행 결과를 로그로 기록',
    category: 'output',
    icon: '📋',
    color: 'bg-orange-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any', required: true }
    ],
    outputs: [],
    configFields: [
      {
        key: 'level',
        label: '로그 레벨',
        type: 'select',
        options: [
          { label: 'Info', value: 'info' },
          { label: 'Warning', value: 'warn' },
          { label: 'Error', value: 'error' },
          { label: 'Debug', value: 'debug' },
        ],
        defaultValue: 'info',
      },
      {
        key: 'message',
        label: '메시지 템플릿',
        type: 'text',
        placeholder: '처리 완료: {{input.count}}건',
      },
    ],
    defaultConfig: {
      level: 'info',
      message: '',
    },
  },
  {
    type: 'output-webhook',
    name: 'Webhook 전송',
    description: '결과를 Webhook으로 전송',
    category: 'output',
    icon: '📤',
    color: 'bg-orange-600',
    inputs: [
      { id: 'input', name: 'input', dataType: 'any', required: true }
    ],
    outputs: [],
    configFields: [
      {
        key: 'url',
        label: 'Webhook URL',
        type: 'text',
        required: true,
        placeholder: 'https://hooks.example.com/...',
      },
      {
        key: 'method',
        label: 'HTTP 메서드',
        type: 'select',
        options: [
          { label: 'POST', value: 'POST' },
          { label: 'PUT', value: 'PUT' },
        ],
        defaultValue: 'POST',
      },
    ],
    defaultConfig: {
      url: '',
      method: 'POST',
    },
  },
];

// 카테고리별 그룹핑
export const nodeCategories: { category: NodeCategory; label: string; icon: string }[] = [
  { category: 'trigger', label: '트리거', icon: '⚡' },
  { category: 'logic', label: '로직', icon: '🔀' },
  { category: 'transform', label: '변환', icon: '🔄' },
  { category: 'action', label: '액션', icon: '🔧' },
  { category: 'ai', label: 'AI', icon: '🤖' },
  { category: 'output', label: '출력', icon: '📤' },
];

// 노드 정의를 타입으로 조회
export function getNodeDefinition(type: string): NodeDefinition | undefined {
  return nodeDefinitions.find((n) => n.type === type);
}

// 카테고리별 노드 목록
export function getNodesByCategory(category: NodeCategory): NodeDefinition[] {
  return nodeDefinitions.filter((n) => n.category === category);
}
