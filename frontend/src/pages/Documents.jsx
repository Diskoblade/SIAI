import { useCallback, useEffect, useRef, useState } from "react";
import { Building2, Globe2, LockKeyhole, Trash2 } from "lucide-react";
import AppShell from "../components/AppShell.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Spinner from "../components/Spinner.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { departmentsApi, documentsApi } from "../services/auth.js";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".xlsx"];
const MAX_FILE_BYTES = 20 * 1024 * 1024;
const TEXT_TO_FILE_THRESHOLD = 200;

function formatFileSize(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildTextFileName(title) {
  const base = title
    .trim()
    .replace(/[\\/]+/g, "-")
    .replace(/\.[^.]+$/, "")
    .replace(/\s+/g, " ")
    .trim();
  return `${(base || "document").slice(0, 120)}.txt`;
}

function VisibilityLabel({ document }) {
  if (document.visibility === "PRIVATE") {
    return <span className="visibility visibility--private"><LockKeyhole size={15} /> Private</span>;
  }
  if (document.visibility === "COMMON") {
    return <span className="visibility visibility--common"><Globe2 size={15} /> Common</span>;
  }
  return (
    <span className="visibility visibility--department">
      <Building2 size={15} /> Shared with {document.department_name || "department"}
    </span>
  );
}

export default function Documents() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [view, setView] = useState("mine");
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [shareError, setShareError] = useState("");
  const [updatingIds, setUpdatingIds] = useState(new Set());
  const [deleteError, setDeleteError] = useState("");
  const [deleteNotice, setDeleteNotice] = useState("");
  const [deletingIds, setDeletingIds] = useState(new Set());

  const [departments, setDepartments] = useState([]);
  const [mode, setMode] = useState("file");
  const [form, setForm] = useState({ title: "", text: "", department_id: "" });
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setListError("");
    try {
      setDocs(await documentsApi.list(view));
    } catch (err) {
      setListError(err.message || "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    load();
    if (isAdmin) departmentsApi.list().then(setDepartments).catch(() => {});
  }, [load, isAdmin]);

  const update = (key) => (event) => (
    setForm((current) => ({ ...current, [key]: event.target.value }))
  );

  const chooseFile = (selected) => {
    setNotice("");
    setUploadError("");
    if (!selected) {
      setFile(null);
      return;
    }
    const lowerName = selected.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
      setFile(null);
      setUploadError("Choose a PDF, DOCX, TXT, Markdown, CSV, or XLSX file.");
      return;
    }
    if (selected.size > MAX_FILE_BYTES) {
      setFile(null);
      setUploadError("File exceeds the 20 MB limit.");
      return;
    }
    setFile(selected);
    setForm((current) => ({
      ...current,
      title: current.title || selected.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "),
    }));
  };

  const dropFile = (event) => {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0] || null);
  };

  const submit = async (event) => {
    event.preventDefault();
    setNotice("");
    setUploadError("");
    if (!form.title.trim()) return setUploadError("A title is required.");
    setSubmitting(true);
    try {
      let uploaded;
      if (mode === "file") {
        if (!file) throw new Error("Please choose a file.");
        const data = new FormData();
        data.append("file", file);
        data.append("title", form.title.trim());
        if (isAdmin && form.department_id) data.append("department_id", form.department_id);
        uploaded = await documentsApi.uploadFile(data);
      } else {
        if (!form.text.trim()) throw new Error("Please enter document text.");
        if (form.text.trim().length > TEXT_TO_FILE_THRESHOLD) {
          const data = new FormData();
          const textFile = new File([form.text], buildTextFileName(form.title), {
            type: "text/plain;charset=utf-8",
          });
          data.append("file", textFile);
          data.append("title", form.title.trim());
          if (isAdmin && form.department_id) data.append("department_id", form.department_id);
          uploaded = await documentsApi.uploadFile(data);
        } else {
          uploaded = await documentsApi.uploadText({
            title: form.title.trim(),
            text: form.text,
            department_id: isAdmin && form.department_id ? Number(form.department_id) : null,
          });
        }
      }
      setNotice(
        uploaded.visibility === "PRIVATE"
          ? "File indexed privately."
          : `Content indexed with ${uploaded.visibility.toLowerCase()} visibility.`
      );
      setForm({ title: "", text: "", department_id: "" });
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setView("mine");
      await load();
    } catch (err) {
      setUploadError(err.message || "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleSharing = async (document) => {
    const nextVisibility = document.visibility === "PRIVATE" ? "DEPARTMENT" : "PRIVATE";
    const previous = document;
    setShareError("");
    setUpdatingIds((current) => new Set(current).add(document.id));
    setDocs((current) => current.map((item) => (
      item.id === document.id ? { ...item, visibility: nextVisibility } : item
    )));
    try {
      const updated = await documentsApi.updateVisibility(document.id, nextVisibility);
      setDocs((current) => current.map((item) => item.id === document.id ? updated : item));
    } catch (err) {
      setDocs((current) => current.map((item) => item.id === document.id ? previous : item));
      setShareError(err.message || "Sharing could not be updated.");
    } finally {
      setUpdatingIds((current) => {
        const next = new Set(current);
        next.delete(document.id);
        return next;
      });
    }
  };

  const deleteFile = async (document) => {
    const confirmed = window.confirm(
      `Delete "${document.title}"? This removes it from knowledge search and cannot be undone.`
    );
    if (!confirmed) return;

    setDeleteError("");
    setDeleteNotice("");
    setDeletingIds((current) => new Set(current).add(document.id));
    try {
      await documentsApi.delete(document.id);
      setDocs((current) => current.filter((item) => item.id !== document.id));
      setDeleteNotice(`Deleted "${document.title}".`);
    } catch (err) {
      setDeleteError(err.message || "The file could not be deleted.");
    } finally {
      setDeletingIds((current) => {
        const next = new Set(current);
        next.delete(document.id);
        return next;
      });
    }
  };

  return (
    <AppShell>
        <PageHeader
          code="VECTOR_STORE / KNOWLEDGE_OBJECTS"
          title="Sovereign knowledge"
          description="Index private files, manage department sharing, and inspect the knowledge available to SI."
        />
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__title">Add a file</h2>
            <p className="panel__desc">
              {isAdmin ? "Publish common or department knowledge." : "New files are private to you."}
            </p>
          </div>

          <form className="form" onSubmit={submit}>
            {notice && <div className="alert alert--success" role="status">{notice}</div>}
            {uploadError && <div className="alert alert--error" role="alert">{uploadError}</div>}

            <div className="seg">
              <button type="button" className={`chip ${mode === "file" ? "chip--active" : ""}`} onClick={() => setMode("file")}>Upload file</button>
              <button type="button" className={`chip ${mode === "text" ? "chip--active" : ""}`} onClick={() => setMode("text")}>Paste text</button>
            </div>

            <label className="field">
              <span className="field__label">Title</span>
              <input className="field__input" value={form.title} onChange={update("title")} placeholder="Project pipeline notes" />
            </label>

            {mode === "text" ? (
              <label className="field">
                <span className="field__label">Document text</span>
                <textarea className="ask__input" rows={6} value={form.text} onChange={update("text")} placeholder="Paste the document content..." />
              </label>
            ) : (
              <label
                className={`upload-drop ${dragging ? "upload-drop--active" : ""}`}
                onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setDragging(false)}
                onDrop={dropFile}
              >
                <input
                  ref={fileInputRef}
                  className="upload-drop__input"
                  type="file"
                  accept={ACCEPTED_EXTENSIONS.join(",")}
                  onChange={(event) => chooseFile(event.target.files?.[0] || null)}
                />
                <span className="upload-drop__title">Drop a file here or browse</span>
                <span className="upload-drop__hint">PDF, DOCX, TXT, Markdown, CSV, or XLSX | 20 MB maximum</span>
                {file && (
                  <span className="upload-drop__file">
                    <strong>{file.name}</strong>
                    <span>{formatFileSize(file.size)}</span>
                  </span>
                )}
              </label>
            )}

            {isAdmin && (
              <label className="field">
                <span className="field__label">Publish to</span>
                <select className="field__input" value={form.department_id} onChange={update("department_id")}>
                  <option value="">Common knowledge</option>
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>{department.name}</option>
                  ))}
                </select>
              </label>
            )}

            <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
              {submitting ? <><Spinner /> Parsing and indexing...</> : "Add to knowledge base"}
            </button>
          </form>
        </section>

        <section className="panel">
          <div className="panel__head panel__head--row">
            <div>
              <h2 className="panel__title">Knowledge files</h2>
              <p className="panel__desc">
                {view === "mine" ? "Files you own." : "Department-shared and common files."}
              </p>
            </div>
            <div className="seg" aria-label="Document view">
              <button type="button" className={`chip ${view === "mine" ? "chip--active" : ""}`} onClick={() => setView("mine")}>My files</button>
              <button type="button" className={`chip ${view === "shared" ? "chip--active" : ""}`} onClick={() => setView("shared")}>Department knowledge</button>
            </div>
          </div>

          {shareError && <div className="alert alert--error" role="alert">{shareError}</div>}
          {deleteError && <div className="alert alert--error" role="alert">{deleteError}</div>}
          {deleteNotice && <div className="alert alert--success" role="status">{deleteNotice}</div>}
          {loading ? (
            <div className="ask__loading"><Spinner /> Loading...</div>
          ) : listError ? (
            <div className="alert alert--error">{listError}</div>
          ) : docs.length === 0 ? (
            <p className="empty">No files in this view.</p>
          ) : (
            <div className="table-wrap">
              <table className="table document-table">
                <thead>
                  <tr><th>File</th><th>Visibility</th><th>Department sharing</th><th>Added</th><th><span className="sr-only">Actions</span></th></tr>
                </thead>
                <tbody>
                  {docs.map((document) => {
                    const canToggle = view === "mine"
                      && document.owner_user_id === user?.id
                      && document.visibility !== "COMMON"
                      && document.owner_department_id === user?.department_id;
                    const updating = updatingIds.has(document.id);
                    const deleting = deletingIds.has(document.id);
                    const canDelete = document.owner_user_id === user?.id;
                    return (
                      <tr key={document.id} className={deleting ? "row--busy" : ""}>
                        <td>
                          <strong className="document-title">{document.title}</strong>
                          <span className="document-file">
                            {document.source_filename || document.document_type} | {document.chunk_count} chunks
                          </span>
                        </td>
                        <td><VisibilityLabel document={document} /></td>
                        <td>
                          {canToggle ? (
                            <label className="share-toggle">
                              <span>Share with {document.department_name || user?.department_name}</span>
                              <input
                                type="checkbox"
                                checked={document.visibility === "DEPARTMENT"}
                                onChange={() => toggleSharing(document)}
                                disabled={updating || deleting}
                              />
                              <span className="share-toggle__track" aria-hidden="true">
                                <span className="share-toggle__thumb" />
                              </span>
                              {updating && <Spinner />}
                            </label>
                          ) : (
                            <span className="cell--muted">{document.visibility === "COMMON" ? "Organization-wide" : "Read only"}</span>
                          )}
                        </td>
                        <td className="cell--muted">{new Date(document.created_at).toLocaleDateString()}</td>
                        <td className="document-actions">
                          {canDelete ? (
                            <button
                              type="button"
                              className="btn btn--icon btn--delete"
                              onClick={() => deleteFile(document)}
                              disabled={deleting || updating}
                              aria-label={`Delete ${document.title}`}
                              title="Delete file"
                            >
                              {deleting ? <Spinner /> : <Trash2 size={17} aria-hidden="true" />}
                            </button>
                          ) : (
                            <span className="cell--muted" aria-hidden="true">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
    </AppShell>
  );
}
