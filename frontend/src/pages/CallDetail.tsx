import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getCall,
  generateClip,
  clipUrl,
  type CallDetail as CallDetailType,
} from "../lib/api";

function ms(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export default function CallDetail() {
  const { id } = useParams<{ id: string }>();
  const callId = Number(id);

  const [call, setCall] = useState<CallDetailType | null>(null);
  const [generating, setGenerating] = useState(false);
  const [clipMsg, setClipMsg] = useState<string | null>(null);

  useEffect(() => {
    getCall(callId).then(setCall);
  }, [callId]);

  const handleGenerateClip = async () => {
    setGenerating(true);
    try {
      const clip = await generateClip(callId);
      setClipMsg(`Clip #${clip.id} generated (status: ${clip.status})`);
      // Refresh call to pick up new clip_url
      getCall(callId).then(setCall);
    } catch (e) {
      setClipMsg(`Error: ${(e as Error).message}`);
    } finally {
      setGenerating(false);
    }
  };

  if (!call) return <p className="text-gray-400">Loading…</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        <Link to="/" className="text-gray-500 hover:text-gray-300">← Back</Link>
        <h1 className="text-2xl font-bold">Call #{call.id}</h1>
        <span className="text-sm text-gray-400">
          {call.scam_type} · {(call.scam_confidence * 100).toFixed(0)}% confidence ·{" "}
          {call.duration_seconds}s · Persona: {call.persona_name ?? "none"}
        </span>
      </div>

      {/* Clip */}
      {call.clip_url && (
        <section>
          <h2 className="text-lg font-semibold mb-3">Clip</h2>
          <video
            src={call.clip_url}
            controls
            className="rounded-lg border border-gray-800 max-h-96"
          />
          <a
            href={clipUrl(call.id)}
            download
            className="mt-2 inline-block text-sm text-green-400 hover:underline"
          >
            Download .mp4
          </a>
          {call.clip && (
            <p className="mt-1 text-xs text-gray-500">{call.clip.caption}</p>
          )}
        </section>
      )}

      {/* Highlights */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Highlights</h2>
          {!call.clip_url && (
            <button
              onClick={handleGenerateClip}
              disabled={generating}
              className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm disabled:opacity-50"
            >
              {generating ? "Generating…" : "Generate Clip"}
            </button>
          )}
        </div>
        {clipMsg && <p className="text-sm text-green-400 mb-2">{clipMsg}</p>}
        {call.highlights.length === 0 ? (
          <p className="text-gray-500 text-sm">No highlights yet.</p>
        ) : (
          <div className="space-y-2">
            {call.highlights.map((h) => (
              <div key={h.id} className="bg-gray-900 rounded-lg p-4 border border-gray-800">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-mono text-xs text-gray-400">
                    {ms(h.start_ms)} – {ms(h.end_ms)}
                  </span>
                  <span className="text-xs bg-yellow-900/50 text-yellow-300 px-2 py-0.5 rounded">
                    score {(h.score * 100).toFixed(0)}
                  </span>
                  <span className="text-xs text-gray-400">{h.reason}</span>
                </div>
                <p className="text-sm text-gray-300 italic">"{h.transcript_snippet}"</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Transcript */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Transcript</h2>
        <div className="space-y-1 font-mono text-sm max-h-96 overflow-y-auto pr-2">
          {call.transcript.map((row) => (
            <div key={row.id} className="flex gap-3">
              <span className="text-gray-500 w-12 shrink-0 text-right">{ms(row.timestamp_ms)}</span>
              <span
                className={
                  row.speaker === "persona" ? "text-green-300" : "text-orange-300"
                }
              >
                [{row.speaker}]
              </span>
              <span className="text-gray-200">{row.text}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
