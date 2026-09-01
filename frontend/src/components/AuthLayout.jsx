import { ArrowLeft, LockKeyhole, Network, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

export default function AuthLayout({ heading, sub, children }) {
  return (
    <div className="auth">
      <aside className="auth__brand">
        <div className="auth__brandInner">
          <Link className="auth__back" to="/"><ArrowLeft size={16} aria-hidden="true" /> SIAI / HOME</Link>
          <div className="auth__seal" aria-hidden="true">SI</div>
          <p className="auth__brandCode">SIAI / SECURE ACCESS NODE</p>
          <h1 className="auth__brandTitle">SOVEREIGN<br />INTELLIGENCE</h1>
          <p className="auth__brandSub">INTELLIGENCE WITHOUT SURRENDER.</p>
          <ul className="auth__points">
            <li><Network size={16} aria-hidden="true" /> Department-scoped retrieval</li>
            <li><ShieldCheck size={16} aria-hidden="true" /> Administrator-approved access</li>
            <li><LockKeyhole size={16} aria-hidden="true" /> Audited authorization</li>
          </ul>
          <p className="auth__gov">ACCESS / RESTRICTED<br />AUTHORIZED PERSONNEL ONLY</p>
        </div>
      </aside>

      <main className="auth__panel">
        <div className="auth__card">
          <span className="auth__formCode">IDENTITY_GATE / 01</span>
          <h2 className="auth__heading">{heading}</h2>
          {sub && <p className="auth__sub">{sub}</p>}
          {children}
        </div>
      </main>
    </div>
  );
}
