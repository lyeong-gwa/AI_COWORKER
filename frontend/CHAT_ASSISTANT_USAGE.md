# Chat Assistant Usage Guide

## Overview

The Chat Assistant component provides context-aware AI interaction throughout the application. Users can select items (tasks, tools, nodes, workflows, documents) and the assistant will understand the context.

## Components

### 1. ChatContext (`src/contexts/ChatContext.tsx`)

Global state management for the chat assistant.

```tsx
interface ChatContextValue {
  isOpen: boolean;
  messages: ChatMessage[];
  selectedContext: ChatContextType;
  isLoading: boolean;
  toggleChat: () => void;
  sendMessage: (content: string) => Promise<void>;
  setContext: (context: ChatContextType) => void;
  clearContext: () => void;
}
```

### 2. ChatAssistant Component (`src/components/common/ChatAssistant.tsx`)

The UI component that renders:
- Floating chat button (bottom-right)
- Chat panel with messages
- Context display area
- Message input

### 3. useChatAssistant Hook (`src/hooks/useChatAssistant.ts`)

Convenience hook for setting context from any page.

## Usage Examples

### Example 1: Task Board Page - Set Task Context

```tsx
import { useChatAssistant } from '../hooks/useChatAssistant';

function TaskBoardPage() {
  const { setTaskContext } = useChatAssistant();

  const handleTaskClick = (task: TaskCard) => {
    // Open chat with task context
    setTaskContext(task);
  };

  return (
    <div>
      {tasks.map(task => (
        <div key={task.id}>
          {task.title}
          <button onClick={() => handleTaskClick(task)}>
            💬 AI에게 물어보기
          </button>
        </div>
      ))}
    </div>
  );
}
```

### Example 2: Tool Management Page - Set Tool Context

```tsx
import { useChatAssistant } from '../hooks/useChatAssistant';

function ToolManagementPage() {
  const { setToolContext } = useChatAssistant();

  return (
    <div>
      {tools.map(tool => (
        <div key={tool.id}>
          {tool.name}
          <button onClick={() => setToolContext(tool)}>
            🤖 AI 도움말
          </button>
        </div>
      ))}
    </div>
  );
}
```

### Example 3: Direct Context Setting

```tsx
import { useChatContext } from '../contexts/ChatContext';

function MyComponent() {
  const { setContext, toggleChat } = useChatContext();

  const handleHelp = (workflow: Workflow) => {
    // Set context and open chat
    setContext({ type: 'workflow', data: workflow });
    toggleChat();
  };

  return <button onClick={() => handleHelp(workflow)}>Help</button>;
}
```

### Example 4: Clear Context

```tsx
import { useChatContext } from '../contexts/ChatContext';

function MyComponent() {
  const { clearContext } = useChatContext();

  return (
    <button onClick={clearContext}>
      Clear Chat Context
    </button>
  );
}
```

## Context Types

The assistant supports these context types:

| Type | Data | Icon | Use Case |
|------|------|------|----------|
| `none` | - | - | General conversation |
| `task` | `TaskCard` | 📋 | Task management help |
| `tool` | `ToolDefinition` | 🔧 | Tool configuration |
| `node` | `AINode` | 🔷 | Node editing help |
| `workflow` | `Workflow` | ⚙️ | Workflow debugging |
| `document` | `KnowledgeDocument` | 📚 | Document questions |

## Features

### Auto-scroll

Messages automatically scroll to the bottom when new messages arrive.

### Minimize/Maximize

Users can minimize the chat panel to save screen space while keeping the conversation history.

### Context Persistence

The selected context persists across messages until cleared, allowing natural follow-up questions.

### Loading States

Visual feedback during AI response generation with animated loading dots.

### Keyboard Shortcuts

- **Enter**: Send message
- **Shift + Enter**: New line (planned)

## Styling

The component uses consistent dark theme styling:
- Primary: `bg-gray-800`, `border-gray-700`
- Accent: `bg-blue-600` gradient
- Messages: User (blue), Assistant (gray)
- Custom shades: `gray-650`, `gray-750`, `gray-850`

## Future Enhancements

- [ ] Multiline message support
- [ ] Message editing/deletion
- [ ] Conversation history export
- [ ] Voice input/output
- [ ] File attachment support
- [ ] Code syntax highlighting in messages
- [ ] Suggested actions based on context
- [ ] Integration with actual AI backend API
