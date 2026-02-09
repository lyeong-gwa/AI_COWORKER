# Data Refresh Mechanism Implementation

## Summary
Add data refresh callback to ChatContext so pages auto-refresh when AI assistant performs actions.

## Files Modified

### 1. ChatContext.tsx ✓ COMPLETED
- Added `onDataChange` to interface
- Added listener ref and implementation
- Replaced TODO with listener invocation
- Added to Provider value

### 2. TaskBoardPage.tsx - NEEDS UPDATE

Add import:
```typescript
import { useChatContext } from '../contexts/ChatContext';
```

Add hook and listener in TaskBoardPage component (after line 966):
```typescript
const { onDataChange } = useChatContext();
```

Extract loadTasks function (lines 983-1001) and add listener after the initial useEffect (around line 1008):
```typescript
// Extract loadTasks as a standalone function
const loadTasks = useCallback(async () => {
  try {
    const apiTasks = await taskApi.list();
    setTasks(apiTasks);
    setIsOnline(true);
  } catch {
    setTasks([...mockTasks]);
    setIsOnline(false);
    toast.info('오프라인 모드로 실행 중입니다', 4000);
  } finally {
    setLoading(false);
  }
}, [toast]);

// Initial load
useEffect(() => {
  loadTasks();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);

// Listen for data changes from AI assistant
useEffect(() => {
  return onDataChange((target) => {
    if (target.includes('task')) {
      loadTasks();
    }
  });
}, [onDataChange, loadTasks]);
```

### 3-6. Similar pattern for other pages
- KnowledgeBasePage: reload when target includes 'knowledge' or 'document'
- WorkflowPage: reload when target includes 'workflow'
- ToolManagementPage: reload when target includes 'tool'
- NodeManagementPage: reload when target includes 'node'
