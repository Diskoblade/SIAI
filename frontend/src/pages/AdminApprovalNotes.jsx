import { useCallback, useEffect, useRef, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import Spinner from "../components/Spinner.jsx";
import { approvalNotesApi } from "../services/approvalNotes.js";

export default function AdminApprovalNotes() {
  const [letterhead, setLetterhead] = useState(null);
  const [types, setTypes] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [uploading, setUploading] = useState(false);
  const [newType, setNewType] = useState("");
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [lh, t] = await Promise.all([
        approvalNotesApi.getLetterhead(),
        approvalNotesApi.adminListTypes(),
      ]);
      setLetterhead(lh);
      setTypes(t);
    } catch (err) {
      setError(err.message || "Could not load settings.");
    } finally {
      setLoading(false);
    }
    approvalNotesApi.onlyofficeHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (e) => {
    e.preventDefault();
    setError("");
    setNotice("");
    const file = fileRef.current?.files?.[0];
    if (!file) return setError("Choose a .docx letterhead file.");
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await approvalNotesApi.uploadLetterhead(fd);
      setNotice("Letterhead saved as the active Approval Note template.");
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const addType = async (e) => {
    e.preventDefault();
    if (!newType.trim()) return;
    try {
      await approvalNotesApi.createType({ name: newType.trim() });
      setNewType("");
      await load();
    } catch (err) {
      setError(err.message || "Could not add type.");
    }
  };

  const toggleType = async (t) => {
    try {
      await approvalNotesApi.updateType(t.id, { is_active: !t.is_active });
      await load();
    } catch (err) {
      setError(err.message || "Could not update type.");
    }
  };

  const active = letterhead?.template;

  return (
    <div className="app-shell">
      <Navbar />
      <main className="content">
        {/* Letterhead */}
        <section className="panel">
          <div className="panel__head panel__head--row">
            <div>
              <h2 className="panel__title">Approval Note Letterhead</h2>
              <p className="panel__desc">Upload the company .docx letterhead used as the master template for every Approval Note.</p>
            </div>
            {health && (
              <span className={`status-pill ${health.reachable ? "status-pill--live" : ""}`} title="ONLYOFFICE Document Server">
                <span className="status-pill__dot" />
                ONLYOFFICE: {health.reachable ? "Connected" : health.configured ? "Unavailable" : "Not configured"}
              </span>
            )}
          </div>

          {error && <div className="alert alert--error" role="alert">{error}</div>}
          {notice && <div className="alert alert--success" role="status">{notice}</div>}

          {loading ? (
            <div className="ask__loading"><Spinner /> Loading…</div>
          ) : (
            <>
              <div className="meta-card" style={{ marginBottom: "1rem" }}>
                {active ? (
                  <>
                    <span className="meta-card__label">Active letterhead</span>
                    <span className="meta-card__value">{active.original_filename}</span>
                    <span className="field__hint">
                      Version {active.version} · updated {new Date(active.updated_at).toLocaleString()}
                    </span>
                    <div className="row-actions" style={{ marginTop: "0.6rem" }}>
                      <button className="btn btn--sm" onClick={() => approvalNotesApi.downloadLetterhead(active.original_filename)}>
                        Download master
                      </button>
                    </div>
                  </>
                ) : (
                  <span className="meta-card__value">No letterhead configured yet.</span>
                )}
              </div>

              <form className="form" onSubmit={upload}>
                <label className="field">
                  <span className="field__label">{active ? "Replace letterhead (.docx)" : "Upload letterhead (.docx)"}</span>
                  <input className="field__input" type="file" accept=".docx" ref={fileRef} />
                  <span className="field__hint">
                    Placeholders supported: <code>{"{{APPROVAL_NOTE_TITLE}}"}</code>, <code>{"{{APPROVAL_NOTE_CONTENT}}"}</code>,
                    plus {"{{DATE}}"}, {"{{DEPARTMENT}}"}, {"{{PREPARED_BY}}"}.
                  </span>
                </label>
                <button className="btn btn--primary" disabled={uploading}>
                  {uploading ? "Uploading…" : active ? "Replace letterhead" : "Upload letterhead"}
                </button>
              </form>
            </>
          )}
        </section>

        {/* Types */}
        <section className="panel">
          <div className="panel__head"><h2 className="panel__title">Approval Note Types</h2></div>
          <form className="form" onSubmit={addType}>
            <div className="field-row">
              <label className="field" style={{ flex: 1 }}>
                <span className="field__label">Add a type</span>
                <input className="field__input" value={newType} onChange={(e) => setNewType(e.target.value)} placeholder="e.g. Emergency Procurement Approval Note" />
              </label>
              <button className="btn btn--primary" style={{ alignSelf: "end" }}>Add</button>
            </div>
          </form>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Name</th><th>Order</th><th>Status</th><th>Action</th></tr></thead>
              <tbody>
                {types.map((t) => (
                  <tr key={t.id}>
                    <td>{t.name}</td>
                    <td className="cell--muted">{t.display_order}</td>
                    <td><span className={`badge badge--${t.is_active ? "approved" : "disabled"}`}>{t.is_active ? "active" : "inactive"}</span></td>
                    <td>
                      <button className={`btn btn--sm ${t.is_active ? "btn--warn" : "btn--success"}`} onClick={() => toggleType(t)}>
                        {t.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
