import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { ToastMessage } from "../../types/domain";

type ToastContextValue = {
  notify: (message: Omit<ToastMessage, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);
  const notify = useCallback((message: Omit<ToastMessage, "id">) => {
    const id = Date.now() + Math.floor(Math.random() * 10_000);
    setMessages((current) => [...current, { ...message, id }]);
    window.setTimeout(() => setMessages((current) => current.filter((item) => item.id !== id)), 5_500);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="true">
        {messages.map((message) => (
          <div className={`toast toast--${message.tone}`} key={message.id}>
            <div>
              <strong>{message.title}</strong>
              {message.description && <p>{message.description}</p>}
            </div>
            <button
              className="toast__dismiss"
              type="button"
              aria-label={`Dismiss ${message.title}`}
              onClick={() => setMessages((current) => current.filter((item) => item.id !== message.id))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}
