import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getClips, clipUrl, type Clip } from "../lib/api";

function ClipCard({ clip }: { clip: Clip }) {
  const isReady = clip.status === "ready";
  const isStub = clip.status === "stub";

  return (
    <div className="bg-navy-900 border border-white/10 rounded-xl overflow-hidden hover:border-white/20 transition-colors">
      {/* Video thumbnail or placeholder */}
      {isReady ? (
        <video
          src={clipUrl(clip.call_id)}
          className="w-full aspect-video object-cover bg-black"
          preload="metadata"
        />
      ) : (
        <div className="w-full aspect-video bg-navy-950 flex items-center justify-center">
          <span
            className={`text-xs font-mono px-2 py-1 rounded ${
              isStub
                ? "bg-yellow-900/30 text-yellow-500 border border-yellow-500/20"
                : "bg-slate-800 text-slate-500"
            }`}
          >
            {clip.status}
          </span>
        </div>
      )}

      <div className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <Link
              to={`/calls/${clip.call_id}`}
              className="text-sm font-medium text-green-400 hover:text-green-300 hover:underline"
            >
              Call #{clip.call_id}
            </Link>
            <span className="text-xs text-slate-600 font-mono ml-2">clip #{clip.id}</span>
          </div>
          <span className="text-xs font-mono text-slate-500">{clip.duration_seconds.toFixed(1)}s</span>
        </div>

        {clip.caption && (
          <p className="text-xs text-slate-300 leading-relaxed line-clamp-3">{clip.caption}</p>
        )}

        {isReady && (
          <a
            href={clipUrl(clip.call_id)}
            download={`scamslayer_clip_${clip.id}.mp4`}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 bg-white/5 hover:bg-white/10 rounded px-3 py-1.5 transition-colors"
          >
            ↓ Download .mp4
          </a>
        )}
      </div>
    </div>
  );
}

export default function Clips() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getClips()
      .then(setClips)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Clips</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Auto-generated short-form video highlights.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12">
          <span className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
          Loading clips…
        </div>
      ) : error ? (
        <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          {error}
        </p>
      ) : clips.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-white/10 rounded-xl">
          <p className="text-slate-500 text-sm">
            No clips yet. Open a call detail page and click "Generate Clip".
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {clips.map((c) => (
            <ClipCard key={c.id} clip={c} />
          ))}
        </div>
      )}
    </div>
  );
}
