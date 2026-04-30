import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getActivePersona,
  getCalls,
  getLlmProvider,
  getPersonas,
  setActivePersona,
  setLlmProvider,
  type CallListItem,
  type Persona,
} from "../lib/api";

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-green-500/20 text-green-400 border-green-500/30 animate-pulse",
    ended: "bg-slate-700/50 text-slate-400 border-slate-600/30",
    error: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-mono font-medium ${styles[status] ?? styles.error}`}
    >
      {status}
    </span>
  );
}

function formatDateTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Dashboard page ─────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [calls, setCalls] = useState<CallListItem[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [activePersona, setActivePersonaState] = useState<string>("");
  const [savingPersona, setSavingPersona] = useState(false);
  const [personaMsg, setPersonaMsg] = useState<string | null>(null);
  const [llmProvider, setLlmProviderState] = useState<"gemini" | "anthropic">("gemini");
  const [savingLlm, setSavingLlm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    getCalls()
      .then(setCalls)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const id = window.setInterval(() => {
      getCalls().then(setCalls).catch(() => {});
    }, 5000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    getPersonas().then(setPersonas).catch(() => {});
    getActivePersona().then((p) => {
      if (p.persona_name) setActivePersonaState(p.persona_name);
    }).catch(() => {});
    getLlmProvider().then((s) => {
      const p = (s.provider || "gemini").toLowerCase();
      setLlmProviderState(p === "anthropic" ? "anthropic" : "gemini");
    }).catch(() => {});
  }, []);

  const saveActivePersona = async () => {
    if (!activePersona) return;
    setSavingPersona(true);
    setPersonaMsg(null);
    try {
      await setActivePersona(activePersona);
      setPersonaMsg(`Locked "${activePersona}" for future live calls.`);
    } catch (e) {
      setPersonaMsg(`Error: ${(e as Error).message}`);
    } finally {
      setSavingPersona(false);
    }
  };

  const saveLlm = async () => {
    setSavingLlm(true);
    setPersonaMsg(null);
    try {
      await setLlmProvider(llmProvider);
      setPersonaMsg(`LLM set to "${llmProvider}".`);
    } catch (e) {
      setPersonaMsg(`Error: ${(e as Error).message}`);
    } finally {
      setSavingLlm(false);
    }
  };


  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Live Call Monitor</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {calls.length} call{calls.length !== 1 ? "s" : ""} recorded
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={llmProvider}
              onChange={(e) => setLlmProviderState(e.target.value === "anthropic" ? "anthropic" : "gemini")}
              className="bg-navy-950 border border-white/10 rounded px-3 py-2 text-sm text-slate-200"
            >
              <option value="gemini">Gemini</option>
              <option value="anthropic">Claude</option>
            </select>
            <button
              onClick={saveLlm}
              disabled={savingLlm}
              className="px-4 py-2 bg-navy-950 hover:bg-white/5 border border-white/10 rounded-lg text-sm font-medium text-slate-200 disabled:opacity-40"
            >
              {savingLlm ? "Saving..." : "Set LLM"}
            </button>
            <select
              value={activePersona}
              onChange={(e) => setActivePersonaState(e.target.value)}
              className="bg-navy-950 border border-white/10 rounded px-3 py-2 text-sm text-slate-200"
            >
              <option value="" disabled>Select live persona</option>
              {personas.map((p) => (
                <option key={p.id} value={p.name}>{p.name}</option>
              ))}
            </select>
            <button
              onClick={saveActivePersona}
              disabled={savingPersona || !activePersona}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium text-white disabled:opacity-40"
            >
              {savingPersona ? "Saving..." : "Lock Persona"}
            </button>
          </div>
        </div>
        {personaMsg && (
          <div className="text-sm text-slate-300 bg-white/5 border border-white/10 rounded px-3 py-2">
            {personaMsg}
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-12">
            <span className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
            Loading calls…
          </div>
        ) : error ? (
          <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            {error}
          </p>
        ) : calls.length === 0 ? (
          <div className="text-center py-20 border border-dashed border-white/10 rounded-xl">
            <p className="text-slate-500 text-sm mb-4">No calls recorded yet.</p>
            <p className="text-slate-600 text-xs">Place a live call to your Twilio number to begin.</p>
          </div>
        ) : (
          <div className="bg-navy-900 border border-white/10 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs text-slate-500 uppercase tracking-wide font-medium">
                  <th className="px-5 py-3 text-left w-16">ID</th>
                  <th className="px-5 py-3 text-left">Incoming</th>
                  <th className="px-5 py-3 text-left">When</th>
                  <th className="px-5 py-3 text-left">Persona</th>
                  <th className="px-5 py-3 text-right">Highlights</th>
                  <th className="px-5 py-3 text-right">Duration</th>
                  <th className="px-5 py-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {calls.map((c) => (
                  <tr key={c.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/calls/${c.id}`}
                        className="font-mono text-green-400 hover:text-green-300 hover:underline"
                      >
                        #{c.id}
                      </Link>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-slate-300">{c.caller_number || "unknown"}</span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="font-mono text-slate-400">{formatDateTime(c.started_at)}</span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-300">
                      {c.persona_name ?? <span className="text-slate-600">—</span>}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {c.highlight_count > 0 ? (
                        <span className="font-mono text-yellow-400">{c.highlight_count}</span>
                      ) : (
                        <span className="text-slate-600 font-mono">0</span>
                      )}
                    </td>
                    <td className="px-5 py-3.5 text-right font-mono text-slate-400">
                      {c.duration_seconds}s
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <StatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
