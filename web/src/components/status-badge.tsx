type Tone = "info" | "good" | "warn" | "bad" | "muted";
function toneFor(label: string): Tone {
  const value = label.toUpperCase();
  if (["PASS", "READY", "RESPONSIVE", "ACTIVE", "CURRENT", "COMPLETED", "OPTIMAL", "FIRM"].includes(value)) return "good";
  if (["FAIL", "ERROR", "FAILED", "DEGRADED", "ABSENT", "INACTIVE", "INFEASIBLE", "NOT_READY", "BLOCKED", "SUPERSEDED"].includes(value)) return "bad";
  if (["CONDITIONAL", "STALE", "UNKNOWN", "NOT_ASSESSED", "QUEUED_PREPARATION", "QUEUED_SOLVE", "RUNNING"].includes(value)) return "warn";
  return "info";
}
export function StatusBadge({ value, label, tone }: { value: string | null | undefined; label?: string; tone?: Tone }) {
  if (!value) return <span className="badge badge-muted">Unavailable</span>;
  return <span className={`badge badge-${tone ?? toneFor(value)}`} title={value}>
    <span aria-hidden="true" className="badge-dot" />{label ?? value.replaceAll("_", " ")}
  </span>;
}
export function DepartmentBadge({ department }: { department: string }) {
  const code = department === "ENGINEERING" ? "ENG" : department === "TRD" ? "TRD" : department === "SNT" ? "S&T" : department;
  return <span className={`department department-${department.toLowerCase()}`}>{code}</span>;
}
