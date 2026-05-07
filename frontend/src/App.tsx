import { Route, Routes, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import CallDetail from "./pages/CallDetail";
import Personas from "./pages/Personas";
import Checks from "./pages/Checks";

function NavItem({ to, label, exact }: { to: string; label: string; exact?: boolean }) {
  return (
    <NavLink
      to={to}
      end={exact}
      className={({ isActive }) =>
        `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
          isActive
            ? "bg-green-500/20 text-green-400 border border-green-500/30"
            : "text-slate-400 hover:text-slate-200 hover:bg-white/5"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-navy-950 text-slate-100">
      <nav className="bg-navy-900 border-b border-white/10 px-6 py-3 flex items-center gap-3 sticky top-0 z-40 backdrop-blur">
        <div className="flex items-center gap-2 mr-6">
          <span className="text-green-400 text-lg">⚔</span>
          <span className="font-bold text-white tracking-tight">ScamSlayer</span>
        </div>
        <NavItem to="/" label="Dashboard" exact />
        <NavItem to="/personas" label="Personas" />
        <NavItem to="/checks" label="Checks" />
      </nav>
      <main className="p-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/personas" element={<Personas />} />
          <Route path="/checks" element={<Checks />} />
        </Routes>
      </main>
    </div>
  );
}
