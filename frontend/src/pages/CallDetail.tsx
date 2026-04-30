import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  coachChat,
  coachChatForSegment,
  getCall,
  generateClip,
  clipUrl,
  type CallDetail as CallDetailType,
  type HighlightRow,
} from "../lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

// ── Highlights sidebar ─────────────────────────────────────────────────────────

function HighlightCard({ h, rank }: { h: HighlightRow; rank: number }) {
  const pct = Math.round(h.score * 100);
  const barColor = pct >= 90 ? "bg-red-500" : pct >= 75 ? "bg-yellow-500" : "bg-green-500";

  return (
    <div className="bg-navy-900 border border-white/10 rounded-lg p-4 space-y-2 hover:border-white/20 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-slate-500">
          {fmtMs(h.start_ms)} – {fmtMs(h.end_ms)}
        </span>
        <span className="text-xs font-mono text-slate-400">#{rank}</span>
      </div>

      {/* Virality score bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
          <div className={`h-full ${barColor} rounded-full`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-xs font-mono font-medium ${pct >= 90 ? "text-red-400" : pct >= 75 ? "text-yellow-400" : "text-green-400"}`}>
          {pct}
        </span>
      </div>

      <p className="text-xs text-slate-400 italic leading-relaxed">
        "{h.transcript_snippet}"
      </p>
      <p className="text-xs text-slate-600">{h.reason}</p>
    </div>
  );
}

// ── Chat bubble ────────────────────────────────────────────────────────────────

function Bubble({
  speaker,
  text,
  ts,
  onWhy,
}: {
  speaker: string;
  text: string;
  ts: number;
  onWhy?: () => void;
}) {
  const isPersona = speaker === "persona";
  return (
    <div className={`flex gap-3 ${isPersona ? "flex-row" : "flex-row-reverse"}`}>
      {/* Avatar */}
      <div
        className={`w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-xs font-bold mt-0.5 ${
          isPersona
            ? "bg-green-500/20 text-green-400 border border-green-500/30"
            : "bg-red-500/20 text-red-400 border border-red-500/30"
        }`}
      >
        {isPersona ? "B" : "S"}
      </div>

      <div className={`flex flex-col gap-1 max-w-[75%] ${isPersona ? "items-start" : "items-end"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isPersona
              ? "bg-green-500/10 border border-green-500/20 text-green-100 rounded-tl-sm"
              : "bg-red-500/10 border border-red-500/20 text-red-100 rounded-tr-sm"
          }`}
        >
          {text}
        </div>
        <div className={`flex items-center gap-2 px-1 ${isPersona ? "justify-start" : "justify-end"}`}>
          <span className="font-mono text-[10px] text-slate-600">{fmtMs(ts)}</span>
          {isPersona && onWhy && (
            <button
              onClick={onWhy}
              className="text-[10px] text-slate-400 hover:text-slate-200 underline underline-offset-2"
              type="button"
            >
              Why?
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function CallDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const callId = Number(id);

  const [call, setCall] = useState<CallDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [clipMsg, setClipMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"conversation" | "transcript" | "coach">("conversation");
  const [coachInput, setCoachInput] = useState("");
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachHistory, setCoachHistory] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);

  const load = () =>
    getCall(callId)
      .then(setCall)
      .finally(() => setLoading(false));

  useEffect(() => { load(); }, [callId]);
  useEffect(() => {
    if (!call || call.status !== "active") return;
    const id = window.setInterval(() => {
      getCall(callId).then(setCall).catch(() => {});
    }, 3000);
    return () => window.clearInterval(id);
  }, [call, callId]);

  const handleGenerateClip = async () => {
    setGenerating(true);
    setClipMsg(null);
    try {
      const clip = await generateClip(callId);
      setClipMsg(`Clip #${clip.id} generated (${clip.status})`);
      await load(); // refresh to pick up clip_url
    } catch (e) {
      setClipMsg(`Error: ${(e as Error).message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleAskCoach = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = coachInput.trim();
    if (!q) return;
    setCoachInput("");
    setCoachHistory((h) => [...h, { role: "user", text: q }]);
    setCoachLoading(true);
    try {
      const out = await coachChat(callId, q);
      setCoachHistory((h) => [...h, { role: "assistant", text: out.answer }]);
    } catch (err) {
      setCoachHistory((h) => [...h, { role: "assistant", text: `Error: ${(err as Error).message}` }]);
    } finally {
      setCoachLoading(false);
    }
  };

  const askCoachAboutSegment = async (segmentId: number, text: string) => {
    const q = `Why did you say: "${text}"?`;
    setActiveTab("coach");
    setCoachHistory((h) => [...h, { role: "user", text: q }]);
    setCoachLoading(true);
    try {
      const out = await coachChatForSegment(callId, segmentId, q);
      setCoachHistory((h) => [...h, { role: "assistant", text: out.answer }]);
    } catch (err) {
      setCoachHistory((h) => [...h, { role: "assistant", text: `Error: ${(err as Error).message}` }]);
    } finally {
      setCoachLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm py-20">
        <span className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
        Loading call…
      </div>
    );
  }

  if (!call) {
    return (
      <div className="text-center py-20">
        <p className="text-slate-500 mb-4">Call not found.</p>
        <button onClick={() => navigate("/")} className="text-green-400 hover:underline text-sm">
          ← Back to dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-slate-500 hover:text-slate-300 text-sm transition-colors">
            ← Back
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-white flex items-center gap-2">
              Call{" "}
              <span className="font-mono text-green-400">#{call.id}</span>
            </h1>
            <p className="text-xs text-slate-500 font-mono mt-0.5">
              from {call.caller_number || "unknown"} · {call.duration_seconds}s · {call.persona_name ?? "no persona"}
            </p>
            {call.recording_available && (
              <div className="mt-3 max-w-md">
                <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Call recording</p>
                <audio
                  controls
                  className="w-full h-9"
                  src={`/api/calls/${call.id}/recording`}
                  preload="metadata"
                >
                  Your browser does not support audio playback.
                </audio>
                {call.recording_duration_seconds > 0 && (
                  <p className="text-[10px] text-slate-600 mt-1 font-mono">
                    Twilio recording · {call.recording_duration_seconds}s
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {!call.clip_url && (
          <button
            onClick={handleGenerateClip}
            disabled={generating}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium text-white disabled:opacity-40 transition-colors"
          >
            {generating && (
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {generating ? "Generating…" : "Generate Clip"}
          </button>
        )}
      </div>

      {clipMsg && (
        <p className="text-sm text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-4 py-2">
          {clipMsg}
        </p>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={() => setActiveTab("conversation")}
          className={`px-3 py-1.5 rounded text-sm border ${
            activeTab === "conversation"
              ? "bg-green-600/20 text-green-300 border-green-500/40"
              : "bg-navy-900 text-slate-400 border-white/10"
          }`}
        >
          Conversation
        </button>
        <button
          onClick={() => setActiveTab("transcript")}
          className={`px-3 py-1.5 rounded text-sm border ${
            activeTab === "transcript"
              ? "bg-green-600/20 text-green-300 border-green-500/40"
              : "bg-navy-900 text-slate-400 border-white/10"
          }`}
        >
          Transcript
        </button>
        <button
          onClick={() => setActiveTab("coach")}
          className={`px-3 py-1.5 rounded text-sm border ${
            activeTab === "coach"
              ? "bg-green-600/20 text-green-300 border-green-500/40"
              : "bg-navy-900 text-slate-400 border-white/10"
          }`}
        >
          Coach Chat
        </button>
      </div>

      {/* Two-column layout: transcript | sidebar */}
      <div className="flex gap-6 items-start">

        {/* ── Transcript (chat bubbles) ── */}
        <div className="flex-1 min-w-0 bg-navy-900 border border-white/10 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/10 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-300">
              {activeTab === "conversation" ? "Conversation" : activeTab === "transcript" ? "Transcript" : "Coach Chat"}
            </span>
            <span className="text-xs font-mono text-slate-500">
              {activeTab === "coach" ? `${coachHistory.length} messages` : `${call.transcript.length} segments`}
            </span>
          </div>
          <div className="p-5 space-y-4 max-h-[60vh] overflow-y-auto">
            {activeTab !== "coach" && call.transcript.length === 0 ? (
              <p className="text-slate-600 text-sm text-center py-8">No transcript yet.</p>
            ) : activeTab === "coach" ? (
              <>
                <div className="space-y-2">
                  {coachHistory.length === 0 ? (
                    <p className="text-slate-500 text-sm">
                      Ask things like: "Why did the agent ask that question?" or "Why did it switch tone?"
                    </p>
                  ) : (
                    coachHistory.map((m, i) => (
                      <div
                        key={i}
                        className={`rounded px-3 py-2 text-sm ${
                          m.role === "user"
                            ? "bg-white/5 text-slate-200"
                            : "bg-green-500/10 border border-green-500/20 text-green-100"
                        }`}
                      >
                        {m.text}
                      </div>
                    ))
                  )}
                </div>
                <form onSubmit={handleAskCoach} className="pt-2 flex gap-2">
                  <input
                    value={coachInput}
                    onChange={(e) => setCoachInput(e.target.value)}
                    placeholder="Ask why the AI responded a certain way..."
                    className="flex-1 bg-navy-950 border border-white/10 rounded px-3 py-2 text-sm text-slate-200"
                  />
                  <button
                    type="submit"
                    disabled={coachLoading || !coachInput.trim()}
                    className="px-3 py-2 rounded text-sm bg-green-600 hover:bg-green-500 text-white disabled:opacity-40"
                  >
                    {coachLoading ? "Asking..." : "Ask"}
                  </button>
                </form>
              </>
            ) : (
              activeTab === "conversation" ? (
                call.transcript.map((row) => (
                  <Bubble
                    key={row.id}
                    speaker={row.speaker}
                    text={row.text}
                    ts={row.timestamp_ms}
                    onWhy={
                      row.speaker === "persona"
                        ? () => askCoachAboutSegment(row.id, row.text)
                        : undefined
                    }
                  />
                ))
              ) : (
                <div className="space-y-2">
                  {call.transcript.map((row) => (
                    <div
                      key={row.id}
                      className="grid grid-cols-[90px_90px_1fr] gap-3 text-xs border border-white/5 rounded px-3 py-2"
                    >
                      <span className="font-mono text-slate-500">{fmtMs(row.timestamp_ms)}</span>
                      <span className="uppercase tracking-wide text-slate-400">{row.speaker}</span>
                      <span className="text-slate-200">{row.text}</span>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>

        {/* ── Sidebar: highlights + clip ── */}
        <div className="w-72 shrink-0 space-y-4">

          {/* Clip player */}
          {call.clip_url ? (
            <div className="bg-navy-900 border border-white/10 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
                <span className="text-sm font-medium text-slate-300">Clip</span>
                <a
                  href={clipUrl(call.id)}
                  download
                  className="text-xs text-green-400 hover:text-green-300 hover:underline"
                >
                  Download .mp4
                </a>
              </div>
              <video
                src={call.clip_url}
                controls
                className="w-full aspect-[9/16] object-cover bg-black"
              />
              {call.clip && (
                <div className="p-4 space-y-2">
                  <p className="text-xs text-slate-300 leading-relaxed">{call.clip.caption}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-navy-900 border border-dashed border-white/10 rounded-xl p-6 text-center">
              <p className="text-slate-600 text-xs">No clip generated yet</p>
            </div>
          )}

          {/* Highlights */}
          <div className="bg-navy-900 border border-white/10 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
              <span className="text-sm font-medium text-slate-300">Highlights</span>
              <span className="text-xs font-mono text-yellow-400">
                {call.highlights.length} found
              </span>
            </div>
            <div className="p-3 space-y-2 max-h-80 overflow-y-auto">
              {call.highlights.length === 0 ? (
                <p className="text-slate-600 text-xs text-center py-4">No highlights mined.</p>
              ) : (
                call.highlights.map((h, i) => (
                  <HighlightCard key={h.id} h={h} rank={i + 1} />
                ))
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
