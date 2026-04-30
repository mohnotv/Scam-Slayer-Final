import { useEffect, useState } from "react";
import { getChecks, type ChecksOut, type CheckResult } from "../lib/api";

function Pill({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-mono font-medium ${
        ok
          ? "bg-green-500/20 text-green-300 border-green-500/30"
          : "bg-red-500/20 text-red-300 border-red-500/30"
      }`}
    >
      {ok ? "ok" : "fail"}
    </span>
  );
}

function Row({ name, r }: { name: string; r: CheckResult }) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-white/5">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-slate-200 font-medium">{name}</span>
          <Pill ok={r.ok} />
          <span className="text-xs font-mono text-slate-500">{r.latency_ms}ms</span>
        </div>
        {r.detail && (
          <p className={`text-xs font-mono mt-1 ${r.ok ? "text-slate-500" : "text-red-300"}`}>
            {r.detail}
          </p>
        )}
      </div>
    </div>
  );
}

export default function Checks() {
  const [data, setData] = useState<ChecksOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const out = await getChecks();
      setData(out);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-white">Checks</h1>
          <p className="text-sm text-slate-500 mt-0.5">Verify external services used by ScamSlayer.</p>
        </div>
        <button
          onClick={load}
          className="px-3 py-2 rounded text-sm bg-navy-950 hover:bg-white/5 border border-white/10 text-slate-200"
        >
          Re-run checks
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12">
          <span className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
          Running checks…
        </div>
      ) : error ? (
        <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          {error}
        </p>
      ) : !data ? (
        <p className="text-slate-500 text-sm">No data.</p>
      ) : (
        <div className="bg-navy-900 border border-white/10 rounded-xl p-5">
          <Row name="Gemini API" r={data.gemini} />
          <Row name="Anthropic API" r={data.anthropic} />
          <Row name="ElevenLabs API" r={data.elevenlabs} />
          <Row name="Twilio API" r={data.twilio} />
        </div>
      )}
    </div>
  );
}

