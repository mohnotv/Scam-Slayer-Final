/**
 * Typed fetch wrapper for the ScamSlayer backend.
 * Base URL is empty — Vite's proxy forwards /calls, /personas, /clips to :8000.
 */

const BASE = "";

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

export interface Call {
  id: number;
  twilio_call_sid: string;
  caller_number: string;
  is_scam: boolean;
  scam_confidence: number;
  scam_type: string;
  status: string;
  duration_seconds: number;
  persona_name: string | null;
}

export interface TranscriptRow {
  id: number;
  speaker: string;
  text: string;
  timestamp_ms: number;
  is_final: boolean;
}

export interface HighlightRow {
  id: number;
  start_ms: number;
  end_ms: number;
  reason: string;
  score: number;
  transcript_snippet: string;
}

export interface Persona {
  id: number;
  name: string;
  backstory: string;
  speech_tics: string;
  elevenlabs_voice_id: string;
  scam_types: string[];
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

// ── Calls ──────────────────────────────────────────────────────────────────

export const getCalls = () => request<Call[]>("/calls");
export const getCall = (id: number) => request<Call>(`/calls/${id}`);
export const getTranscript = (id: number) => request<TranscriptRow[]>(`/calls/${id}/transcript`);
export const getHighlights = (id: number) => request<HighlightRow[]>(`/calls/${id}/highlights`);

// ── Personas ───────────────────────────────────────────────────────────────

export const getPersonas = () => request<Persona[]>("/personas");
export const getPersona = (id: number) => request<Persona>(`/personas/${id}`);
export const createPersona = (body: Omit<Persona, "id">) =>
  request<Persona>("/personas", { method: "POST", body: JSON.stringify(body) });
export const updatePersona = (id: number, body: Omit<Persona, "id">) =>
  request<Persona>(`/personas/${id}`, { method: "PUT", body: JSON.stringify(body) });
export const deletePersona = (id: number) =>
  fetch(`/personas/${id}`, { method: "DELETE" });

// ── Clips ──────────────────────────────────────────────────────────────────

export const getClips = () => request<Clip[]>("/clips");
export const getClip = (id: number) => request<Clip>(`/clips/${id}`);
export const generateClip = (callId: number) =>
  request<Clip>(`/clips/${callId}/generate`, { method: "POST" });
