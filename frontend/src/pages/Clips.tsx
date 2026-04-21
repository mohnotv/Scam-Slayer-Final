import { useEffect, useState } from "react";
import { getClips, type Clip } from "../lib/api";

function ClipCard({ clip }: { clip: Clip }) {
  const isReady = clip.status === "ready";

  return (
    <div className="bg-gray-900 rounded-lg p-5 border border-gray-800 space-y-3">
      <div className="flex justify-between items-start">
        <div>
          <span className="font-semibold text-green-300">Clip #{clip.id}</span>
          <span className="ml-3 text-xs text-gray-500">call #{clip.call_id}</span>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${
            isReady ? "bg-green-900/50 text-green-300" : "bg-yellow-900/50 text-yellow-300"
          }`}
        >
          {clip.status}
        </span>
      </div>

      <p className="text-sm text-gray-200 whitespace-pre-line">{clip.caption}</p>

      <div className="flex flex-wrap gap-1">
        {clip.hashtags.map((t) => (
          <span key={t} className="text-xs text-blue-400">{t}</span>
        ))}
      </div>

      <div className="flex gap-3 items-center">
        <span className="text-xs text-gray-500">{clip.duration_seconds.toFixed(1)}s</span>
        {isReady && (
          <a
            href={`/clips/${clip.id}/download`}
            className="text-xs px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded"
          >
            Download .mp4
          </a>
        )}
      </div>
    </div>
  );
}

export default function Clips() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getClips()
      .then(setClips)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400">Loading clips…</p>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Clips</h1>
      {clips.length === 0 ? (
        <p className="text-gray-500">
          No clips yet. Open a call detail page and click "Generate Clip".
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {clips.map((c) => <ClipCard key={c.id} clip={c} />)}
        </div>
      )}
    </div>
  );
}
