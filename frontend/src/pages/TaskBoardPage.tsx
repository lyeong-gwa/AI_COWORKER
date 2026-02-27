import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { mockTasks } from '../data/mockData';
import { taskApi, chatApi } from '../services/api';
import type { CreateTaskData } from '../services/api';
import { useToast } from '../components/common/Toast';
import { useChatAssistant } from '../hooks/useChatAssistant';
import { useChatContext } from '../contexts/ChatContext';
import type { TaskCard, TaskColumn, TaskStatus, TaskPriority } from '../types';
import { StyledMarkdown } from '../components/common/StyledMarkdown';

// ============================================
// Constants
// ============================================

const COLUMN_DEFINITIONS: { id: string; title: string; status: TaskStatus }[] = [
  { id: 'col-backlog', title: 'Backlog', status: 'backlog' },
  { id: 'col-todo', title: 'To Do', status: 'todo' },
  { id: 'col-in-progress', title: 'In Progress', status: 'in-progress' },
  { id: 'col-review', title: 'Review', status: 'review' },
  { id: 'col-done', title: 'Done', status: 'done' },
];

const priorityColors: Record<TaskPriority, string> = {
  low: 'bg-gray-500',
  medium: 'bg-blue-500',
  high: 'bg-orange-500',
  urgent: 'bg-red-500',
};

const priorityLabels: Record<TaskPriority, string> = {
  low: '낮음',
  medium: '보통',
  high: '높음',
  urgent: '긴급',
};

const statusColors: Record<TaskStatus, string> = {
  backlog: 'border-gray-500',
  todo: 'border-yellow-500',
  'in-progress': 'border-blue-500',
  review: 'border-purple-500',
  done: 'border-green-500',
};

// ============================================
// Helpers
// ============================================

function generateId(): string {
  return `task-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function buildColumns(tasks: TaskCard[]): TaskColumn[] {
  return COLUMN_DEFINITIONS.map((def) => ({
    ...def,
    cards: tasks.filter((t) => t.status === def.status),
  }));
}

// ============================================
// Loading Spinner
// ============================================

function Spinner() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="flex flex-col items-center gap-3">
        <div className="w-10 h-10 border-4 border-gray-600 border-t-blue-500 rounded-full animate-spin" />
        <span className="text-gray-400 text-sm">로딩 중...</span>
      </div>
    </div>
  );
}

// ============================================
// Task Creation / Edit Modal
// ============================================

interface TaskFormData {
  title: string;
  description: string;
  priority: TaskPriority;
  status: TaskStatus;
  tags: string;
  assigneeName: string;
  dueDate: string;
}

const emptyForm: TaskFormData = {
  title: '',
  description: '',
  priority: 'medium',
  status: 'todo',
  tags: '',
  assigneeName: '',
  dueDate: '',
};

function TaskCreateModal({
  defaultStatus,
  onClose,
  onSubmit,
}: {
  defaultStatus?: TaskStatus;
  onClose: () => void;
  onSubmit: (data: TaskFormData) => Promise<void>;
}) {
  const [form, setForm] = useState<TaskFormData>({
    ...emptyForm,
    status: defaultStatus || 'todo',
  });
  const [saving, setSaving] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    setSaving(true);
    try {
      await onSubmit(form);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">새 태스크 생성</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Title */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="block text-sm font-medium text-gray-400">
                제목 <span className="text-red-400">*</span>
              </label>
              <span className={`text-xs ${form.title.length > 180 ? 'text-red-400' : 'text-gray-500'}`}>
                {form.title.length}/200
              </span>
            </div>
            <input
              ref={titleRef}
              type="text"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              maxLength={200}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="태스크 제목을 입력하세요"
              required
            />
          </div>

          {/* Description */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="block text-sm font-medium text-gray-400">
                설명
              </label>
              {form.description.length > 1500 && (
                <span className={`text-xs ${form.description.length > 1800 ? 'text-red-400' : 'text-yellow-400'}`}>
                  {form.description.length}/2000
                </span>
              )}
            </div>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              maxLength={2000}
              rows={3}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              placeholder="태스크 설명을 입력하세요"
            />
          </div>

          {/* Priority + Status row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                우선순위
              </label>
              <select
                value={form.priority}
                onChange={(e) =>
                  setForm({ ...form, priority: e.target.value as TaskPriority })
                }
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="low">낮음</option>
                <option value="medium">보통</option>
                <option value="high">높음</option>
                <option value="urgent">긴급</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                상태
              </label>
              <select
                value={form.status}
                onChange={(e) =>
                  setForm({ ...form, status: e.target.value as TaskStatus })
                }
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="backlog">Backlog</option>
                <option value="todo">To Do</option>
                <option value="in-progress">In Progress</option>
                <option value="review">Review</option>
                <option value="done">Done</option>
              </select>
            </div>
          </div>

          {/* Tags */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              태그
            </label>
            <input
              type="text"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="쉼표로 구분 (예: frontend, bug, urgent)"
            />
          </div>

          {/* Assignee + Due Date row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                담당자
              </label>
              <input
                type="text"
                value={form.assigneeName}
                onChange={(e) =>
                  setForm({ ...form, assigneeName: e.target.value })
                }
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="이름"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                마감일
              </label>
              <input
                type="date"
                value={form.dueDate}
                onChange={(e) => setForm({ ...form, dueDate: e.target.value })}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={saving || !form.title.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {saving ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  생성 중...
                </>
              ) : '생성'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================
// Task Card Component (with drag)
// ============================================

function TaskCardItem({
  task,
  onClick,
  onDragStart,
}: {
  task: TaskCard;
  onClick: () => void;
  onDragStart: (e: React.DragEvent, taskId: string) => void;
}) {
  const completedTodos = task.todos.filter((t) => t.completed).length;
  const totalTodos = task.todos.length;

  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task.id)}
      onClick={onClick}
      className="bg-gray-700 rounded-lg p-3 cursor-grab hover:bg-gray-650 hover:ring-1 hover:ring-blue-500 transition-all active:cursor-grabbing"
    >
      {/* Tags */}
      {task.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {task.tags.slice(0, 3).map((tag) => (
            <span
              key={tag}
              className="px-2 py-0.5 text-xs rounded bg-gray-600 text-gray-300"
            >
              {tag}
            </span>
          ))}
          {task.tags.length > 3 && (
            <span className="px-2 py-0.5 text-xs rounded bg-gray-600 text-gray-400">
              +{task.tags.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Title */}
      <h4 className="font-medium text-white mb-2">{task.title}</h4>

      {/* Meta info */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          {/* Priority */}
          <span
            className={`w-2 h-2 rounded-full ${priorityColors[task.priority] || 'bg-gray-600'}`}
          />

          {/* Todo progress */}
          {totalTodos > 0 && (
            <span className="text-gray-400">
              {completedTodos}/{totalTodos}
            </span>
          )}

          {/* Comments */}
          {task.comments.length > 0 && (
            <span className="text-gray-400">{task.comments.length}</span>
          )}
        </div>

        {/* Assignee */}
        {task.assigneeName && (
          <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-xs text-white">
            {task.assigneeName[0]}
          </div>
        )}
      </div>

      {/* Due date */}
      {task.dueDate && (
        <div className="mt-2 text-xs text-gray-400">
          {new Date(task.dueDate).toLocaleDateString('ko-KR')}
        </div>
      )}
    </div>
  );
}

// ============================================
// Column Component (with drop target)
// ============================================

function Column({
  column,
  onCardClick,
  onAddCard,
  onDragStart,
  onDrop,
  dragOverColumn,
  onDragOver,
  onDragLeave,
}: {
  column: TaskColumn;
  onCardClick: (task: TaskCard) => void;
  onAddCard: (status: TaskStatus) => void;
  onDragStart: (e: React.DragEvent, taskId: string) => void;
  onDrop: (e: React.DragEvent, targetStatus: TaskStatus) => void;
  dragOverColumn: TaskStatus | null;
  onDragOver: (e: React.DragEvent, status: TaskStatus) => void;
  onDragLeave: () => void;
}) {
  const isDragOver = dragOverColumn === column.status;

  return (
    <div className="flex-shrink-0 w-72">
      {/* Column Header */}
      <div
        className={`bg-gray-800 rounded-t-lg p-3 border-t-2 ${statusColors[column.status]}`}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white">{column.title}</h3>
          <span className="bg-gray-700 text-gray-300 px-2 py-0.5 rounded text-sm">
            {column.cards.length}
          </span>
        </div>
      </div>

      {/* Cards (drop target) */}
      <div
        onDragOver={(e) => onDragOver(e, column.status)}
        onDragLeave={onDragLeave}
        onDrop={(e) => onDrop(e, column.status)}
        className={`bg-gray-800/50 rounded-b-lg p-2 space-y-2 min-h-[200px] transition-colors ${
          isDragOver ? 'ring-2 ring-blue-500 bg-blue-500/10' : ''
        }`}
      >
        {column.cards.length === 0 && (
          <div className="flex flex-col items-center py-8 text-center">
            <p className="text-gray-500 text-sm mb-2">카드가 없습니다</p>
            <p className="text-gray-600 text-xs">여기에 카드를 드래그하거나 아래 버튼으로 추가하세요</p>
          </div>
        )}

        {column.cards.map((card) => (
          <TaskCardItem
            key={card.id}
            task={card}
            onClick={() => onCardClick(card)}
            onDragStart={onDragStart}
          />
        ))}

        {/* Add card button */}
        <button
          onClick={() => onAddCard(column.status)}
          className="w-full p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors text-sm flex items-center justify-center gap-1"
        >
          + 카드 추가
        </button>
      </div>
    </div>
  );
}

// ============================================
// Task Detail Modal (with Edit / Delete / Comments / Todos)
// ============================================

function TaskDetailModal({
  task,
  onClose,
  onUpdate,
  onDelete,
  isOnline,
}: {
  task: TaskCard;
  onClose: () => void;
  onUpdate: (updated: TaskCard) => void;
  onDelete: (taskId: string) => void;
  isOnline: boolean;
}) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<
    'detail' | 'todos' | 'activity' | 'comments' | 'references'
  >('detail');
  const [isEditing, setIsEditing] = useState(false);
  const [expandedRefs, setExpandedRefs] = useState<Set<string>>(new Set());
  const [editForm, setEditForm] = useState({
    title: task.title,
    description: task.description,
    priority: task.priority,
    assigneeName: task.assigneeName || '',
    dueDate: task.dueDate || '',
    tags: task.tags.join(', '),
  });
  const [commentText, setCommentText] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [localTask, setLocalTask] = useState<TaskCard>(task);
  const [newTodoText, setNewTodoText] = useState('');
  const [editingTodoId, setEditingTodoId] = useState<string | null>(null);
  const [editingTodoText, setEditingTodoText] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const commentsEndRef = useRef<HTMLDivElement>(null);

  // Sync localTask when external task changes
  // Only reset tab/refs when a DIFFERENT task is opened (by id), not on same-task updates
  const prevTaskIdRef = useRef(task.id);
  useEffect(() => {
    setLocalTask(task);
    if (task.id !== prevTaskIdRef.current) {
      setActiveTab('detail');
      setExpandedRefs(new Set());
      setEditingTodoId(null);
      setEditingTodoText('');
      setNewTodoText('');
      prevTaskIdRef.current = task.id;
    }
  }, [task]);

  useEffect(() => {
    if (activeTab === 'comments') {
      commentsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [localTask.comments, activeTab, aiLoading]);

  const handleSaveEdit = async () => {
    setSaving(true);
    try {
    const updatedTask: TaskCard = {
      ...localTask,
      title: editForm.title,
      description: editForm.description,
      priority: editForm.priority,
      assigneeName: editForm.assigneeName || undefined,
      dueDate: editForm.dueDate ? `${editForm.dueDate}T00:00:00` : undefined,
      tags: editForm.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      updatedAt: new Date().toISOString(),
    };

    if (isOnline) {
      try {
        await taskApi.update(localTask.id, {
          title: updatedTask.title,
          description: updatedTask.description,
          priority: updatedTask.priority,
          assigneeName: updatedTask.assigneeName,
          dueDate: updatedTask.dueDate,
          tags: updatedTask.tags,
        });
        toast.success('태스크가 수정되었습니다');
      } catch (err) {
        const detail = err instanceof Error ? err.message : '';
        toast.warning(`API 저장 실패${detail ? `: ${detail}` : ''}. 로컬에만 반영됩니다`);
      }
    }

      setLocalTask(updatedTask);
      onUpdate(updatedTask);
      setIsEditing(false);
      setEditingTodoId(null);
      setEditingTodoText('');
      setNewTodoText('');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
    if (isOnline) {
      try {
        await taskApi.delete(localTask.id);
        toast.success('태스크가 삭제되었습니다');
      } catch (err) {
        const detail = err instanceof Error ? err.message : '';
        toast.warning(`API 삭제 실패${detail ? `: ${detail}` : ''}. 로컬에서만 삭제합니다`);
      }
    }
      onDelete(localTask.id);
      onClose();
    } finally {
      setDeleting(false);
    }
  };

  const handleToggleTodo = async (todoId: string) => {
    const updatedTodos = localTask.todos.map((t) =>
      t.id === todoId ? { ...t, completed: !t.completed } : t
    );
    const updatedTask = {
      ...localTask,
      todos: updatedTodos,
      updatedAt: new Date().toISOString(),
    };

    if (isOnline) {
      try {
        await taskApi.update(localTask.id, { todos: updatedTodos });
      } catch {
        // silent fail
      }
    }

    setLocalTask(updatedTask);
    onUpdate(updatedTask);
  };

  const handleAddTodo = async () => {
    if (!newTodoText.trim()) return;
    const newTodo = {
      id: `todo-${Date.now()}`,
      text: newTodoText.trim(),
      completed: false,
    };
    const updatedTodos = [...localTask.todos, newTodo];
    const updatedTask = { ...localTask, todos: updatedTodos, updatedAt: new Date().toISOString() };

    if (isOnline) {
      try {
        await taskApi.update(localTask.id, { todos: updatedTodos });
      } catch {
        // silent fail
      }
    }

    setLocalTask(updatedTask);
    onUpdate(updatedTask);
    setNewTodoText('');
  };

  const handleDeleteTodo = async (todoId: string) => {
    const updatedTodos = localTask.todos.filter((t) => t.id !== todoId);
    const updatedTask = { ...localTask, todos: updatedTodos, updatedAt: new Date().toISOString() };

    if (isOnline) {
      try {
        await taskApi.update(localTask.id, { todos: updatedTodos });
      } catch {
        // silent fail
      }
    }

    setLocalTask(updatedTask);
    onUpdate(updatedTask);
  };

  const handleSaveTodoEdit = async (todoId: string) => {
    if (!editingTodoText.trim()) return;
    const updatedTodos = localTask.todos.map((t) =>
      t.id === todoId ? { ...t, text: editingTodoText.trim() } : t
    );
    const updatedTask = { ...localTask, todos: updatedTodos, updatedAt: new Date().toISOString() };

    if (isOnline) {
      try {
        await taskApi.update(localTask.id, { todos: updatedTodos });
      } catch {
        // silent fail
      }
    }

    setLocalTask(updatedTask);
    onUpdate(updatedTask);
    setEditingTodoId(null);
    setEditingTodoText('');
  };

  const handleAddComment = async () => {
    if (!commentText.trim() || aiLoading) return;

    const userComment = {
      id: `comment-${Date.now()}`,
      authorId: 'user-1',
      authorName: '나',
      content: commentText.trim(),
      createdAt: new Date().toISOString(),
    };

    // Optimistic: add user comment immediately
    const withUserComment: TaskCard = {
      ...localTask,
      comments: [...localTask.comments, userComment],
      updatedAt: new Date().toISOString(),
    };
    setLocalTask(withUserComment);
    onUpdate(withUserComment);
    setCommentText('');

    // Save user comment to backend
    if (isOnline) {
      try {
        await taskApi.update(localTask.id, {
          comments: withUserComment.comments as any,
        });
      } catch {
        // silent fail for save
      }
    }

    // Call AI
    if (isOnline) {
      setAiLoading(true);
      try {
        const response = await chatApi.sendMessage({
          content: userComment.content,
          context: { type: 'task', id: localTask.id },
        });

        const aiComment = {
          id: `comment-${Date.now()}-ai`,
          authorId: 'ai-assistant',
          authorName: 'AI 어시스턴트',
          content: response.content,
          createdAt: new Date().toISOString(),
        };

        const withAiComment: TaskCard = {
          ...withUserComment,
          comments: [...withUserComment.comments, aiComment],
          updatedAt: new Date().toISOString(),
        };

        // Save AI comment
        try {
          await taskApi.update(localTask.id, {
            comments: withAiComment.comments as any,
          });
        } catch {
          // silent fail
        }

        setLocalTask(withAiComment);
        onUpdate(withAiComment);

        // If AI performed an action (e.g., updated TODOs), refresh task data from backend
        if (response.action?.success) {
          try {
            const refreshed = await taskApi.get(localTask.id);
            setLocalTask(refreshed);
            onUpdate(refreshed);
          } catch {
            // silent fail - the comment is already shown
          }
        }
      } catch {
        toast.warning('AI 응답을 가져오지 못했습니다');
      } finally {
        setAiLoading(false);
      }
    }
  };

  const handleCommentKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !aiLoading) {
      e.preventDefault();
      handleAddComment();
    }
  };

  const handleDeleteComment = async (commentId: string) => {
    if (!isOnline) return;
    try {
      await taskApi.deleteComment(localTask.id, commentId);
      const updated = { ...localTask, comments: localTask.comments.filter(c => c.id !== commentId) };
      setLocalTask(updated);
      onUpdate(updated);
      toast.success('댓글이 삭제되었습니다');
    } catch (err: any) {
      toast.error(err.message || '댓글 삭제 실패');
    }
  };

  const handleDeleteActivity = async (logId: string) => {
    if (!isOnline) return;
    try {
      await taskApi.deleteActivity(localTask.id, logId);
      const updated = { ...localTask, activityLog: localTask.activityLog.filter(a => a.id !== logId) };
      setLocalTask(updated);
      onUpdate(updated);
      toast.success('이력이 삭제되었습니다');
    } catch (err: any) {
      toast.error(err.message || '이력 삭제 실패');
    }
  };

  const handleDeleteReference = async (docId: string) => {
    if (!isOnline) return;
    try {
      await taskApi.deleteReference(localTask.id, docId);
      const updated = { ...localTask, references: localTask.references?.filter(r => r.docId !== docId) || [] };
      setLocalTask(updated);
      onUpdate(updated);
      toast.success('참조가 삭제되었습니다');
    } catch (err: any) {
      toast.error(err.message || '참조 삭제 실패');
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-gray-800 rounded-xl w-full max-w-[95vw] sm:max-w-2xl h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className={`px-2 py-0.5 text-xs rounded ${priorityColors[localTask.priority]} text-white`}
              >
                {priorityLabels[localTask.priority]}
              </span>
              <span className="text-gray-400 text-sm">{localTask.status}</span>
            </div>
            {isEditing ? (
              <div>
                <input
                  value={editForm.title}
                  onChange={(e) =>
                    setEditForm({ ...editForm, title: e.target.value })
                  }
                  maxLength={200}
                  className="text-xl font-bold text-white bg-gray-700 border border-gray-600 rounded px-2 py-1 w-full focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                <span className={`text-xs ${editForm.title.length > 180 ? 'text-red-400' : 'text-gray-500'} ml-1`}>
                  {editForm.title.length}/200
                </span>
              </div>
            ) : (
              <h2 className="text-xl font-bold text-white truncate" title={localTask.title}>
                {localTask.title}
              </h2>
            )}
          </div>
          <div className="flex items-center gap-2 ml-3 flex-shrink-0">
            {!isEditing && (
              <>
                <button
                  onClick={() => setIsEditing(true)}
                  className="text-gray-400 hover:text-blue-400 text-sm px-2 py-1 rounded hover:bg-gray-700 transition-colors"
                >
                  수정
                </button>
                <button
                  onClick={() => setShowDeleteConfirm(true)}
                  className="text-gray-400 hover:text-red-400 text-sm px-2 py-1 rounded hover:bg-gray-700 transition-colors"
                >
                  삭제
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white text-2xl leading-none"
            >
              &times;
            </button>
          </div>
        </div>

        {/* Delete Confirmation */}
        {showDeleteConfirm && (
          <div className="p-3 bg-red-900/30 border-b border-red-700 flex items-center justify-between">
            <span className="text-red-300 text-sm">
              이 태스크를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-3 py-1 text-sm text-gray-300 hover:text-white transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    삭제 중...
                  </>
                ) : '삭제'}
              </button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-gray-700 overflow-x-auto">
          <button
            onClick={() => setActiveTab('detail')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'detail'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
            }`}
          >
            상세
          </button>
          <button
            onClick={() => setActiveTab('todos')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'todos'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
            }`}
          >
            TODO ({localTask.todos.length})
          </button>
          <button
            onClick={() => setActiveTab('activity')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'activity'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
            }`}
          >
            이력 ({localTask.activityLog.length})
          </button>
          <button
            onClick={() => setActiveTab('comments')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeTab === 'comments'
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
            }`}
          >
            AI 대화 ({localTask.comments.length})
          </button>
          {localTask.references && localTask.references.length > 0 && (
            <button
              onClick={() => setActiveTab('references')}
              className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                activeTab === 'references'
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-700'
              }`}
            >
              참조 자료 ({localTask.references.length})
            </button>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 'detail' && (
            <div className="space-y-4">
              {isEditing ? (
                <>
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <h4 className="text-sm font-medium text-gray-400">
                        설명
                      </h4>
                      {editForm.description.length > 1500 && (
                        <span className={`text-xs ${editForm.description.length > 1800 ? 'text-red-400' : 'text-yellow-400'}`}>
                          {editForm.description.length}/2000
                        </span>
                      )}
                    </div>
                    <textarea
                      value={editForm.description}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          description: e.target.value,
                        })
                      }
                      maxLength={2000}
                      rows={4}
                      className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        우선순위
                      </h4>
                      <select
                        value={editForm.priority}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            priority: e.target.value as TaskPriority,
                          })
                        }
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="low">낮음</option>
                        <option value="medium">보통</option>
                        <option value="high">높음</option>
                        <option value="urgent">긴급</option>
                      </select>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        담당자
                      </h4>
                      <input
                        type="text"
                        value={editForm.assigneeName}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            assigneeName: e.target.value,
                          })
                        }
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        마감일
                      </h4>
                      <input
                        type="date"
                        value={editForm.dueDate}
                        onChange={(e) =>
                          setEditForm({ ...editForm, dueDate: e.target.value })
                        }
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        태그
                      </h4>
                      <input
                        type="text"
                        value={editForm.tags}
                        onChange={(e) =>
                          setEditForm({ ...editForm, tags: e.target.value })
                        }
                        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        placeholder="쉼표로 구분"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      onClick={() => {
                        setIsEditing(false);
                        setEditingTodoId(null);
                        setEditingTodoText('');
                        setNewTodoText('');
                      }}
                      className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
                    >
                      취소
                    </button>
                    <button
                      onClick={handleSaveEdit}
                      disabled={saving}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {saving ? (
                        <>
                          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          저장 중...
                        </>
                      ) : '저장'}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <h4 className="text-sm font-medium text-gray-400 mb-1">
                      설명
                    </h4>
                    {localTask.description ? (
                      <StyledMarkdown variant="comment">{localTask.description}</StyledMarkdown>
                    ) : (
                      <p className="text-gray-500">(설명 없음)</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        담당자
                      </h4>
                      <p className="text-gray-200">
                        {localTask.assigneeName || '-'}
                      </p>
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-gray-400 mb-1">
                        마감일
                      </h4>
                      <p className="text-gray-200">
                        {localTask.dueDate
                          ? new Date(localTask.dueDate).toLocaleDateString(
                              'ko-KR'
                            )
                          : '-'}
                      </p>
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-gray-400 mb-1">
                      태그
                    </h4>
                    <div className="flex flex-wrap gap-1">
                      {localTask.tags.length > 0 ? (
                        localTask.tags.map((tag) => (
                          <span
                            key={tag}
                            className="px-2 py-1 text-sm rounded bg-gray-700 text-gray-300"
                          >
                            {tag}
                          </span>
                        ))
                      ) : (
                        <span className="text-gray-500 text-sm">-</span>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === 'todos' && (
            <div className="space-y-3">
              {/* Progress indicator */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">
                  {localTask.todos.filter(t => t.completed).length}/{localTask.todos.length} 완료
                </span>
              </div>

              {/* Add TODO input (edit mode only) */}
              {isEditing && (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newTodoText}
                    onChange={(e) => setNewTodoText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleAddTodo();
                      }
                    }}
                    placeholder="새 TODO 항목 추가..."
                    maxLength={200}
                    className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <button
                    onClick={handleAddTodo}
                    disabled={!newTodoText.trim()}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    추가
                  </button>
                </div>
              )}

              {/* TODO list */}
              {localTask.todos.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-4">
                  {isEditing ? 'TODO 항목이 없습니다. 위에서 추가해보세요.' : 'TODO 항목이 없습니다.'}
                </p>
              ) : (
                localTask.todos.map((todo) => (
                  <div
                    key={todo.id}
                    className="flex items-center gap-3 p-2 rounded hover:bg-gray-700 group"
                  >
                    <input
                      type="checkbox"
                      checked={todo.completed}
                      onChange={() => handleToggleTodo(todo.id)}
                      className="w-4 h-4 rounded border-gray-500 accent-blue-500 flex-shrink-0"
                    />
                    {isEditing && editingTodoId === todo.id ? (
                      <input
                        type="text"
                        value={editingTodoText}
                        onChange={(e) => setEditingTodoText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            handleSaveTodoEdit(todo.id);
                          } else if (e.key === 'Escape') {
                            setEditingTodoId(null);
                            setEditingTodoText('');
                          }
                        }}
                        onBlur={() => handleSaveTodoEdit(todo.id)}
                        autoFocus
                        maxLength={200}
                        className="flex-1 bg-gray-600 border border-gray-500 rounded px-2 py-1 text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    ) : (
                      <span
                        onDoubleClick={isEditing ? () => {
                          setEditingTodoId(todo.id);
                          setEditingTodoText(todo.text);
                        } : undefined}
                        className={`flex-1 ${isEditing ? 'cursor-text' : 'cursor-default'} ${
                          todo.completed ? 'text-gray-500 line-through' : 'text-gray-200'
                        }`}
                        title={isEditing ? '더블클릭하여 편집' : undefined}
                      >
                        {todo.text}
                      </span>
                    )}
                    {isEditing && (
                      <button
                        onClick={() => handleDeleteTodo(todo.id)}
                        className="text-gray-400 hover:text-red-400 text-sm px-1 transition-colors"
                        title="삭제"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))
              )}

              {/* Save/Cancel buttons in edit mode */}
              {isEditing && (
                <div className="flex justify-end gap-3 pt-2">
                  <button
                    onClick={() => setIsEditing(false)}
                    className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
                  >
                    수정 완료
                  </button>
                </div>
              )}
            </div>
          )}

          {activeTab === 'activity' && (
            <div className="space-y-3">
              {localTask.activityLog.length === 0 ? (
                <p className="text-gray-400">활동 이력이 없습니다.</p>
              ) : (
                localTask.activityLog.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-start gap-3 text-sm border-l-2 border-gray-600 pl-3 group relative"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-blue-400 font-medium">
                          {log.userName}
                        </span>
                        <span className="text-gray-300 font-medium"> · {log.action}</span>
                        {isOnline && (
                          <button
                            onClick={() => handleDeleteActivity(log.id)}
                            className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-400 text-xs px-2 py-1"
                            title="이력 삭제"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                      {log.detail && (
                        <div className="mt-1">
                          <StyledMarkdown variant="activity">{log.detail}</StyledMarkdown>
                        </div>
                      )}
                      <div className="text-gray-500 text-xs mt-1">
                        {new Date(log.timestamp).toLocaleString('ko-KR')}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'comments' && (
            <div className="flex flex-col h-full">
              {/* Chat messages */}
              <div className="flex-1 overflow-auto space-y-3 mb-3">
                {localTask.comments.length === 0 && !aiLoading ? (
                  <div className="text-center py-8">
                    <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center mx-auto mb-3">
                      <span className="text-2xl">💬</span>
                    </div>
                    <p className="text-gray-400 text-sm mb-1">이 태스크에 대해 AI에게 질문하세요</p>
                    <p className="text-gray-500 text-xs">태스크 내용을 맥락으로 이해하고 답변합니다</p>
                  </div>
                ) : (
                  <>
                    {localTask.comments.map((comment) => {
                      const isAi = comment.authorId === 'ai-assistant';
                      return (
                        <div
                          key={comment.id}
                          className={`flex ${isAi ? 'justify-start' : 'justify-end'}`}
                        >
                          <div className={`max-w-[80%] ${isAi ? 'order-1' : ''}`}>
                            <div className={`flex items-center gap-2 mb-1 ${isAi ? '' : 'justify-end'}`}>
                              {isAi && (
                                <div className="w-5 h-5 rounded-full bg-green-600 flex items-center justify-center text-xs text-white flex-shrink-0">
                                  A
                                </div>
                              )}
                              <span className="text-gray-500 text-xs">
                                {comment.authorName} · {new Date(comment.createdAt).toLocaleString('ko-KR')}
                              </span>
                              {!isAi && isOnline && (
                                <button
                                  onClick={() => handleDeleteComment(comment.id)}
                                  className="text-gray-500 hover:text-red-400 text-xs"
                                  title="삭제"
                                >
                                  ✕
                                </button>
                              )}
                            </div>
                            <div
                              className={`rounded-lg px-3 py-2 ${
                                isAi
                                  ? 'bg-gray-700 text-gray-200'
                                  : 'bg-blue-600 text-white'
                              }`}
                            >
                              <StyledMarkdown variant="comment">{comment.content}</StyledMarkdown>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                    {aiLoading && (
                      <div className="flex justify-start">
                        <div className="max-w-[80%]">
                          <div className="flex items-center gap-2 mb-1">
                            <div className="w-5 h-5 rounded-full bg-green-600 flex items-center justify-center text-xs text-white">
                              A
                            </div>
                            <span className="text-gray-500 text-xs">AI 어시스턴트</span>
                          </div>
                          <div className="bg-gray-700 rounded-lg px-4 py-3">
                            <div className="flex gap-1">
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                              <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
                <div ref={commentsEndRef} />
              </div>

              {/* Input */}
              <div className="flex gap-2 pt-2 border-t border-gray-700">
                <input
                  type="text"
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  onKeyDown={handleCommentKeyDown}
                  placeholder="이 태스크에 대해 AI에게 질문하세요..."
                  disabled={aiLoading}
                  className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                />
                <button
                  onClick={handleAddComment}
                  disabled={!commentText.trim() || aiLoading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {aiLoading ? (
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : '전송'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'references' && localTask.references && (
            <div className="space-y-3">
              {localTask.references.map((ref) => (
                <div
                  key={ref.docId}
                  className="bg-gray-700/50 border border-gray-600 rounded-lg overflow-hidden group"
                >
                  <div className="relative">
                    <button
                      onClick={() => {
                        setExpandedRefs((prev) => {
                          const next = new Set(prev);
                          if (next.has(ref.docId)) {
                            next.delete(ref.docId);
                          } else {
                            next.add(ref.docId);
                          }
                          return next;
                        });
                      }}
                      className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-700/80 transition-colors text-left"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <span className="text-lg flex-shrink-0">📄</span>
                        <div className="flex-1 min-w-0">
                          <div className="text-gray-200 font-medium truncate">
                            {ref.title}
                          </div>
                          <div className="flex items-center gap-2 mt-1">
                            {ref.category && (
                              <span className="text-xs bg-blue-600/30 text-blue-300 px-2 py-0.5 rounded">
                                {ref.category}
                              </span>
                            )}
                            <span className="text-xs bg-green-600/30 text-green-300 px-2 py-0.5 rounded">
                              유사도: {(ref.score * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                      </div>
                      <span className="text-gray-400 text-sm flex-shrink-0 ml-2">
                        {expandedRefs.has(ref.docId) ? '▲' : '▼'}
                      </span>
                    </button>
                    {isOnline && (
                      <button
                        onClick={() => handleDeleteReference(ref.docId)}
                        className="absolute top-3 right-10 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-400 text-xs px-2 py-1 bg-gray-800 rounded"
                        title="참조 삭제"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {expandedRefs.has(ref.docId) && (
                    <div className="px-4 pb-4 border-t border-gray-600">
                      <div className="mt-3">
                        <StyledMarkdown variant="comment">{ref.content}</StyledMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// Main Page Component
// ============================================

export function TaskBoardPage() {
  const { toast } = useToast();
  const { setTaskContext, clearContext } = useChatAssistant();
  const { onDataChange, setMode } = useChatContext();
  const [tasks, setTasks] = useState<TaskCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [isOnline, setIsOnline] = useState(false);
  const [selectedTask, setSelectedTask] = useState<TaskCard | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createDefaultStatus, setCreateDefaultStatus] = useState<TaskStatus>('todo');
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const draggedTaskId = useRef<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPriority, setFilterPriority] = useState<TaskPriority | 'all'>('all');
  const initialLoadRef = useRef(true);

  useEffect(() => {
    document.title = '태스크 보드 | AI 업무도우미';
  }, []);

  useEffect(() => {
    setMode('taskboard');
    return () => setMode('general');
  }, [setMode]);

  // ── Data loading ──────────────────────────────────────────────

  const loadTasks = useCallback(async () => {
    try {
      const apiTasks = await taskApi.list();
      setTasks(apiTasks);
      setIsOnline(true);
      if (initialLoadRef.current) {
        initialLoadRef.current = false;
      }
    } catch {
      setTasks([...mockTasks]);
      setIsOnline(false);
      if (initialLoadRef.current) {
        toast.info('오프라인 모드로 실행 중입니다', 4000);
        initialLoadRef.current = false;
      }
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    return onDataChange((target) => {
      if (target.includes('task')) loadTasks();
    });
  }, [onDataChange, loadTasks]);

  // ── Keyboard shortcuts ────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input/textarea
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable) {
        // Only handle Escape in input fields
        if (e.key === 'Escape') {
          target.blur();
        }
        return;
      }

      // Escape: close any open modal
      if (e.key === 'Escape') {
        if (selectedTask) {
          setSelectedTask(null);
        } else if (showCreateModal) {
          setShowCreateModal(false);
        }
      }

      // Ctrl+N or Cmd+N: open create modal
      if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        setCreateDefaultStatus('todo');
        setShowCreateModal(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedTask, showCreateModal]);

  // ── Set chat context when task is selected ──────────────────────

  useEffect(() => {
    if (selectedTask) {
      setTaskContext(selectedTask);
    } else {
      clearContext();
    }
  }, [selectedTask, setTaskContext, clearContext]);

  const filteredTasks = useMemo(() => {
    return tasks.filter(task => {
      const matchesSearch = !searchQuery ||
        task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesPriority = filterPriority === 'all' || task.priority === filterPriority;
      return matchesSearch && matchesPriority;
    });
  }, [tasks, searchQuery, filterPriority]);

  const columns = buildColumns(filteredTasks);

  // ── Task CRUD ─────────────────────────────────────────────────

  const handleCreateTask = useCallback(
    async (formData: TaskFormData) => {
      const now = new Date().toISOString();
      const parsedTags = formData.tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);

      if (isOnline) {
        try {
          const createData: CreateTaskData = {
            title: formData.title,
            description: formData.description || undefined,
            status: formData.status,
            priority: formData.priority,
            tags: parsedTags.length > 0 ? parsedTags : undefined,
            assigneeName: formData.assigneeName || undefined,
            dueDate: formData.dueDate ? `${formData.dueDate}T00:00:00` : undefined,
          };
          const created = await taskApi.create(createData);
          setTasks((prev) => [...prev, created]);
          toast.success('태스크가 생성되었습니다');
        } catch (err) {
          const detail = err instanceof Error ? err.message : '';
          toast.error(`태스크 생성에 실패했습니다${detail ? `: ${detail}` : ''}`);
          return;
        }
      } else {
        const newTask: TaskCard = {
          id: generateId(),
          title: formData.title,
          description: formData.description,
          status: formData.status,
          priority: formData.priority,
          tags: parsedTags,
          assigneeName: formData.assigneeName || undefined,
          dueDate: formData.dueDate || undefined,
          todos: [],
          comments: [],
          activityLog: [],
          references: [],
          createdAt: now,
          updatedAt: now,
        };
        setTasks((prev) => [...prev, newTask]);
        toast.success('태스크가 생성되었습니다 (오프라인)');
      }

      setShowCreateModal(false);
    },
    [isOnline, toast]
  );

  const handleUpdateTask = useCallback((updated: TaskCard) => {
    setTasks((prev) =>
      prev.map((t) => (t.id === updated.id ? updated : t))
    );
    setSelectedTask((prev) => (prev?.id === updated.id ? updated : prev));
  }, []);

  const handleDeleteTask = useCallback((taskId: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
    setSelectedTask(null);
  }, []);

  // ── Drag and Drop ─────────────────────────────────────────────

  const handleDragStart = useCallback(
    (e: React.DragEvent, taskId: string) => {
      draggedTaskId.current = taskId;
      e.dataTransfer.effectAllowed = 'move';
      // Store task ID in dataTransfer for cross-browser compat
      e.dataTransfer.setData('text/plain', taskId);
    },
    []
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent, status: TaskStatus) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDragOverColumn(status);
    },
    []
  );

  const handleDragLeave = useCallback(() => {
    setDragOverColumn(null);
  }, []);

  const handleDrop = useCallback(
    async (e: React.DragEvent, targetStatus: TaskStatus) => {
      e.preventDefault();
      setDragOverColumn(null);

      const taskId = draggedTaskId.current || e.dataTransfer.getData('text/plain');
      if (!taskId) return;

      const task = tasks.find((t) => t.id === taskId);
      if (!task || task.status === targetStatus) return;

      // Optimistic update
      const updatedTask = {
        ...task,
        status: targetStatus,
        updatedAt: new Date().toISOString(),
      };

      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? updatedTask : t))
      );

      if (isOnline) {
        try {
          await taskApi.updateStatus(taskId, targetStatus);
        } catch (err) {
          // Revert on failure
          setTasks((prev) =>
            prev.map((t) => (t.id === taskId ? task : t))
          );
          const detail = err instanceof Error ? err.message : '';
          toast.error(`상태 변경에 실패했습니다${detail ? `: ${detail}` : ''}`);
        }
      }

      draggedTaskId.current = null;
    },
    [tasks, isOnline, toast]
  );

  // ── Column add card handler ───────────────────────────────────

  const handleAddCardToColumn = useCallback((status: TaskStatus) => {
    setCreateDefaultStatus(status);
    setShowCreateModal(true);
  }, []);

  // ── Render ────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="h-full flex flex-col">
        <header className="p-4 border-b border-gray-700">
          <h1 className="text-2xl font-bold text-white">태스크 보드</h1>
          <p className="text-gray-400 text-sm">
            프로젝트 태스크를 칸반 보드로 관리합니다
          </p>
        </header>
        <Spinner />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <header className="p-4 border-b border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white">태스크 보드</h1>
              {!isOnline && (
                <span className="px-2 py-0.5 text-xs rounded bg-yellow-600/30 text-yellow-400 border border-yellow-600/50">
                  오프라인
                </span>
              )}
            </div>
            <p className="text-gray-400 text-sm">
              프로젝트 태스크를 칸반 보드로 관리합니다
            </p>
          </div>
          <button
            onClick={() => {
              setCreateDefaultStatus('todo');
              setShowCreateModal(true);
            }}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <span>+</span>
            <span>새 태스크</span>
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="태스크 검색 (제목, 설명, 태그)..."
              className="w-full bg-gray-800 border border-gray-600 rounded-lg pl-9 pr-3 py-1.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value as TaskPriority | 'all')}
            className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">모든 우선순위</option>
            <option value="urgent">긴급</option>
            <option value="high">높음</option>
            <option value="medium">보통</option>
            <option value="low">낮음</option>
          </select>
          {(searchQuery || filterPriority !== 'all') && (
            <button
              onClick={() => { setSearchQuery(''); setFilterPriority('all'); }}
              className="text-gray-400 hover:text-white text-sm underline"
            >
              필터 초기화
            </button>
          )}
          <span className="text-gray-500 text-xs">
            {filteredTasks.length}/{tasks.length}건
          </span>
        </div>
      </header>

      {/* Board */}
      <div className="flex-1 overflow-x-auto p-4">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center h-full">
            <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-4">
              <span className="text-3xl">📋</span>
            </div>
            <h3 className="text-lg font-medium text-gray-300 mb-2">태스크가 없습니다</h3>
            <p className="text-gray-500 text-sm mb-4 max-w-md">첫 번째 태스크를 추가하여 프로젝트 관리를 시작하세요</p>
            <button
              onClick={() => {
                setCreateDefaultStatus('todo');
                setShowCreateModal(true);
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              + 첫 번째 태스크 만들기
            </button>
          </div>
        ) : (
          <div className="flex gap-4 h-full">
            {columns.map((column) => (
              <Column
                key={column.id}
                column={column}
                onCardClick={setSelectedTask}
                onAddCard={handleAddCardToColumn}
                onDragStart={handleDragStart}
                onDrop={handleDrop}
                dragOverColumn={dragOverColumn}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <TaskCreateModal
          defaultStatus={createDefaultStatus}
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateTask}
        />
      )}

      {/* Detail Modal */}
      {selectedTask && (
        <TaskDetailModal
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
          onUpdate={handleUpdateTask}
          onDelete={handleDeleteTask}
          isOnline={isOnline}
        />
      )}
    </div>
  );
}
