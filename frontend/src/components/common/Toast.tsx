import React, { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';

// Toast types
export type ToastType = 'success' | 'error' | 'warning' | 'info';

// Toast interface
export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

// Toast context interface
interface ToastContextType {
  toast: {
    success: (message: string, duration?: number) => void;
    error: (message: string, duration?: number) => void;
    warning: (message: string, duration?: number) => void;
    info: (message: string, duration?: number) => void;
  };
}

// Create context
const ToastContext = createContext<ToastContextType | undefined>(undefined);

// Toast Provider Props
interface ToastProviderProps {
  children: React.ReactNode;
}

// Toast Provider Component
export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Add toast
  const addToast = useCallback((type: ToastType, message: string, duration = 3000) => {
    const id = `toast-${Date.now()}-${Math.random()}`;
    const newToast: Toast = { id, type, message, duration };

    setToasts((prev) => [...prev, newToast]);

    // Auto-dismiss
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  }, []);

  // Remove toast
  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  // Toast methods (memoized to prevent consumer re-renders)
  const toast = useMemo(() => ({
    success: (message: string, duration?: number) => addToast('success', message, duration),
    error: (message: string, duration?: number) => addToast('error', message, duration),
    warning: (message: string, duration?: number) => addToast('warning', message, duration),
    info: (message: string, duration?: number) => addToast('info', message, duration),
  }), [addToast]);

  const contextValue = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
}

// Toast Container Component
interface ToastContainerProps {
  toasts: Toast[];
  onRemove: (id: string) => void;
}

function ToastContainer({ toasts, onRemove }: ToastContainerProps) {
  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  );
}

// Toast Item Component
interface ToastItemProps {
  toast: Toast;
  onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
  const [isExiting, setIsExiting] = useState(false);

  // Handle close
  const handleClose = () => {
    setIsExiting(true);
    setTimeout(() => {
      onRemove(toast.id);
    }, 300); // Match animation duration
  };

  // Auto-dismiss setup
  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      // Trigger exit animation 300ms before removal
      const exitTimer = setTimeout(() => {
        setIsExiting(true);
      }, toast.duration - 300);

      return () => clearTimeout(exitTimer);
    }
  }, [toast.duration]);

  // Style variants by type
  const typeStyles = {
    success: {
      bg: 'bg-green-600',
      border: 'border-green-500',
      icon: '✓',
      iconBg: 'bg-green-500',
    },
    error: {
      bg: 'bg-red-600',
      border: 'border-red-500',
      icon: '✕',
      iconBg: 'bg-red-500',
    },
    warning: {
      bg: 'bg-yellow-600',
      border: 'border-yellow-500',
      icon: '⚠',
      iconBg: 'bg-yellow-500',
    },
    info: {
      bg: 'bg-blue-600',
      border: 'border-blue-500',
      icon: 'ℹ',
      iconBg: 'bg-blue-500',
    },
  };

  const styles = typeStyles[toast.type];

  return (
    <div
      className={`
        ${styles.bg} ${styles.border}
        border rounded-lg shadow-lg
        min-w-[320px] max-w-md
        flex items-start gap-3 p-4
        pointer-events-auto
        transition-all duration-300 ease-out
        ${
          isExiting
            ? 'opacity-0 translate-x-8 scale-95'
            : 'opacity-100 translate-x-0 scale-100'
        }
        animate-[slideIn_0.3s_ease-out]
      `}
    >
      {/* Icon */}
      <div
        className={`
          ${styles.iconBg}
          w-6 h-6 rounded-full
          flex items-center justify-center
          text-white font-bold text-sm
          flex-shrink-0
        `}
      >
        {styles.icon}
      </div>

      {/* Message */}
      <p className="flex-1 text-white text-sm font-medium leading-relaxed">
        {toast.message}
      </p>

      {/* Close Button */}
      <button
        onClick={handleClose}
        className="
          text-white hover:bg-white/20
          rounded p-1 transition-colors
          flex-shrink-0
        "
        aria-label="Close"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}

// Hook to use toast
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}

// Add keyframes to global CSS (add this to index.css or tailwind config)
// @keyframes slideIn {
//   from {
//     opacity: 0;
//     transform: translateX(2rem);
//   }
//   to {
//     opacity: 1;
//     transform: translateX(0);
//   }
// }
