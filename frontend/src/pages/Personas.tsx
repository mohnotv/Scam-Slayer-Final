import { useEffect, useState } from "react";
import { getPersonas, getVoices, updatePersona, type Persona, type Voice } from "../lib/api";

function PersonaCard({
  p,
  voices,
  onUpdated,
}: {
  p: Persona;
  voices: Voice[];
  onUpdated: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [voiceId, setVoiceId] = useState(p.elevenlabs_voice_id || "");
  const [msg, setMsg] = useState<string | null>(null);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await updatePersona(p.id, {
        name: p.name,
        backstory: p.backstory,
        speech_tics: p.speech_tics,
        elevenlabs_voice_id: voiceId,
        scam_types: p.scam_types,
      });
      setMsg("Saved.");
      onUpdated();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-navy-900 border border-white/10 rounded-xl p-5 space-y-3 hover:border-white/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-green-400">{p.name}</h3>
          <p className="text-xs font-mono text-slate-500 mt-0.5">
            Voice ID: {p.elevenlabs_voice_id || "—"}
          </p>
        </div>
      </div>

      <p className="text-sm text-slate-300 leading-relaxed line-clamp-3">{p.backstory}</p>

      <div className="border-t border-white/5 pt-3 space-y-2">
        <div className="flex items-center gap-2">
          <select
            value={voiceId}
            onChange={(e) => setVoiceId(e.target.value)}
            className="flex-1 bg-navy-950 border border-white/10 rounded px-3 py-2 text-sm text-slate-200"
          >
            <option value="">(no voice selected)</option>
            {voices.map((v) => (
              <option key={v.voice_id} value={v.voice_id}>
                {v.name}
              </option>
            ))}
          </select>
          <button
            onClick={save}
            disabled={saving}
            className="px-3 py-2 rounded text-sm bg-green-600 hover:bg-green-500 text-white disabled:opacity-40"
          >
            {saving ? "Saving..." : "Save voice"}
          </button>
        </div>
        {msg && <p className="text-xs text-slate-500">{msg}</p>}
      </div>

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
  const [voices, setVoices] = useState<Voice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    getPersonas()
      .then(setPersonas)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
    getVoices().then(setVoices).catch(() => {});
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
            <PersonaCard key={p.id} p={p} voices={voices} onUpdated={load} />
          ))}
        </div>
      )}
    </div>
  );
}
