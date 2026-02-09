import type {
  TaskCard,
  TaskColumn,
  KnowledgeDocument,
  AINode,
  Workflow,
  User,
  ToolDefinition,
} from '../types';

// ============================================
// Users
// ============================================

export const mockUsers: User[] = [
  { id: 'user-1', name: '김철수', email: 'chulsoo@example.com' },
  { id: 'user-2', name: '이영희', email: 'younghee@example.com' },
  { id: 'user-3', name: 'AI Assistant', email: 'ai@example.com' },
];

// ============================================
// Task Board Data
// ============================================

export const mockTasks: TaskCard[] = [
  {
    id: 'task-1',
    title: 'API 엔드포인트 설계',
    description: 'REST API 엔드포인트 구조를 설계하고 문서화합니다.',
    status: 'done',
    priority: 'high',
    assigneeId: 'user-1',
    assigneeName: '김철수',
    todos: [
      { id: 'todo-1', text: 'GET /tasks 엔드포인트', completed: true },
      { id: 'todo-2', text: 'POST /tasks 엔드포인트', completed: true },
      { id: 'todo-3', text: 'Swagger 문서 작성', completed: true },
    ],
    comments: [
      {
        id: 'comment-1',
        authorId: 'user-2',
        authorName: '이영희',
        content: 'RESTful 규칙을 잘 따르고 있네요!',
        createdAt: '2024-01-15T10:30:00Z',
      },
    ],
    activityLog: [
      {
        id: 'log-1',
        userId: 'user-1',
        userName: '김철수',
        action: 'created',
        detail: '태스크를 생성했습니다.',
        timestamp: '2024-01-10T09:00:00Z',
      },
      {
        id: 'log-2',
        userId: 'user-1',
        userName: '김철수',
        action: 'status_changed',
        detail: '상태를 "완료"로 변경했습니다.',
        timestamp: '2024-01-15T14:00:00Z',
      },
    ],
    references: [
      {
        docId: 'doc-1',
        title: 'API 사용 가이드',
        content: '# API 사용 가이드\n\n## 인증\n모든 API 요청에는 Bearer 토큰이 필요합니다.\n\n## 엔드포인트\n- GET /api/tasks - 태스크 목록 조회\n- POST /api/tasks - 태스크 생성\n- PUT /api/tasks/:id - 태스크 수정\n- DELETE /api/tasks/:id - 태스크 삭제',
        category: 'technical',
        score: 0.92,
      },
    ],
    tags: ['backend', 'api', 'documentation'],
    dueDate: '2024-01-20',
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-15T14:00:00Z',
  },
  {
    id: 'task-2',
    title: '사용자 인증 구현',
    description: 'JWT 기반 사용자 인증 시스템을 구현합니다.',
    status: 'in-progress',
    priority: 'urgent',
    assigneeId: 'user-1',
    assigneeName: '김철수',
    todos: [
      { id: 'todo-4', text: 'JWT 토큰 발급 로직', completed: true },
      { id: 'todo-5', text: '미들웨어 구현', completed: true },
      { id: 'todo-6', text: '리프레시 토큰 구현', completed: false },
      { id: 'todo-7', text: '로그아웃 처리', completed: false },
    ],
    comments: [],
    activityLog: [
      {
        id: 'log-3',
        userId: 'user-1',
        userName: '김철수',
        action: 'created',
        detail: '태스크를 생성했습니다.',
        timestamp: '2024-01-12T09:00:00Z',
      },
    ],
    references: [],
    tags: ['backend', 'security', 'auth'],
    dueDate: '2024-01-25',
    createdAt: '2024-01-12T09:00:00Z',
    updatedAt: '2024-01-18T11:00:00Z',
  },
  {
    id: 'task-3',
    title: '대시보드 UI 디자인',
    description: '메인 대시보드의 UI/UX를 디자인합니다.',
    status: 'review',
    priority: 'medium',
    assigneeId: 'user-2',
    assigneeName: '이영희',
    todos: [
      { id: 'todo-8', text: '와이어프레임 작성', completed: true },
      { id: 'todo-9', text: '컬러 팔레트 선정', completed: true },
      { id: 'todo-10', text: '반응형 레이아웃', completed: true },
    ],
    comments: [],
    activityLog: [],
    references: [],
    tags: ['frontend', 'design', 'ui'],
    createdAt: '2024-01-14T09:00:00Z',
    updatedAt: '2024-01-17T16:30:00Z',
  },
  {
    id: 'task-4',
    title: '벡터 DB 연동',
    description: 'Pinecone 또는 Chroma DB와 연동하여 임베딩 저장소를 구축합니다.',
    status: 'todo',
    priority: 'high',
    todos: [],
    comments: [],
    activityLog: [],
    references: [],
    tags: ['backend', 'ai', 'database'],
    createdAt: '2024-01-16T09:00:00Z',
    updatedAt: '2024-01-16T09:00:00Z',
  },
  {
    id: 'task-5',
    title: '워크플로우 엔진 설계',
    description: '워크플로우 실행 엔진을 설계합니다.',
    status: 'backlog',
    priority: 'medium',
    todos: [],
    comments: [],
    activityLog: [],
    references: [],
    tags: ['architecture', 'workflow'],
    createdAt: '2024-01-18T09:00:00Z',
    updatedAt: '2024-01-18T09:00:00Z',
  },
];

export const mockColumns: TaskColumn[] = [
  {
    id: 'col-1',
    title: 'Backlog',
    status: 'backlog',
    cards: mockTasks.filter((t) => t.status === 'backlog'),
  },
  {
    id: 'col-2',
    title: 'To Do',
    status: 'todo',
    cards: mockTasks.filter((t) => t.status === 'todo'),
  },
  {
    id: 'col-3',
    title: 'In Progress',
    status: 'in-progress',
    cards: mockTasks.filter((t) => t.status === 'in-progress'),
  },
  {
    id: 'col-4',
    title: 'Review',
    status: 'review',
    cards: mockTasks.filter((t) => t.status === 'review'),
  },
  {
    id: 'col-5',
    title: 'Done',
    status: 'done',
    cards: mockTasks.filter((t) => t.status === 'done'),
  },
];

// ============================================
// Knowledge Base Data
// ============================================

export const mockDocuments: KnowledgeDocument[] = [
  {
    id: 'doc-1',
    filename: 'api-guide.md',
    title: 'API 사용 가이드',
    content: `# API 사용 가이드

## 인증
모든 API 요청에는 Bearer 토큰이 필요합니다.

## 엔드포인트
- GET /api/tasks - 태스크 목록 조회
- POST /api/tasks - 태스크 생성
- PUT /api/tasks/:id - 태스크 수정
- DELETE /api/tasks/:id - 태스크 삭제
`,
    summary: 'REST API 인증 및 CRUD 엔드포인트 가이드',
    source: '내부 개발팀',
    category: 'technical',
    vectorId: 'vec-001',
    syncStatus: 'synced',
    lastSyncedAt: '2024-01-15T10:00:00Z',
    tokenCount: 156,
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-15T10:00:00Z',
    tags: ['api', 'documentation'],
    metadata: { version: '1.0' },
  },
  {
    id: 'doc-2',
    filename: 'service-desk-faq.md',
    title: '서비스데스크 FAQ',
    content: `# 서비스데스크 자주 묻는 질문

## 계정 관련
Q: 비밀번호를 잊었습니다.
A: 로그인 페이지의 "비밀번호 찾기"를 클릭하세요.

Q: 계정 잠금이 되었습니다.
A: 관리자에게 문의하여 계정 잠금을 해제해주세요.

## 결제 관련
Q: 환불 절차가 어떻게 되나요?
A: 결제일로부터 7일 이내 환불 신청이 가능합니다.
`,
    summary: '계정, 결제 관련 자주 묻는 질문 모음',
    source: '고객지원팀',
    category: 'support',
    vectorId: 'vec-002',
    syncStatus: 'synced',
    lastSyncedAt: '2024-01-14T15:00:00Z',
    tokenCount: 180,
    createdAt: '2024-01-08T09:00:00Z',
    updatedAt: '2024-01-14T15:00:00Z',
    tags: ['faq', 'service-desk', 'customer-support'],
    metadata: { department: 'customer-service' },
  },
  {
    id: 'doc-3',
    filename: 'product-info.md',
    title: '제품 정보',
    content: `# 제품 정보

## 프리미엄 플랜
- 가격: 월 29,000원
- 무제한 API 호출
- 우선 지원

## 베이직 플랜
- 가격: 월 9,900원
- 월 1,000회 API 호출
- 이메일 지원
`,
    summary: '프리미엄/베이직 플랜 가격 및 기능 비교',
    source: '마케팅팀',
    category: 'product',
    syncStatus: 'pending',
    tokenCount: 120,
    createdAt: '2024-01-18T16:00:00Z',
    updatedAt: '2024-01-18T16:30:00Z',
    tags: ['product', 'pricing', 'service-desk'],
    metadata: { version: '2.0' },
  },
];

// ============================================
// Tool Definitions (라이브러리 – 중앙 관리용 도구)
// ============================================

export const mockToolDefinitions: ToolDefinition[] = [
  // ── API 호출기 ──────────────────────────────────────────────────────────
  {
    id: 'tool-def-sd-tickets',
    name: '서비스데스크 문의글 조회',
    description: '서비스데스크 API에서 문의글 목록을 조회하는 도구입니다',
    type: 'api_call',
    icon: '🎫',
    color: 'bg-blue-600',
    tags: ['service-desk', 'api', 'tickets'],
    config: {
      method: 'GET',
      urlTemplate: '{{input.baseUrl}}/api/tickets?status={{input.status}}&limit={{input.limit}}',
      headers: {
        'Authorization': 'Bearer {{env.SERVICE_DESK_TOKEN}}',
        'Content-Type': 'application/json',
      },
      responseMapping: 'data',
      auth: { type: 'bearer', value: '{{env.SERVICE_DESK_TOKEN}}' },
    },
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-15T14:00:00Z',
  },
  {
    id: 'tool-def-sd-comment',
    name: '서비스데스크 댓글 등록',
    description: '특정 문의글에 AI 생성 답변을 댓글로 등록합니다',
    type: 'api_call',
    icon: '💬',
    color: 'bg-green-600',
    tags: ['service-desk', 'api', 'comment', 'post'],
    config: {
      method: 'POST',
      urlTemplate: '{{input.baseUrl}}/api/tickets/{{item.ticketId}}/comments',
      headers: {
        'Authorization': 'Bearer {{env.SERVICE_DESK_TOKEN}}',
        'Content-Type': 'application/json',
      },
      bodyTemplate: '{"content": "{{item.replyContent}}", "author": "AI Assistant"}',
      auth: { type: 'bearer', value: '{{env.SERVICE_DESK_TOKEN}}' },
    },
    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-15T14:00:00Z',
  },
  {
    id: 'tool-def-slack-webhook',
    name: 'Slack 웹훅 알림',
    description: 'Slack 채널에 웹훅을 통해 메시지를 전송합니다',
    type: 'api_call',
    icon: '📣',
    color: 'bg-indigo-600',
    tags: ['slack', 'notification', 'webhook'],
    config: {
      method: 'POST',
      urlTemplate: '{{env.SLACK_WEBHOOK_URL}}',
      headers: { 'Content-Type': 'application/json' },
      bodyTemplate: '{"text": "{{input.message}}"}',
    },
    createdAt: '2024-01-11T10:00:00Z',
    updatedAt: '2024-01-11T10:00:00Z',
  },
  {
    id: 'tool-def-weather-api',
    name: '날씨 정보 조회',
    description: 'OpenWeatherMap API에서 현재 날씨 정보를 조회합니다',
    type: 'api_call',
    icon: '🌤️',
    color: 'bg-cyan-600',
    tags: ['weather', 'external', 'api'],
    config: {
      method: 'GET',
      urlTemplate: 'https://api.openweathermap.org/data/2.5/weather?q={{input.city}}&appid={{env.WEATHER_API_KEY}}&units=metric&lang=kr',
      headers: {},
      responseMapping: 'data',
    },
    createdAt: '2024-01-12T08:00:00Z',
    updatedAt: '2024-01-12T08:00:00Z',
  },

  // ── 파일 읽기 ───────────────────────────────────────────────────────────
  {
    id: 'tool-def-csv-reader',
    name: 'CSV 파일 읽기',
    description: 'CSV 파일을 읽어서 구조화된 배열로 변환합니다',
    type: 'file_read',
    icon: '📊',
    color: 'bg-yellow-600',
    tags: ['file', 'csv', 'data'],
    config: {
      pathTemplate: '/data/{{input.filename}}.csv',
      encoding: 'utf-8',
      parser: 'csv',
    },
    createdAt: '2024-01-11T09:00:00Z',
    updatedAt: '2024-01-11T09:00:00Z',
  },
  {
    id: 'tool-def-json-config',
    name: 'JSON 설정 파일 읽기',
    description: 'JSON 형식의 설정 파일을 로드합니다',
    type: 'file_read',
    icon: '⚙️',
    color: 'bg-orange-600',
    tags: ['file', 'json', 'config'],
    config: {
      pathTemplate: '/config/{{input.configName}}.json',
      encoding: 'utf-8',
      parser: 'json',
    },
    createdAt: '2024-01-12T09:00:00Z',
    updatedAt: '2024-01-12T09:00:00Z',
  },

  // ── 파일 쓰기 ───────────────────────────────────────────────────────────
  {
    id: 'tool-def-report-writer',
    name: '보고서 파일 저장',
    description: '처리 결과를 보고서 파일로 저장합니다',
    type: 'file_write',
    icon: '📄',
    color: 'bg-pink-600',
    tags: ['file', 'report', 'output'],
    config: {
      pathTemplate: '/reports/{{input.reportName}}_{{input.date}}.txt',
      contentTemplate: '보고서\n생성일: {{input.date}}\n\n{{input.content}}',
    },
    createdAt: '2024-01-13T09:00:00Z',
    updatedAt: '2024-01-13T09:00:00Z',
  },
  {
    id: 'tool-def-log-writer',
    name: '로그 파일 기록',
    description: '실행 과정을 로그 파일에 기록합니다',
    type: 'file_write',
    icon: '📝',
    color: 'bg-gray-600',
    tags: ['file', 'log', 'debug'],
    config: {
      pathTemplate: '/logs/{{input.module}}/{{input.timestamp}}.log',
      contentTemplate: '[{{input.timestamp}}] {{input.level}}: {{input.message}}',
    },
    createdAt: '2024-01-13T10:00:00Z',
    updatedAt: '2024-01-13T10:00:00Z',
  },

  // ── 코드 실행 ───────────────────────────────────────────────────────────
  {
    id: 'tool-def-data-transform',
    name: '데이터 변환 스크립트',
    description: 'JavaScript를 사용하여 입력 데이터를 변환합니다',
    type: 'code_execute',
    icon: '🔧',
    color: 'bg-purple-600',
    tags: ['code', 'transform', 'javascript'],
    config: {
      language: 'javascript',
      code: `// input 변수로 데이터 접근
const items = input.data || [];
const transformed = items.map(item => ({
  ...item,
  processed: true,
  timestamp: new Date().toISOString(),
}));
return { items: transformed, count: transformed.length };`,
    },
    createdAt: '2024-01-14T09:00:00Z',
    updatedAt: '2024-01-14T09:00:00Z',
  },
  {
    id: 'tool-def-python-analysis',
    name: 'Python 데이터 분석',
    description: 'Python을 사용한 간단한 통계 분석을 수행합니다',
    type: 'code_execute',
    icon: '🐍',
    color: 'bg-blue-600',
    tags: ['code', 'python', 'analysis'],
    config: {
      language: 'python',
      code: `import json

data = input.get('values', [])
if data:
    avg = sum(data) / len(data)
    result = {
        'count': len(data),
        'sum': sum(data),
        'avg': round(avg, 2),
        'min': min(data),
        'max': max(data),
    }
else:
    result = {'count': 0}
return result`,
    },
    createdAt: '2024-01-14T10:00:00Z',
    updatedAt: '2024-01-14T10:00:00Z',
  },

  // ── DB 쿼리 ─────────────────────────────────────────────────────────────
  {
    id: 'tool-def-user-lookup',
    name: '사용자 조회',
    description: '사용자 ID로 사용자 정보를 조회합니다',
    type: 'database_query',
    icon: '👤',
    color: 'bg-teal-600',
    tags: ['database', 'user', 'query'],
    config: {
      connectionId: 'pg-main',
      queryTemplate: "SELECT id, name, email, created_at FROM users WHERE id = '{{input.userId}}'",
    },
    createdAt: '2024-01-15T09:00:00Z',
    updatedAt: '2024-01-15T09:00:00Z',
  },
  {
    id: 'tool-def-task-stats',
    name: '태스크 통계 조회',
    description: '상태별 태스크 수를 집계합니다',
    type: 'database_query',
    icon: '📈',
    color: 'bg-emerald-600',
    tags: ['database', 'stats', 'task'],
    config: {
      connectionId: 'pg-main',
      queryTemplate: "SELECT status, COUNT(*) as cnt FROM tasks WHERE project_id = '{{input.projectId}}' GROUP BY status ORDER BY cnt DESC",
    },
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '2024-01-15T10:00:00Z',
  },
];

// Helper: 도구 타입으로 필터링
export function getToolDefinitionsByType(type: string): ToolDefinition[] {
  return mockToolDefinitions.filter(t => t.type === type);
}

// Helper: 도구 ID로 찾기
export function getToolDefinitionById(id: string): ToolDefinition | undefined {
  return mockToolDefinitions.find(t => t.id === id);
}

// ============================================
// AI Nodes (재사용 가능한 LLM 노드)
// ============================================

export const mockAINodes: AINode[] = [
  // 노드 1: 서비스데스크 문의글 조회
  {
    id: 'node-fetch-tickets',
    name: '문의글 조회',
    description: '서비스데스크 API에서 미응답 문의글 목록을 조회합니다',
    icon: '📥',
    color: 'bg-blue-600',
    tags: ['service-desk', 'api', 'fetch'],

    inputSchema: {
      type: 'object',
      description: '문의글 조회 조건',
      properties: {
        baseUrl: {
          type: 'string',
          description: 'API 기본 URL',
        },
        status: {
          type: 'string',
          description: '문의 상태 필터',
          enum: ['unanswered', 'pending', 'all'],
          default: 'unanswered',
        },
        limit: {
          type: 'number',
          description: '조회할 최대 건수',
          default: 10,
        },
      },
      required: ['baseUrl'],
    },

    outputSchema: {
      type: 'object',
      description: '조회된 문의글 목록',
      properties: {
        tickets: {
          type: 'array',
          description: '문의글 배열',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string', description: '문의글 ID' },
              title: { type: 'string', description: '제목' },
              content: { type: 'string', description: '문의 내용' },
              author: { type: 'string', description: '작성자' },
              createdAt: { type: 'string', description: '작성일' },
              category: { type: 'string', description: '카테고리' },
            },
          },
        },
        totalCount: {
          type: 'number',
          description: '전체 건수',
        },
      },
      required: ['tickets', 'totalCount'],
    },

    // 연결된 도구 (라이브러리 참조)
    linkedToolIds: ['tool-def-sd-tickets'],

    tools: [], // deprecated

    knowledge: {
      enabled: false,
      filters: [],
      maxChunks: 0,
      includeInPrompt: false,
    },

    systemPrompt: '당신은 API 응답 데이터를 정해진 JSON 포맷으로 변환하는 전문가입니다. 불필요한 필드는 제거하고 필요한 필드만 추출하세요.',
    userPromptTemplate: `API 응답 데이터:
{{toolResults.tool-def-sd-tickets}}

위 데이터를 outputSchema에 맞게 변환하여 JSON으로 반환하세요.`,

    llmConfig: {
      model: 'gpt-4o-mini',
      temperature: 0.1,
      maxTokens: 2000,
      responseFormat: 'json',
    },

    createdAt: '2024-01-10T09:00:00Z',
    updatedAt: '2024-01-15T14:00:00Z',
  },

  // 노드 2: 답변 생성
  {
    id: 'node-generate-reply',
    name: '답변 생성',
    description: '문의글에 대한 AI 답변을 생성합니다',
    icon: '💬',
    color: 'bg-purple-600',
    tags: ['service-desk', 'ai', 'reply', 'generation'],

    inputSchema: {
      type: 'object',
      description: '답변 생성을 위한 입력',
      properties: {
        tickets: {
          type: 'array',
          description: '답변할 문의글 목록',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              title: { type: 'string' },
              content: { type: 'string' },
              author: { type: 'string' },
              category: { type: 'string' },
            },
          },
        },
      },
      required: ['tickets'],
    },

    outputSchema: {
      type: 'object',
      description: '생성된 답변 목록',
      properties: {
        replies: {
          type: 'array',
          description: '답변 배열',
          items: {
            type: 'object',
            properties: {
              ticketId: { type: 'string', description: '원본 문의글 ID' },
              title: { type: 'string', description: '원본 제목' },
              replyContent: { type: 'string', description: '생성된 답변 내용' },
              confidence: { type: 'number', description: '답변 신뢰도 (0-1)' },
              usedKnowledge: {
                type: 'array',
                description: '참조한 지식 문서 ID 목록',
                items: { type: 'string' },
              },
            },
          },
        },
        processedCount: {
          type: 'number',
          description: '처리된 문의글 수',
        },
      },
      required: ['replies', 'processedCount'],
    },

    // 연결된 도구 (라이브러리 참조)
    linkedToolIds: [],

    tools: [], // deprecated

    knowledge: {
      enabled: true,
      filters: [
        {
          field: 'tag',
          operator: 'in',
          value: ['faq', 'service-desk', 'customer-support'],
        },
      ],
      maxChunks: 5,
      includeInPrompt: true,
      promptTemplate: `
[관련 지식 베이스]
{{knowledge}}
---`,
    },

    systemPrompt: `당신은 친절하고 전문적인 고객 서비스 담당자입니다.
고객의 문의에 대해 정확하고 도움이 되는 답변을 작성합니다.

답변 작성 규칙:
1. 항상 공손하고 친절한 톤을 유지하세요
2. 가능한 구체적인 해결책을 제시하세요
3. 지식 베이스의 정보를 적극 활용하세요
4. 확실하지 않은 정보는 추측하지 마세요
5. 필요시 추가 문의를 안내하세요`,

    userPromptTemplate: `{{knowledge}}

문의글 목록:
{{#each input.tickets}}
---
[문의 {{@index}}]
ID: {{this.id}}
제목: {{this.title}}
카테고리: {{this.category}}
내용: {{this.content}}
{{/each}}

위 각 문의글에 대해 적절한 답변을 생성하세요.
JSON 형식으로 outputSchema에 맞게 반환하세요.`,

    llmConfig: {
      model: 'gpt-4o',
      temperature: 0.7,
      maxTokens: 4000,
      responseFormat: 'json',
    },

    createdAt: '2024-01-11T09:00:00Z',
    updatedAt: '2024-01-16T10:00:00Z',
  },

  // 노드 3: 댓글 등록
  {
    id: 'node-post-reply',
    name: '댓글 등록',
    description: '생성된 답변을 서비스데스크에 댓글로 등록합니다',
    icon: '📤',
    color: 'bg-green-600',
    tags: ['service-desk', 'api', 'post'],

    inputSchema: {
      type: 'object',
      description: '등록할 답변 목록',
      properties: {
        baseUrl: {
          type: 'string',
          description: 'API 기본 URL',
        },
        replies: {
          type: 'array',
          description: '등록할 답변 배열',
          items: {
            type: 'object',
            properties: {
              ticketId: { type: 'string' },
              replyContent: { type: 'string' },
            },
          },
        },
      },
      required: ['baseUrl', 'replies'],
    },

    outputSchema: {
      type: 'object',
      description: '등록 결과',
      properties: {
        results: {
          type: 'array',
          description: '등록 결과 배열',
          items: {
            type: 'object',
            properties: {
              ticketId: { type: 'string' },
              success: { type: 'boolean' },
              commentId: { type: 'string' },
              error: { type: 'string' },
            },
          },
        },
        successCount: { type: 'number' },
        failCount: { type: 'number' },
      },
      required: ['results', 'successCount', 'failCount'],
    },

    // 연결된 도구 (라이브러리 참조)
    linkedToolIds: ['tool-def-sd-comment'],

    tools: [], // deprecated

    knowledge: {
      enabled: false,
      filters: [],
      maxChunks: 0,
      includeInPrompt: false,
    },

    systemPrompt: 'API 호출 결과를 정리하여 성공/실패 통계와 함께 JSON 형식으로 반환하세요.',
    userPromptTemplate: `등록 요청 목록:
{{input.replies}}

API 호출 결과:
{{toolResults}}

위 결과를 outputSchema 형식에 맞게 정리하세요.`,

    llmConfig: {
      model: 'gpt-4o-mini',
      temperature: 0.1,
      maxTokens: 1000,
      responseFormat: 'json',
    },

    createdAt: '2024-01-12T09:00:00Z',
    updatedAt: '2024-01-17T11:00:00Z',
  },

  // 노드 4: 데이터 변환 (범용)
  {
    id: 'node-transform-data',
    name: '데이터 변환',
    description: '입력 데이터를 지정된 포맷으로 변환합니다',
    icon: '🔄',
    color: 'bg-yellow-600',
    tags: ['utility', 'transform'],

    inputSchema: {
      type: 'object',
      description: '변환할 데이터',
      properties: {
        data: {
          type: 'object',
          description: '원본 데이터',
        },
        transformRule: {
          type: 'string',
          description: '변환 규칙 (자연어 또는 JSONPath)',
        },
      },
      required: ['data'],
    },

    outputSchema: {
      type: 'object',
      description: '변환된 데이터',
      properties: {
        result: {
          type: 'object',
          description: '변환 결과',
        },
      },
      required: ['result'],
    },

    // 연결된 도구 (라이브러리 참조)
    linkedToolIds: [],

    tools: [], // deprecated

    knowledge: {
      enabled: false,
      filters: [],
      maxChunks: 0,
      includeInPrompt: false,
    },

    systemPrompt: '데이터 변환 전문가입니다. 입력 데이터를 요청된 형식으로 정확하게 변환합니다.',
    userPromptTemplate: `입력 데이터:
{{input.data}}

변환 규칙:
{{input.transformRule}}

위 데이터를 변환하여 JSON으로 반환하세요.`,

    llmConfig: {
      model: 'gpt-4o-mini',
      temperature: 0.1,
      maxTokens: 2000,
      responseFormat: 'json',
    },

    createdAt: '2024-01-13T09:00:00Z',
    updatedAt: '2024-01-13T09:00:00Z',
  },

  // 노드 5: 이메일 분류
  {
    id: 'node-classify-email',
    name: '이메일 분류',
    description: '이메일 내용을 분석하여 카테고리를 분류합니다',
    icon: '📧',
    color: 'bg-pink-600',
    tags: ['email', 'classification', 'ai'],

    inputSchema: {
      type: 'object',
      description: '분류할 이메일',
      properties: {
        emails: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              subject: { type: 'string' },
              body: { type: 'string' },
              sender: { type: 'string' },
            },
          },
        },
        categories: {
          type: 'array',
          description: '분류 카테고리 목록',
          items: { type: 'string' },
        },
      },
      required: ['emails', 'categories'],
    },

    outputSchema: {
      type: 'object',
      properties: {
        classifications: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              emailId: { type: 'string' },
              category: { type: 'string' },
              confidence: { type: 'number' },
              reason: { type: 'string' },
            },
          },
        },
      },
      required: ['classifications'],
    },

    // 연결된 도구 (라이브러리 참조)
    linkedToolIds: [],

    tools: [], // deprecated

    knowledge: {
      enabled: false,
      filters: [],
      maxChunks: 0,
      includeInPrompt: false,
    },

    systemPrompt: '이메일 분류 전문가입니다. 이메일의 제목과 내용을 분석하여 가장 적합한 카테고리로 분류합니다.',
    userPromptTemplate: `분류 카테고리: {{input.categories}}

이메일 목록:
{{#each input.emails}}
---
ID: {{this.id}}
제목: {{this.subject}}
발신자: {{this.sender}}
내용: {{this.body}}
{{/each}}

각 이메일을 분석하여 적절한 카테고리로 분류하세요.`,

    llmConfig: {
      model: 'gpt-4o-mini',
      temperature: 0.3,
      maxTokens: 1500,
      responseFormat: 'json',
    },

    createdAt: '2024-01-14T09:00:00Z',
    updatedAt: '2024-01-14T09:00:00Z',
  },
];

// ============================================
// Workflows (AI 노드 기반)
// ============================================

export const mockWorkflows: Workflow[] = [
  {
    id: 'wf-service-desk-auto-reply',
    name: '서비스데스크 자동 답변',
    description: 'A서비스의 서비스데스크에 미응답한 문의글에 대해 자동으로 답변 댓글을 달아줍니다',

    nodes: [
      {
        id: 'inst-1',
        nodeId: 'node-fetch-tickets',
        name: '미응답 문의글 조회',
        position: { x: 100, y: 200 },
        inputMapping: {
          baseUrl: '{{variables.serviceDeskUrl}}',
          status: 'unanswered',
          limit: '20',
        },
      },
      {
        id: 'inst-2',
        nodeId: 'node-generate-reply',
        name: 'AI 답변 생성',
        position: { x: 400, y: 200 },
        inputMapping: {
          tickets: '{{prev.tickets}}',
        },
        configOverrides: {
          llmConfig: {
            temperature: 0.5,
          },
        },
      },
      {
        id: 'inst-3',
        nodeId: 'node-post-reply',
        name: '댓글 등록',
        position: { x: 700, y: 200 },
        inputMapping: {
          baseUrl: '{{variables.serviceDeskUrl}}',
          replies: '{{prev.replies}}',
        },
      },
    ],

    connections: [
      { id: 'conn-1', sourceNodeId: 'inst-1', targetNodeId: 'inst-2' },
      { id: 'conn-2', sourceNodeId: 'inst-2', targetNodeId: 'inst-3' },
    ],

    variables: {
      serviceDeskUrl: 'https://api.servicedesk.example.com',
    },

    trigger: {
      type: 'schedule',
      config: {
        cron: '0 */30 * * * *',  // 30분마다
        timezone: 'Asia/Seoul',
      },
    },

    tags: ['service-desk', 'automation', 'customer-support'],
    createdAt: '2024-01-15T09:00:00Z',
    updatedAt: '2024-01-18T14:00:00Z',
  },
  {
    id: 'wf-email-categorizer',
    name: '이메일 자동 분류',
    description: '수신된 이메일을 카테고리별로 자동 분류합니다',

    nodes: [
      {
        id: 'inst-email-1',
        nodeId: 'node-classify-email',
        name: '이메일 분류',
        position: { x: 200, y: 200 },
        inputMapping: {
          categories: '["업무", "개인", "스팸", "프로모션", "기타"]',
        },
      },
    ],

    connections: [],

    variables: {},

    trigger: {
      type: 'webhook',
      config: {
        path: '/webhook/new-email',
        method: 'POST',
      },
    },

    tags: ['email', 'automation'],
    createdAt: '2024-01-16T09:00:00Z',
    updatedAt: '2024-01-16T09:00:00Z',
  },
];

// Helper: 노드 ID로 AINode 찾기
export function getAINodeById(nodeId: string): AINode | undefined {
  return mockAINodes.find(node => node.id === nodeId);
}

// Helper: 워크플로우 ID로 Workflow 찾기
export function getWorkflowById(workflowId: string): Workflow | undefined {
  return mockWorkflows.find(wf => wf.id === workflowId);
}
