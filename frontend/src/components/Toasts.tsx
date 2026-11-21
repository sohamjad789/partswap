import { useCallback, useState } from "react";
import { Icon, type IconName } from "./Icon";

export interface Toast { id: number; tone: "success" | "info" | "error"; title: string; body?: string; }
const toneIcon: Record<Toast["tone"], IconName> = { success: "check", info: "info", error: "alert" };

let nextId = 1;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts(list => list.filter(t => t.id !== id)), []);
  const push = useCallback((toast: Omit<Toast, "id">) => {
    const id = nextId++;
    setToasts(list => [...list.slice(-2), { ...toast, id }]);
    window.setTimeout(() => dismiss(id), toast.tone === "error" ? 6000 : 3500);
  }, [dismiss]);
  return { toasts, push, dismiss };
}

export function Toasts({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast ${toast.tone}`}>
          <span className="toast-icon"><Icon name={toneIcon[toast.tone]} size={16} strokeWidth={2.4} /></span>
          <div className="toast-text"><strong>{toast.title}</strong>{toast.body && <span>{toast.body}</span>}</div>
          <button type="button" onClick={() => onDismiss(toast.id)} aria-label="Dismiss"><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>
  );
}
