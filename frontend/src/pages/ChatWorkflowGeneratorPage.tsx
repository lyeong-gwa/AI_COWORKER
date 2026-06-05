/**
 * ChatWorkflowGeneratorPage
 *   - /workflows/new/chat  → 신규 생성 모드
 *   - /workflows/:id/edit  → 편집 모드 (editId 있을 때)
 *
 * 구성:
 * - 좌측: 채팅 패널 (user/assistant 버블, 입력창)
 * - 우측 상단: 드래프트 미리보기 (WorkflowViewerCanvas)
 * - 우측 하단: 검증 리포트 패널 + 수정 제안 패널
 * - 헤더 액션 바: 저장 / 처음부터 (편집 모드 시 텍스트 변경)
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import {
  workflowApi,
  type GenerateResult,
  type ValidationReport,
  type WorkflowSuggestion,
  type WorkflowChatTurn,
} from '../services/api';
import { WorkflowViewerCanvas } from '../components/workflow/WorkflowViewerCanvas';
import { StyledMarkdown } from '../components/common/StyledMarkdown';
import { useToast } from '../components/common/Toast';
import type { Workflow } from '../types';

// ─── 로컬 타입 ───────────────────────────────────────────────────────────────

interface LocalMessage {
  role: 'user' | 'assistant' | 'divider';
  content: string;
  timestamp: string;
  /** 이전 세션에서 복원된 메시지 (시각적으로 흐리게 표시) */
  isHistory?: boolean;
}

// ─── draft → Workflow 변환 (미리보기용) ──────────────────────────────────────

function draftToWorkflow(draft: GenerateResult['draft']): Workflow {
  return {
    id: '__preview__',
    name: draft.name,
    description: draft.description,
    tags: draft.tags,
    nodes: draft.nodes.map((n, idx) => ({
      id: n.id,
      nodeId: n.nodeId,
      definitionType: n.definitionType,
      name: n.name,
      orderIndex: idx,
      config: n.config ?? {},
      inputMapping: n.inputMapping ?? {},
    })),
    connections: draft.connections.map((c) => ({
      id: c.id,
      sourceNodeId: c.sourceNodeId,
      targetNodeId: c.targetNodeId,
      sourceHandle: c.sourceHandle,
      targetHandle: c.targetHandle,
    })),
    variables: {},
    trigger: { type: 'manual', config: {} },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

// ─── Workflow → draft 역변환 (편집 모드 로드용) ──────────────────────────────

function workflowToDraft(wf: Workflow): GenerateResult['draft'] {
  return {
    name: wf.name,
    description: wf.description,
    tags: wf.tags ?? [],
    nodes: wf.nodes.map((n) => ({
      id: n.id,
      nodeId: n.nodeId,
      definitionType: n.definitionType ?? '',
      name: n.name,
      config: n.config ?? {},
      inputMapping: n.inputMapping ?? {},
      ...(n.aiNodeId ? { aiNodeId: n.aiNodeId } : {}),
    })),
    connections: wf.connections.map((c) => ({
      id: c.id,
      sourceNodeId: c.sourceNodeId,
      targetNodeId: c.targetNodeId,
      sourceHandle: c.sourceHandle,
      targetHandle: c.targetHandle,
    })),
  };
}

// ─── 검증 리포트 패널 ─────────────────────────────────────────────────────────

function ValidationPanel({ validation, attempts }: { validation: ValidationReport | null; attempts: number }) {
  if (!validation) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-xs font-mono">
        생성 후 검증 결과가 여기에 표시됩니다
      </div>
    );
  }

  return (
    <div className="p-4 space-y-3 overflow-auto h-full">
      {/* 상태 배지 */}
      <div className="flex items-center justify-between">
        {validation.valid ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-900/40 border border-emerald-700/60 text-emerald-300 text-xs font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
            검증 통과
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-900/30 border border-red-700/60 text-red-300 text-xs font-semibold">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
            오류 {validation.errorCount}건 · 경고 {validation.warningCount}건
          </span>
        )}
        {attempts > 1 && (
          <span className="text-[10px] font-mono text-slate-500">
            자동 교정 {attempts}회
          </span>
        )}
      </div>

      {/* 오류 목록 */}
      {validation.errors.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-mono uppercase tracking-widest text-red-400/80">
            오류
          </div>
          {validation.errors.map((issue, i) => (
            <div
              key={i}
              className="rounded-md bg-red-950/40 border border-red-800/50 px-3 py-2 text-xs text-red-200"
            >
              <span className="font-mono text-red-400 mr-2">[{issue.code}]</span>
              {issue.nodeName && (
                <span className="text-red-300 mr-1">{issue.nodeName}:</span>
              )}
              {issue.message}
            </div>
          ))}
        </div>
      )}

      {/* 경고 목록 */}
      {validation.warnings.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-[10px] font-mono uppercase tracking-widest text-yellow-400/80">
            경고
          </div>
          {validation.warnings.map((issue, i) => (
            <div
              key={i}
              className="rounded-md bg-yellow-950/40 border border-yellow-800/50 px-3 py-2 text-xs text-yellow-200"
            >
              <span className="font-mono text-yellow-400 mr-2">[{issue.code}]</span>
              {issue.nodeName && (
                <span className="text-yellow-300 mr-1">{issue.nodeName}:</span>
              )}
              {issue.message}
            </div>
          ))}
        </div>
      )}

      {validation.valid && validation.warnings.length === 0 && (
        <div className="text-xs text-slate-400">오류 및 경고가 없습니다.</div>
      )}
    </div>
  );
}

// ─── 수정 제안 패널 ───────────────────────────────────────────────────────────

interface SuggestionPanelProps {
  suggestions: WorkflowSuggestion[];
  onApply: (suggestion: string) => void;
}

function SuggestionPanel({ suggestions, onApply }: SuggestionPanelProps) {
  if (suggestions.length === 0) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 text-xs text-emerald-400/80 font-mono">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
        개선 제안 없음 ✓
      </div>
    );
  }

  return (
    <div className="overflow-auto max-h-full p-3 space-y-2">
      {suggestions.map((s, i) => {
        const isWarning = s.severity === 'warning';
        return (
          <div
            key={i}
            className={`rounded-md border px-3 py-2 text-xs space-y-1.5 ${
              isWarning
                ? 'bg-amber-950/30 border-amber-800/50'
                : 'bg-slate-800/60 border-slate-700/50'
            }`}
          >
            <div className="flex items-start gap-1.5">
              <span
                className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  isWarning ? 'bg-amber-400' : 'bg-slate-400'
                }`}
              />
              <div className="flex-1 min-w-0">
                {s.nodeName && (
                  <span
                    className={`font-mono mr-1 ${
                      isWarning ? 'text-amber-300' : 'text-slate-400'
                    }`}
                  >
                    {s.nodeName}:
                  </span>
                )}
                <span className={isWarning ? 'text-amber-200' : 'text-slate-300'}>
                  {s.message}
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onApply(s.suggestion)}
              className={`inline-flex items-center gap-1 text-[11px] font-mono px-2 py-0.5 rounded transition-colors ${
                isWarning
                  ? 'text-amber-300 hover:text-amber-100 hover:bg-amber-900/40 border border-amber-700/40'
                  : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700/40 border border-slate-600/40'
              }`}
            >
              ✎ 이 내용으로 수정 요청
            </button>
          </div>
        );
      })}
    </div>
  );
}

// ─── 채팅 버블 ────────────────────────────────────────────────────────────────

function UserBubble({ content, isHistory }: { content: string; isHistory?: boolean }) {
  return (
    <div className={`flex justify-end ${isHistory ? 'opacity-60' : ''}`}>
      <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-sky-600/30 border border-sky-600/40 px-4 py-2.5 text-sm text-slate-100 leading-relaxed">
        {isHistory && (
          <span className="inline-block mr-1.5 text-[9px] font-mono text-sky-400/70 bg-sky-900/30 border border-sky-800/40 rounded px-1 py-0.5 align-middle">
            이전
          </span>
        )}
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({ content, isHistory }: { content: string; isHistory?: boolean }) {
  return (
    <div className={`flex justify-start ${isHistory ? 'opacity-60' : ''}`}>
      <div className="max-w-[90%] rounded-2xl rounded-tl-sm bg-slate-800/70 border border-slate-700/60 px-4 py-2.5 text-sm">
        {isHistory && (
          <span className="inline-block mr-1.5 mb-1 text-[9px] font-mono text-slate-400/70 bg-slate-700/30 border border-slate-600/40 rounded px-1 py-0.5 align-middle">
            이전
          </span>
        )}
        <StyledMarkdown variant="chat">{content}</StyledMarkdown>
      </div>
    </div>
  );
}

function ChatDivider({ content }: { content: string }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <div className="flex-1 h-px bg-slate-700/50" />
      <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">{content}</span>
      <div className="flex-1 h-px bg-slate-700/50" />
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="rounded-2xl rounded-tl-sm bg-slate-800/70 border border-slate-700/60 px-4 py-3 flex gap-1 items-center">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:300ms]" />
      </div>
    </div>
  );
}

// ─── 메인 페이지 ──────────────────────────────────────────────────────────────

export default function ChatWorkflowGeneratorPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  // 편집 모드 감지: /workflows/:id/edit 경로에서 id 추출
  const { id: editId } = useParams<{ id: string }>();
  const isEditMode = !!editId;

  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingWorkflow, setIsLoadingWorkflow] = useState(false);

  const [currentDraft, setCurrentDraft] = useState<GenerateResult['draft'] | null>(null);
  const [currentValidation, setCurrentValidation] = useState<ValidationReport | null>(null);
  const [currentAttempts, setCurrentAttempts] = useState(0);
  const [lastTraceId, setLastTraceId] = useState<string | null>(null);
  /** 이 세션에서 생성된(+기존 복원된) trace ID 목록 — 저장 시 workfl에 연결 */
  const [sessionTraceIds, setSessionTraceIds] = useState<string[]>([]);

  // 수정 제안 상태
  const [suggestions, setSuggestions] = useState<WorkflowSuggestion[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 메시지 추가 시 스크롤 하단 이동
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  // 편집 모드: 기존 워크플로우 로드 (1회)
  useEffect(() => {
    if (!isEditMode || !editId) return;

    let cancelled = false;
    async function loadWorkflow() {
      setIsLoadingWorkflow(true);
      try {
        // 워크플로우 기본 정보 + 채팅 히스토리 병렬 로드
        const [wf, chatHistory] = await Promise.all([
          workflowApi.get(editId!),
          workflowApi.getChatHistory(editId!).catch((e: unknown) => {
            console.warn('[ChatWorkflowGeneratorPage] getChatHistory 실패 (무시):', e);
            return [] as WorkflowChatTurn[];
          }),
        ]);
        if (cancelled) return;

        const draft = workflowToDraft(wf);
        setCurrentDraft(draft);

        if (chatHistory.length > 0) {
          // 이전 대화 복원: 각 turn → user 버블 + assistant 버블
          const restoredMessages: LocalMessage[] = [
            { role: 'divider', content: '── 이전 대화 ──', timestamp: chatHistory[0].createdAt, isHistory: true },
          ];
          for (const turn of chatHistory) {
            restoredMessages.push({
              role: 'user',
              content: turn.userMessage,
              timestamp: turn.createdAt,
              isHistory: true,
            });
            restoredMessages.push({
              role: 'assistant',
              content: turn.assistantMessage,
              timestamp: turn.createdAt,
              isHistory: true,
            });
          }
          restoredMessages.push({
            role: 'divider',
            content: '── 이어서 편집 ──',
            timestamp: new Date().toISOString(),
            isHistory: false,
          });

          setMessages(restoredMessages);

          // 기존 traceId 목록으로 sessionTraceIds 초기화 (새 편집 시 append, dedup)
          const restoredIds = chatHistory.map((t) => t.traceId);
          setSessionTraceIds(restoredIds);
        } else {
          // 이전 히스토리 없음: 기존 단일 시드 메시지
          setMessages([
            {
              role: 'assistant',
              content: `현재 워크플로우 **'${wf.name}'**을 불러왔습니다. 수정할 내용을 말씀하시거나, 아래 수정 제안을 적용하세요.`,
              timestamp: new Date().toISOString(),
            },
          ]);
        }
      } catch (e) {
        if (cancelled) return;
        toast.error(`워크플로우 로드 실패: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        if (!cancelled) setIsLoadingWorkflow(false);
      }
    }

    loadWorkflow();
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editId, isEditMode]);

  // draft 변경 시 advise 호출 (조용히 실패)
  useEffect(() => {
    if (!currentDraft) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    workflowApi
      .advise({
        nodes: currentDraft.nodes as any[],
        connections: currentDraft.connections as any[],
      })
      .then((result) => {
        if (cancelled) return;
        setSuggestions(result.suggestions ?? []);
      })
      .catch(() => {
        // 조용히 무시
      });
    return () => { cancelled = true; };
  }, [currentDraft]);

  // textarea 자동 높이 조절
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isGenerating) return;

    const userMsg: LocalMessage = {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    setIsGenerating(true);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      let mode: 'create' | 'edit';
      let baseDraft: GenerateResult['draft'] | null;

      if (isEditMode) {
        // 편집 모드: 항상 edit + baseDraft 전달
        mode = 'edit';
        baseDraft = currentDraft;
      } else {
        // 신규 모드: 첫 메시지는 create, 이후 edit
        const isFirst = messages.length === 0;
        mode = isFirst ? 'create' : 'edit';
        baseDraft = isFirst ? null : currentDraft;
      }

      const result = await workflowApi.generate({
        description: text,
        mode,
        history,
        baseDraft,
      });

      const assistantMsg: LocalMessage = {
        role: 'assistant',
        content: result.assistantMessage,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setCurrentDraft(result.draft);
      setCurrentValidation(result.validation);
      setCurrentAttempts(result.attempts);
      if (result.traceId) {
        setLastTraceId(result.traceId);
        // sessionTraceIds에 dedup 추가
        setSessionTraceIds((prev) =>
          prev.includes(result.traceId!) ? prev : [...prev, result.traceId!]
        );
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      toast.error(`생성 실패: ${errMsg}`);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `워크플로우 생성 중 오류가 발생했습니다.\n\n**오류:** ${errMsg}\n\n다시 시도하거나 설명을 더 구체적으로 작성해 보세요.`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setIsGenerating(false);
    }
  }, [input, isGenerating, messages, toast, isEditMode, currentDraft]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleReset = useCallback(() => {
    setMessages([]);
    setInput('');
    setCurrentDraft(null);
    setCurrentValidation(null);
    setCurrentAttempts(0);
    setLastTraceId(null);
    setSessionTraceIds([]);
    setSuggestions([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, []);

  // 제안 → 입력창에 설정
  const handleApplySuggestion = useCallback((suggestion: string) => {
    setInput(suggestion);
    textareaRef.current?.focus();
  }, []);

  const handleSave = useCallback(async () => {
    if (!currentDraft || !currentValidation?.valid) return;
    setIsSaving(true);
    try {
      const nodePayload = currentDraft.nodes.map((n, idx) => ({
        id: n.id,
        nodeId: n.nodeId,
        definitionType: n.definitionType,
        name: n.name,
        orderIndex: idx,
        config: n.config as Record<string, unknown>,
        inputMapping: n.inputMapping ?? {},
        ...((n as any).aiNodeId ? { aiNodeId: (n as any).aiNodeId } : {}),
      }));
      const connPayload = currentDraft.connections.map((c) => ({
        id: c.id,
        sourceNodeId: c.sourceNodeId,
        targetNodeId: c.targetNodeId,
        sourceHandle: c.sourceHandle,
        targetHandle: c.targetHandle,
      }));

      if (isEditMode && editId) {
        // 편집 모드: update
        await workflowApi.update(editId, {
          name: currentDraft.name,
          description: currentDraft.description,
          tags: currentDraft.tags,
          nodes: nodePayload,
          connections: connPayload,
          ...(sessionTraceIds.length > 0 ? { generationTraceIds: sessionTraceIds } : {}),
        });
        toast.success(`"${currentDraft.name}" 변경 사항이 저장되었습니다.`);
        navigate(`/workflows/${editId}`);
      } else {
        // 신규 모드: create + activate
        const created = await workflowApi.create({
          name: currentDraft.name,
          description: currentDraft.description,
          tags: currentDraft.tags,
          nodes: nodePayload,
          connections: connPayload,
          ...(sessionTraceIds.length > 0 ? { generationTraceIds: sessionTraceIds } : {}),
        });

        try {
          await workflowApi.update(created.id, { status: 'active' });
          toast.success(`"${created.name}" 저장 및 활성화 완료`);
        } catch {
          toast.warning(`"${created.name}" 생성됨(활성화 실패: 상세에서 활성화 필요)`);
        }

        navigate(`/workflows/${created.id}`);
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      toast.error(`저장 실패: ${errMsg}`);
    } finally {
      setIsSaving(false);
    }
  }, [currentDraft, currentValidation, navigate, toast, isEditMode, editId, sessionTraceIds]);

  const previewWorkflow: Workflow | null = currentDraft ? draftToWorkflow(currentDraft) : null;
  const canSave = !!currentDraft && currentValidation?.valid === true && !isSaving;

  return (
    <div className="flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* 헤더 */}
      <header className="flex-shrink-0 px-6 py-4 border-b border-slate-800 flex items-center gap-4">
        <Link
          to={isEditMode && editId ? `/workflows/${editId}` : '/workflows'}
          className="text-slate-500 hover:text-slate-300 transition-colors text-sm font-mono"
        >
          ← {isEditMode ? '상세로' : '목록'}
        </Link>
        <div>
          <div className="text-[10px] font-mono tracking-[0.25em] uppercase text-slate-500">
            {isEditMode ? '채팅으로 편집' : '채팅으로 생성'}
          </div>
          <h1 className="text-base font-semibold text-slate-100 leading-tight">
            {isEditMode ? '업무자동화 편집' : '업무자동화 생성'}
          </h1>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {!isEditMode && (
            <button
              type="button"
              onClick={handleReset}
              className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300 hover:bg-slate-700 hover:text-slate-100 transition-colors"
            >
              처음부터
            </button>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              canSave
                ? 'bg-sky-600 hover:bg-sky-500 text-white border border-sky-500'
                : 'bg-slate-800 border border-slate-700 text-slate-500 cursor-not-allowed'
            }`}
          >
            {isSaving ? '저장 중...' : isEditMode ? '변경 저장' : '확정 저장'}
          </button>
        </div>
      </header>

      {/* 워크플로우 로딩 중 오버레이 */}
      {isLoadingWorkflow && (
        <div className="flex-1 flex items-center justify-center bg-slate-950">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-slate-700 border-t-sky-500 rounded-full animate-spin" />
            <span className="text-xs text-slate-500 font-mono">워크플로우 불러오는 중...</span>
          </div>
        </div>
      )}

      {/* 본체: 2열 */}
      {!isLoadingWorkflow && (
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* ── 좌측: 채팅 패널 ────────────────────────────────────── */}
          <div className="flex flex-col w-[400px] min-w-[320px] border-r border-slate-800 flex-shrink-0">
            {/* 메시지 목록 */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
              {messages.length === 0 && !isEditMode && (
                <div className="flex flex-col items-center justify-center h-full text-center py-8">
                  <div className="w-12 h-12 rounded-xl bg-sky-900/30 border border-sky-700/40 flex items-center justify-center mb-4 text-sky-400 text-xl">
                    ✦
                  </div>
                  <p className="text-sm font-semibold text-slate-200 mb-1">
                    업무 설명을 입력하세요
                  </p>
                  <p className="text-xs text-slate-500 leading-relaxed max-w-[260px]">
                    어떤 업무를 자동화할지 자연어로 설명하면 워크플로우 초안을 생성합니다.
                    추가 요청으로 계속 수정할 수 있습니다.
                  </p>
                  <div className="mt-4 space-y-1.5 text-left w-full max-w-[280px]">
                    {[
                      '매일 Jira 티켓을 조회해서 요약 보고서 만들기',
                      '신규 문의를 분류해서 담당자에게 알리기',
                      '코드 변경사항을 분석해서 위험 알림 보내기',
                    ].map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => {
                          setInput(ex);
                          textareaRef.current?.focus();
                        }}
                        className="w-full text-left text-xs text-slate-400 hover:text-sky-300 px-3 py-2 rounded-lg border border-slate-800 hover:border-sky-800/50 hover:bg-sky-950/20 transition-colors"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((msg, i) =>
                msg.role === 'divider' ? (
                  <ChatDivider key={i} content={msg.content} />
                ) : msg.role === 'user' ? (
                  <UserBubble key={i} content={msg.content} isHistory={msg.isHistory} />
                ) : (
                  <AssistantBubble key={i} content={msg.content} isHistory={msg.isHistory} />
                )
              )}
              {isGenerating && <TypingIndicator />}
              <div ref={messagesEndRef} />
            </div>

            {/* 입력창 */}
            <div className="flex-shrink-0 border-t border-slate-800 p-3">
              <div className="flex gap-2 items-end">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder={
                    isEditMode
                      ? '수정할 내용을 입력하세요... (Shift+Enter 줄바꿈)'
                      : messages.length === 0
                        ? '자동화할 업무를 설명하세요...'
                        : '수정 요청을 입력하세요... (Shift+Enter 줄바꿈)'
                  }
                  disabled={isGenerating}
                  rows={1}
                  className="flex-1 resize-none rounded-xl bg-slate-800/80 border border-slate-700/80 text-sm text-slate-100 placeholder-slate-500 px-3 py-2.5 focus:outline-none focus:border-sky-600/60 focus:bg-slate-800 transition-colors disabled:opacity-50 leading-relaxed"
                  style={{ minHeight: '42px', maxHeight: '160px' }}
                />
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!input.trim() || isGenerating}
                  className={`flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                    input.trim() && !isGenerating
                      ? 'bg-sky-600 hover:bg-sky-500 text-white'
                      : 'bg-slate-800 text-slate-600 cursor-not-allowed'
                  }`}
                  aria-label="전송"
                >
                  {isGenerating ? (
                    <span className="w-4 h-4 border-2 border-slate-500 border-t-sky-400 rounded-full animate-spin" />
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M2 8h12M9 3l5 5-5 5" />
                    </svg>
                  )}
                </button>
              </div>
              {isGenerating && (
                <p className="text-[10px] text-slate-500 font-mono mt-1.5 text-center">
                  워크플로우 {isEditMode ? '수정' : '생성'} 중... (수십 초 소요될 수 있습니다)
                </p>
              )}
            </div>
          </div>

          {/* ── 우측: 미리보기 + 검증 + 수정 제안 ─────────────────── */}
          <div className="flex flex-col flex-1 min-w-0">
            {/* 드래프트 미리보기 */}
            <div className="flex-1 min-h-0 relative border-b border-slate-800">
              {previewWorkflow ? (
                <>
                  {/* 드래프트 이름 배지 */}
                  <div className="absolute top-3 left-3 z-10 flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/80 border border-slate-700 text-slate-300 text-xs backdrop-blur-sm">
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isEditMode ? 'bg-amber-400' : 'bg-sky-400'}`} />
                      {isEditMode ? '편집 중' : '초안'}: {previewWorkflow.name}
                    </span>
                    {currentDraft && (
                      <span className="text-[10px] font-mono text-slate-500 bg-slate-900/80 px-2 py-1 rounded-full border border-slate-700 backdrop-blur-sm">
                        노드 {currentDraft.nodes.length}개 · 연결 {currentDraft.connections.length}개
                      </span>
                    )}
                  </div>
                  <ReactFlowProvider>
                    <WorkflowViewerCanvas workflow={previewWorkflow} />
                  </ReactFlowProvider>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-center p-6">
                  <div className="w-16 h-16 rounded-2xl bg-slate-900/60 border border-slate-800 flex items-center justify-center mb-3 text-slate-600 text-2xl">
                    ◻
                  </div>
                  <p className="text-sm text-slate-500">
                    {isEditMode
                      ? '워크플로우를 불러오는 중입니다...'
                      : '생성된 워크플로우 초안이 여기에 미리 보입니다'}
                  </p>
                </div>
              )}
            </div>

            {/* 검증 리포트 패널 */}
            <div className="flex-shrink-0 h-[180px] bg-slate-900/30 border-b border-slate-800">
              <div className="flex items-center px-4 py-2 border-b border-slate-800 gap-3">
                <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
                  검증 리포트
                </span>
                {lastTraceId && (
                  <Link
                    to={`/workflows/generation-history`}
                    state={{ traceId: lastTraceId }}
                    className="ml-auto text-[10px] font-mono text-sky-500 hover:text-sky-300 transition-colors"
                  >
                    이 생성 과정 로그 보기 →
                  </Link>
                )}
              </div>
              <div className="h-[calc(180px-36px)]">
                <ValidationPanel
                  validation={currentValidation}
                  attempts={currentAttempts}
                />
              </div>
            </div>

            {/* 수정 제안 패널 */}
            <div className="flex-shrink-0 h-[160px] bg-slate-900/20">
              <div className="flex items-center px-4 py-2 border-b border-slate-800">
                <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
                  수정 제안
                </span>
                {suggestions.length > 0 && (
                  <span className="ml-2 inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-900/60 border border-amber-700/60 text-[9px] font-mono text-amber-300">
                    {suggestions.length}
                  </span>
                )}
              </div>
              <div className="h-[calc(160px-36px)] overflow-auto">
                <SuggestionPanel
                  suggestions={suggestions}
                  onApply={handleApplySuggestion}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
