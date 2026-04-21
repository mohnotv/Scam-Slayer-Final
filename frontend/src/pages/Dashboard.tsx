import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCalls, type CallListItem } from "../lib/api";

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "active"
      ? "bg-green-500 animate-pulse"
      : status === "ended"
        ? "bg-gray-500"
        : "bg-red-500";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold text-white ${color}`}>
      {status}
    </span>
  );
}

function ScamBadge({ isScam }: { isScam: boolean }) {
  return isScam ? (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-red-900/60 text-red-300">
      SCAM
    </span>
  ) : (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-semibold bg-gray-800 text-gray-400">
      clean
    </span>
  );
}

export default function Dashboard() {
  const [calls, setCalls] = useState<CallListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCalls()
      .then(setCalls)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400">Loading calls…</p>;
  if (error) return <p className="text-red-400">Error: {error}</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Live Call Monitor</h1>
      {calls.length === 0 && (
        <p className="text-gray-500">No calls yet. Point your Twilio number at /voice/incoming.</p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-gray-400 text-left">
              <th className="pb-2 pr-4">ID</th>
              <th className="pb-2 pr-4">Scam</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4">Persona</th>
              <th className="pb-2 pr-4">Highlights</th>
              <th className="pb-2 pr-4">Duration</th>
              <th className="pb-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id} className="border-b border-gray-800/50 hover:bg-gray-900/50">
                <td className="py-2 pr-4">
                  <Link to={`/calls/${c.id}`} className="text-green-400 hover:underline">
                    #{c.id}
                  </Link>
                </td>
                <td className="py-2 pr-4">
                  <ScamBadge isScam={c.is_scam} />
                </td>
                <td className="py-2 pr-4">{c.scam_type}</td>
                <td className="py-2 pr-4">{c.persona_name ?? "—"}</td>
                <td className="py-2 pr-4">{c.highlight_count}</td>
                <td className="py-2 pr-4">{c.duration_seconds}s</td>
                <td className="py-2">
                  <StatusBadge status={c.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
