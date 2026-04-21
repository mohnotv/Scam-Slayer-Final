import { useEffect, useState } from "react";
import { getPersonas, type Persona } from "../lib/api";

function PersonaCard({ p }: { p: Persona }) {
  return (
    <div className="bg-navy-900 border border-white/10 rounded-xl p-5 space-y-3 hover:border-white/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-green-400">{p.name}</h3>
          <p className="text-xs font-mono text-slate-500 mt-0.5">{p.elevenlabs_voice_id}</p>
        </div>
        <div className="flex flex-wrap gap-1 justify-end">
          {p.scam_types.map((t) => (
            <span
              key={t}
              className="text-xs bg-red-500/10 border border-red-500/20 text-red-400 px-2 py-0.5 rounded font-mono"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      <p className="text-sm text-slate-300 leading-relaxed line-clamp-3">{p.backstory}</p>

      {p.speech_tics && (
        <div className="text-xs text-slate-500 border-t border-white/5 pt-3">
          <span className="text-slate-600 uppercase tracking-wide text-[10px] font-medium mr-2">
            Tics
          </span>
          {p.speech_tics}
        </div>
      )}
    </div>
  );
}

export default function Personas() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPersonas()
      .then(setPersonas)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Personas</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          AI characters deployed to engage scammers.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-500 text-sm py-12">
          <span className="w-4 h-4 border-2 border-slate-600 border-t-slate-400 rounded-full animate-spin" />
          Loading personas…
        </div>
      ) : error ? (
        <p className="text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          {error}
        </p>
      ) : personas.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-white/10 rounded-xl">
          <p className="text-slate-500 text-sm">
            No personas yet. Run a simulation to create Grandma Betty.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {personas.map((p) => (
            <PersonaCard key={p.id} p={p} />
          ))}
        </div>
      )}
    </div>
  );
}
