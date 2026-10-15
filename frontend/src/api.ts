export const API = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "");
export const WS = API
  ? API.replace(/^http/, "ws")
  : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;

export interface Citation { ref: number; document: string; section: string | null; snippet: string; filename: string; page: number | null }
export interface Msg { id?: number; role: "user" | "assistant"; content: string; modality?: "text" | "voice"; citations?: Citation[] | null }
export interface Appt { id: number; status: string; service: string; city: string; address: string; start_at: string; technician: string; price_inr: number; cancellation_fee_inr: number | null; hold_expires_at: string | null }
export interface Me { id: number; email: string; name: string; is_admin: boolean }
export interface TurnResult { conversation_id: number; reply: string; citations: Citation[]; intent: string; pending: { type: string; appointment_id: number } | null; appointment: Appt | null; handoff: boolean; ticket_id: number | null }
export interface ConvSummary { id: number; channel: string; status: string; created_at: string }

let token: string | null = localStorage.getItem("token");
export const getToken = () => token;
export function setToken(t: string | null) {
  token = t;
  t ? localStorage.setItem("token", t) : localStorage.removeItem("token");
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(API + path, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    const d = j.detail;
    throw new Error(typeof d === "string" ? d : d?.message ?? `Request failed (${res.status})`);
  }
  return res.json();
}
