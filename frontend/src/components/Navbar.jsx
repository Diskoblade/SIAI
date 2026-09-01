import {
  Clock3,
  Code2,
  Database,
  FileSignature,
  LogOut,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const navigation = [
  { to: "/dashboard", label: "Intelligence", number: "01", icon: MessageSquareText },
  { to: "/documents", label: "Knowledge", number: "02", icon: Database },
  { to: "/recent", label: "Activity", number: "03", icon: Clock3 },
  { to: "/code", label: "Code", number: "04", icon: Code2 },
  { to: "/approval-notes", label: "Approval Notes", number: "05", icon: FileSignature },
];

export default function Navbar() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <aside className="navbar">
      <NavLink className="navbar__brand" to="/dashboard" aria-label="SI intelligence workspace">
        <span className="navbar__seal" aria-hidden="true">SI</span>
        <span>
          <strong className="navbar__title">SIAI</strong>
          <small className="navbar__subtitle">SOVEREIGN INTELLIGENCE</small>
        </span>
      </NavLink>

      <div className="navbar__system">
        <span>SYS / ONLINE</span>
        <span>INTELLIGENCE WITHOUT SURRENDER.</span>
      </div>

      <nav className="navbar__links" aria-label="Product navigation">
        {navigation.map(({ to, label, number, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <span className="navbar__number">{number}</span>
            <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
            <span>{label}</span>
          </NavLink>
        ))}
        {isAdmin && (
          <>
            <NavLink to="/admin/approval-notes" className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="navbar__number">06</span>
              <FileSignature size={17} strokeWidth={1.8} aria-hidden="true" />
              <span>Approval Settings</span>
            </NavLink>
            <NavLink to="/admin" className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="navbar__number">07</span>
              <ShieldCheck size={17} strokeWidth={1.8} aria-hidden="true" />
              <span>Administration</span>
            </NavLink>
          </>
        )}
      </nav>

      <div className="navbar__user">
        <div className="navbar__identity">
          <span>IDENTITY / AUTHENTICATED</span>
          <strong className="navbar__username">{user?.full_name}</strong>
          <small>{user?.department_name || "Department unassigned"}</small>
        </div>
        <div className="navbar__userActions">
          <span className="badge badge--role">{user?.role}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={handleLogout}>
            <LogOut size={15} aria-hidden="true" />
            Log out
          </button>
        </div>
      </div>
    </aside>
  );
}
