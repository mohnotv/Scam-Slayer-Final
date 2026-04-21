import { Route, Routes, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import CallDetail from "./pages/CallDetail";
import Personas from "./pages/Personas";
import Clips from "./pages/Clips";

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
          isActive
            ? "bg-green-600 text-white"
            : "text-gray-300 hover:bg-gray-700 hover:text-white"
        }`
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <nav className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-2">
        <span className="text-green-400 font-bold text-lg mr-6">⚔ ScamSlayer</span>
        <NavItem to="/" label="Dashboard" />
        <NavItem to="/personas" label="Personas" />
        <NavItem to="/clips" label="Clips" />
      </nav>
      <main className="p-6 max-w-7xl mx-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/calls/:id" element={<CallDetail />} />
          <Route path="/personas" element={<Personas />} />
          <Route path="/clips" element={<Clips />} />
        </Routes>
      </main>
    </div>
  );
}
