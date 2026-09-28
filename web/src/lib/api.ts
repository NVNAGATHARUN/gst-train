export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail :
      Array.isArray(detail) ? detail.slice(0,3).map(item => {
        if (!item || typeof item !== "object") return "Invalid input";
        const problem = item as {loc?: unknown;msg?: unknown};
        const field = Array.isArray(problem.loc) ? problem.loc.filter(part => part !== "body").join(".") : "Input";
        return `${field}: ${String(problem.msg ?? "invalid value")}`;
      }).join("; ") :
      detail && typeof detail === "object" && "code" in detail ? String(detail.code) : `Request failed (${status})`);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, options: { method?: string; body?: unknown; csrf?: string; signal?: AbortSignal } = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? "GET",
    headers: {
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(options.csrf ? { "X-CSRF-Token": options.csrf } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
  });
  if (!response.ok) {
    let detail: unknown = `HTTP ${response.status}`;
    try { detail = (await response.json()).detail ?? detail; } catch { /* The server may be unavailable or return non-JSON. */ }
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      if (error.detail === "INVALID_CREDENTIAL") return "Credential not recognized. Check your assigned role credential and try again.";
      return "Your session expired. Sign in again.";
    }
    if (error.status === 403) {
      if (error.detail === "BROWSER_ORIGIN_FORBIDDEN" || error.detail === "CROSS_SITE_REQUEST_FORBIDDEN") {
        return "Access denied: Browser origin not permitted by security policy.";
      }
      return "Your role cannot perform this action.";
    }
    if (error.status === 409) return `The planning state changed: ${error.message}. Refresh the evidence before acting.`;
    if (error.status === 429) return "Too many sign-in attempts. Wait and try again.";
    return error.message;
  }
  return "R-MAPS could not reach the API. Check the backend connection and retry.";
}

export function shortId(id: string | null | undefined): string {
  return id ? id.length > 14 ? `${id.slice(0, 8)}…` : id : "Not selected";
}

export const zone = "Asia/Kolkata";
export function timeAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : new Intl.DateTimeFormat("en-IN", {
    timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23"
  }).format(date);
}
export function dateAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : new Intl.DateTimeFormat("en-IN", {
    timeZone: zone, day: "2-digit", month: "short", year: "numeric"
  }).format(date);
}
export function dateTimeAt(value: string): string { return `${dateAt(value)}, ${timeAt(value)} IST`; }
