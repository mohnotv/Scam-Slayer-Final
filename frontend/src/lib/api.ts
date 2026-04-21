/**
 * Typed fetch wrapper for the ScamSlayer backend.
 *
 * All REST endpoints live under /api — Vite's dev proxy forwards /api/* to :8000.
 * WebSocket endpoints (/voice/stream) are handled separately by the browser.
 */

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface CallListItem {
  id: number;
  started_at: string;
  duration_seconds: number;
  persona_name: string | null;
  is_scam: boolean;
  scam_type: string;
  status: string;
  highlight_count: number;
  clip_id: number | null;
}

export interface TranscriptRow {
  id: number;
  speaker: string;
  text: string;
  timestamp_ms: number;
  is_final: boolean;
  confidence: number;
}

export interface HighlightRow {
  id: number;
  start_ms: number;
  end_ms: number;
  reason: string;
  score: number;
  transcript_snippet: string;
}

export interface Clip {
  id: number;
  call_id: number;
  file_path: string;
  duration_seconds: number;
  caption: string;
  hashtags: string[];
  status: string;
}

export interface CallDetail {
  id: number;
  twilio_call_sid: string;
  caller_number: string;
  is_scam: boolean;
  scam_confidence: number;
  scam_type: string;
  status: string;
  duration_seconds: number;
  started_at: string;
  ended_at: string | null;
  persona_name: string | null;
  transcript: TranscriptRow[];
  highlights: HighlightRow[];
  clip_url: string | null;
  clip: Clip | null;
}

export interface SimulateRequest {
  scammer_utterances: string[];
}

export interface SimulateResponse {
  call_id: number;
  persona_name: string;
  is_scam: boolean;
  confidence: number;
  scam_type: string;
  duration_seconds: number;
  transcript: TranscriptRow[];
  highlights: HighlightRow[];
  clip: Clip | null;
}

export interface Persona {
  id: number;
  name: string;
  backstory: string;
  speech_tics: string;
  elevenlabs_voice_id: string;
  scam_types: string[];
}

// ── Calls ──────────────────────────────────────────────────────────────────

export const getCalls = () => request<CallListItem[]>("/calls");
export const getCall = (id: number) => request<CallDetail>(`/calls/${id}`);
export const getTranscript = (id: number) =>
  request<TranscriptRow[]>(`/calls/${id}/transcript`);
export const getHighlights = (id: number) =>
  request<HighlightRow[]>(`/calls/${id}/highlights`);
export const simulateCall = (body: SimulateRequest) =>
  request<SimulateResponse>("/calls/simulate", {
    method: "POST",
    body: JSON.stringify(body),
  });

/** URL that streams the .mp4 file for a call. */
export const clipUrl = (callId: number) => `/api/calls/${callId}/clip`;

// ── Personas ───────────────────────────────────────────────────────────────

export const getPersonas = () => request<Persona[]>("/personas");
export const getPersona = (id: number) => request<Persona>(`/personas/${id}`);
export const createPersona = (body: Omit<Persona, "id">) =>
  request<Persona>("/personas", { method: "POST", body: JSON.stringify(body) });
export const updatePersona = (id: number, body: Omit<Persona, "id">) =>
  request<Persona>(`/personas/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
export const deletePersona = (id: number) =>
  fetch(`${BASE}/personas/${id}`, { method: "DELETE" });

// ── Clips (legacy endpoints still available) ───────────────────────────────

export const getClips = () => request<Clip[]>("/clips");
export const getClip = (id: number) => request<Clip>(`/clips/${id}`);
export const generateClip = (callId: number) =>
  request<Clip>(`/clips/${callId}/generate`, { method: "POST" });
