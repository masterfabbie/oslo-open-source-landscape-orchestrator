import { useApp } from "./ui";

export interface Toast {
  id: number;
  kind: "success" | "error";
  text: string;
  activityId?: number;
}

export function Toasts({ toasts, onClose }: { toasts: Toast[]; onClose: (id: number) => void }) {
  const { t } = useApp();
  return (
    <div className="oslo-toasts" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`oslo-toast oslo-toast-${toast.kind}`}>
          <span>{toast.text}</span>
          {toast.activityId !== undefined && (
            <a href={`/activities/${toast.activityId}`}>{t("ui.show_activity", { id: toast.activityId })}</a>
          )}
          <button type="button" className="link" onClick={() => onClose(toast.id)} aria-label={t("ui.close")}>
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
