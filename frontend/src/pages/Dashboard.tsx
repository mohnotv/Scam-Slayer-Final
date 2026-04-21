import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getCalls, simulateCall, type CallListItem } from "../lib/api";

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

function ScamBadge({ isScam, type }: { isScam: boolean; type: string }) {
  if (!isScam) {
    return <span className="text-slate-500 text-xs">—</span>;
  }
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className="inline-flex items-center gap-1 text-xs font-medium text-red-400">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
        SCAM
      </span>
      <span className="text-xs text-slate-500 font-mono">{type}</span>
    </span>
  );
}

// ── Simulate dialog ────────────────────────────────────────────────────────────

const PLACEHOLDER = `Hello, this is the IRS. You owe $3,000 in back taxes.
If you don't pay within the hour you will be arrested.
We need your Social Security number to process the payment.`;

function SimulateDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [text, setText] = useState(PLACEHOLDER);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Close on backdrop click
  const handleBackdrop = (e: React.MouseEvent) => {
    if (e.target === dialogRef.current) onClose();
  };

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const utterances = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (utterances.length < 1) return;
    setLoading(true);
    setError(null);
    try {
      const result = await simulateCall({ scammer_utterances: utterances });
      navigate(`/calls/${result.call_id}`);
    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  };

  return (
    <div
      ref={dialogRef}
      onClick={handleBackdrop}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
    >
      <div className="bg-navy-900 border border-white/10 rounded-xl w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <div>
            <h2 className="font-semibold text-white">Simulate a Scam Call</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Enter scammer lines (one per line). Betty responds to each.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 text-xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium uppercase tracking-wide">
              Scammer utterances
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={6}
              className="w-full bg-navy-950 border border-white/10 rounded-lg px-4 py-3 text-sm font-mono text-slate-200 focus:outline-none focus:border-green-500/50 focus:ring-1 focus:ring-green-500/20 resize-none placeholder:text-slate-600"
              placeholder="One line per utterance…"
            />
            <p className="text-xs text-slate-600 mt-1">
              {utterances.length} utterance{utterances.length !== 1 ? "s" : ""} detected
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded text-sm text-slate-400 hover:text-slate-200 hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || utterances.length === 0}
              className="px-5 py-2 bg-green-600 hover:bg-green-500 rounded text-sm font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading && (
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              {loading ? "Running pipeline…" : "Run Simulation"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Dashboard page ─────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [calls, setCalls] = useState<CallListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDialog, setShowDialog] = useState(false);

  const load = () =>
    getCalls()
      .then(setCalls)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, []);

  return (
    <>
      {showDialog && <SimulateDialog onClose={() => setShowDialog(false)} />}

      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white">Live Call Monitor</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {calls.length} call{calls.length !== 1 ? "s" : ""} recorded
            </p>
          </div>
          <button
            onClick={() => setShowDialog(true)}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium text-white transition-colors shadow-lg shadow-green-900/30"
          >
            <span className="text-base leading-none">+</span>
            Simulate New Call
          </button>
        </div>

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
            <button
              onClick={() => setShowDialog(true)}
              className="text-green-400 hover:text-green-300 text-sm underline underline-offset-2"
            >
              Run your first simulation →
            </button>
          </div>
        ) : (
          <div className="bg-navy-900 border border-white/10 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs text-slate-500 uppercase tracking-wide font-medium">
                  <th className="px-5 py-3 text-left w-16">ID</th>
                  <th className="px-5 py-3 text-left">Scam</th>
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
                      <ScamBadge isScam={c.is_scam} type={c.scam_type} />
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
