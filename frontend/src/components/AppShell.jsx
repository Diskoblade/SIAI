import { useAuth } from "../context/AuthContext.jsx";
import Navbar from "./Navbar.jsx";

export default function AppShell({ children, contentClassName = "", shellClassName = "" }) {
  const { user } = useAuth();

  return (
    <div className={`app-shell ${shellClassName}`.trim()}>
      <Navbar />
      <div className="app-stage">
        <header className="app-topbar">
          <span>SI / OPERATOR ENVIRONMENT</span>
          <div className="app-topbar__state">
            <span>ACCESS / AUTHORIZED</span>
            <span>DEPT / {user?.department_name || "UNASSIGNED"}</span>
            <span>ROLE / {user?.role || "USER"}</span>
          </div>
        </header>
        <main className={`content ${contentClassName}`.trim()}>{children}</main>
      </div>
    </div>
  );
}
