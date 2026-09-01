import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import Spinner from "../components/Spinner.jsx";
import { approvalNotesApi } from "../services/approvalNotes.js";

const PARAM_FIELDS = [
  { key: "Amount / Value", placeholder: "e.g. ₹5 crore" },
  { key: "Vendor / Party", placeholder: "e.g. ACME Pvt Ltd" },
  { key: "Justification", placeholder: "Why this is required" },
];

export default function ApprovalNotes() {
  const navigate = useNavigate();
  const [types, setTypes] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [typeId, setTypeId] = useState("");
  const [title, setTitle] = useState("");
  const [params, setParams] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, n] = await Promise.all([approvalNotesApi.listTypes(), approvalNotesApi.listNotes()]);
      setTypes(t);
      setNotes(n);
    } catch (err) {
      setError(err.message || "Could not load Approval Notes.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async (e) => {
    e.preventDefault();
    setError("");
    setNotice("");
    if (!typeId) return setError("Please select an Approval Note type.");
    setSubmitting(true);
    try {
      const cleanParams = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v && v.trim())
      );
      const note = await approvalNotesApi.createNote({
        approval_note_type_id: Number(typeId),
        title: title.trim() || undefined,
        parameters: cleanParams,
      });
      navigate(`/approval-notes/${note.id}/edit`);
    } catch (err) {
      setError(err.message || "Could not create the Approval Note.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app-shell">
      <Navbar />
      <main className="content">
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__title">Create Approval Note</h2>
            <p className="panel__desc">
              Pick a type, add any details, and the local AI drafts the note on your company
              letterhead. You can then edit it in ONLYOFFICE.
            </p>
          </div>
          <form className="form" onSubmit={create}>
            {error && <div className="alert alert--error" role="alert">{error}</div>}
            {notice && <div className="alert alert--success" role="status">{notice}</div>}

            <label className="field">
              <span className="field__label">Approval Note Type</span>
              <select className="field__input" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
                <option value="" disabled>Select a type…</option>
                {types.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              {types.length === 0 && !loading && (
                <span className="field__hint">No active types yet — ask an administrator to add some.</span>
              )}
            </label>

            <label className="field">
              <span className="field__label">Title (optional — defaults to the type name)</span>
              <input className="field__input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. CAPEX APPROVAL NOTE" />
            </label>

            <div className="field-row">
              {PARAM_FIELDS.map((f) => (
                <label className="field" key={f.key}>
                  <span className="field__label">{f.key}</span>
                  <input
                    className="field__input"
                    value={params[f.key] || ""}
                    onChange={(e) => setParams((p) => ({ ...p, [f.key]: e.target.value }))}
                    placeholder={f.placeholder}
                  />
                </label>
              ))}
            </div>

            <button type="submit" className="btn btn--primary" disabled={submitting || types.length === 0}>
              {submitting ? "Generating…" : "Generate Approval Note"}
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panel__head"><h2 className="panel__title">My Approval Notes</h2></div>
          {loading ? (
            <div className="ask__loading"><Spinner /> Loading…</div>
          ) : notes.length === 0 ? (
            <p className="empty">You haven&apos;t created any Approval Notes yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Title</th><th>Status</th><th>Version</th><th>Created</th><th>Actions</th></tr>
                </thead>
                <tbody>
                  {notes.map((n) => (
                    <tr key={n.id}>
                      <td>{n.title}</td>
                      <td><span className="badge badge--approved">{n.status}</span></td>
                      <td className="cell--muted">v{n.document_version}</td>
                      <td className="cell--muted">{new Date(n.created_at).toLocaleDateString()}</td>
                      <td>
                        <div className="row-actions">
                          <button className="btn btn--sm btn--primary" onClick={() => navigate(`/approval-notes/${n.id}/edit`)}>
                            Edit Document
                          </button>
                          <button className="btn btn--sm" onClick={() => approvalNotesApi.downloadNote(n.id, `${n.title}.docx`)}>
                            Download
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
