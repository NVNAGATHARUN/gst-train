import { RailIcon } from "./rail-icon";

export function DataState({ title, detail, action, onAction }: {
  title: string; detail: string; action?: string; onAction?: () => void;
}) {
  return <div className="data-state" role="status">
    <span className="data-state-marker" aria-hidden="true"><RailIcon name="data" size={20}/></span>
    <strong>{title}</strong><p>{detail}</p>
    {action && onAction ? <button className="button button-outline" type="button" onClick={onAction}>{action}</button> : null}
  </div>;
}
