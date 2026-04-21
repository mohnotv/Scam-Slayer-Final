import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getCall,
  getTranscript,
  getHighlights,
  generateClip,
  type Call,
  type TranscriptRow,
  type HighlightRow,
} from "../lib/api";

function ms(ms: number) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

export default function CallDetail() {
  const { id } = useParams<{ id: string }>();
  const callId = Number(id);

  const [call, setCall] = useState<Call | null>(null);
  const [transcript, setTranscript] = useState<TranscriptRow[]>([]);
  const [highlights, setHighlights] = useState<HighlightRow[]>([]);
  const [generating, setGenerating] = useState(false);
  const [clipMsg, setClipMsg] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getCall(callId), getTranscript(callId), getHighlights(callId)]).then(
      ([c, t, h]) => {
        setCall(c);
        setTranscript(t);
        setHighlights(h);
      }
    );
  }, [callId]);

  const handleGenerateClip = async () => {
    setGenerating(true);
    try {
      const clip = await generateClip(callId);
      setClipMsg(`Clip #${clip.id} queued (status: ${clip.status})`);
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

      {/* Highlights */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Highlights</h2>
          <button
            onClick={handleGenerateClip}
            disabled={generating}
            className="px-3 py-1 bg-green-600 hover:bg-green-700 rounded text-sm disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate Clip"}
          </button>
        </div>
        {clipMsg && <p className="text-sm text-green-400 mb-2">{clipMsg}</p>}
        {highlights.length === 0 ? (
          <p className="text-gray-500 text-sm">No highlights yet.</p>
        ) : (
          <div className="space-y-2">
            {highlights.map((h) => (
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
          {transcript.map((row) => (
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
