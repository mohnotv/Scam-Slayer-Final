import { useEffect, useState } from "react";
import { getPersonas, createPersona, deletePersona, type Persona } from "../lib/api";

const EMPTY: Omit<Persona, "id"> = {
  name: "",
  backstory: "",
  speech_tics: "",
  elevenlabs_voice_id: "",
  scam_types: [],
};

export default function Personas() {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [form, setForm] = useState<Omit<Persona, "id">>(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = () => getPersonas().then(setPersonas);
  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await createPersona({
        ...form,
        scam_types: form.scam_types,
      });
      setForm(EMPTY);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    await deletePersona(id);
    await load();
  };

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Personas</h1>

      {/* Persona list */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {personas.map((p) => (
          <div key={p.id} className="bg-gray-900 rounded-lg p-4 border border-gray-800">
            <div className="flex justify-between items-start mb-2">
              <h3 className="font-semibold text-green-300">{p.name}</h3>
              <button
                onClick={() => handleDelete(p.id)}
                className="text-xs text-gray-500 hover:text-red-400"
              >
                Delete
              </button>
            </div>
            <p className="text-sm text-gray-300 mb-2 line-clamp-3">{p.backstory}</p>
            <div className="flex flex-wrap gap-1">
              {p.scam_types.map((t) => (
                <span key={t} className="text-xs bg-gray-800 px-2 py-0.5 rounded text-gray-400">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Create form */}
      <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
        <h2 className="text-lg font-semibold mb-4">New Persona</h2>
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Name</label>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Backstory</label>
            <textarea
              required
              rows={4}
              value={form.backstory}
              onChange={(e) => setForm({ ...form, backstory: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Speech tics</label>
            <input
              value={form.speech_tics}
              onChange={(e) => setForm({ ...form, speech_tics: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">ElevenLabs Voice ID</label>
            <input
              value={form.elevenlabs_voice_id}
              onChange={(e) => setForm({ ...form, elevenlabs_voice_id: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm font-mono"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Scam types (comma-separated)
            </label>
            <input
              value={form.scam_types.join(", ")}
              onChange={(e) =>
                setForm({
                  ...form,
                  scam_types: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded text-sm disabled:opacity-50"
          >
            {saving ? "Saving…" : "Create Persona"}
          </button>
        </form>
      </div>
    </div>
  );
}
