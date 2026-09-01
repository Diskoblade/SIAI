import { useEffect, useState } from "react";
import { Code2, FilePlus2, Play, Save, Trash2 } from "lucide-react";
import AppShell from "../components/AppShell.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Spinner from "../components/Spinner.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ideApi } from "../services/auth.js";

function normalizePath(value) {
  return value
    .trim()
    .replace(/[\\/]+/g, "/")
    .replace(/^\//, "")
    .replace(/\.\.(?=\/|$)/g, "")
    .replace(/\/+/g, "/")
    .trim();
}

function buildNextPath(files, rawPath) {
  const cleaned = normalizePath(rawPath) || "src/new-file.js";
  if (!files.some((file) => file.path === cleaned)) return cleaned;
  const match = cleaned.match(/^(.*?)(\.[^.]+)?$/);
  const stem = match?.[1] || cleaned;
  const ext = match?.[2] || "";
  let index = 2;
  while (files.some((file) => file.path === `${stem}-${index}${ext}`)) {
    index += 1;
  }
  return `${stem}-${index}${ext}`;
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

export default function DeveloperWorkspace() {
  const { user } = useAuth();
  const [integration, setIntegration] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [codeProject, setCodeProject] = useState(null);
  const [files, setFiles] = useState([]);
  const [activeFile, setActiveFile] = useState("");
  const [newPath, setNewPath] = useState("src/new-file.js");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [saveError, setSaveError] = useState("");
  const [saveNotice, setSaveNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.allSettled([ideApi.code(), ideApi.status()]).then(([codeResult, statusResult]) => {
      if (!active) return;
      if (codeResult.status === "fulfilled") {
        const project = codeResult.value;
        setCodeProject(project);
        setFiles(project.files);
        setActiveFile(project.active_file);
        setNewPath(buildNextPath(project.files, "src/new-file.js"));
      } else {
        setError(codeResult.reason?.message || "Could not load the saved code project.");
      }
      if (statusResult.status === "fulfilled") {
        setIntegration(statusResult.value);
        setWorkspace(statusResult.value.workspace);
      } else {
        setWorkspaceError(statusResult.reason?.message || "Could not load the OpenHands status.");
      }
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!dirty || !codeProject || files.length === 0 || !activeFile) return undefined;
    const timer = window.setTimeout(() => {
      setSaving(true);
      setSaveError("");
      ideApi
        .saveCode({ active_file: activeFile, files })
        .then((project) => {
          setCodeProject(project);
          setFiles(project.files);
          setActiveFile(project.active_file);
          setSaveNotice(`Saved at ${formatTimestamp(project.updated_at) || "now"}.`);
          setDirty(false);
        })
        .catch((err) => {
          setSaveError(err.message || "The code could not be saved.");
        })
        .finally(() => setSaving(false));
    }, 700);
    return () => window.clearTimeout(timer);
  }, [activeFile, codeProject, dirty, files]);

  const start = async () => {
    setStarting(true);
    setWorkspaceError("");
    try {
      setWorkspace(await ideApi.startWorkspace());
    } catch (err) {
      setWorkspaceError(err.message || "The coding workspace could not be started.");
    } finally {
      setStarting(false);
    }
  };

  const launch = async () => {
    setStarting(true);
    setWorkspaceError("");
    try {
      const result = await ideApi.launchWorkspace();
      window.location.assign(result.launch_url);
    } catch (err) {
      setWorkspaceError(err.message || "The coding workspace could not be opened.");
      setStarting(false);
    }
  };

  const selectFile = (path) => {
    setActiveFile(path);
    setDirty(true);
    setSaveNotice("");
  };

  const updateContent = (value) => {
    setFiles((current) => current.map((file) => (
      file.path === activeFile ? { ...file, content: value } : file
    )));
    setDirty(true);
    setSaveNotice("");
  };

  const addFile = () => {
    const path = buildNextPath(files, newPath);
    setFiles((current) => [...current, { path, content: "" }]);
    setActiveFile(path);
    setNewPath(buildNextPath([...files, { path, content: "" }], path));
    setDirty(true);
    setSaveNotice("");
    setSaveError("");
  };

  const removeFile = (path) => {
    if (files.length <= 1) {
      setSaveError("Keep at least one file in the project.");
      return;
    }
    const nextFiles = files.filter((file) => file.path !== path);
    const nextActive = path === activeFile ? nextFiles[0].path : activeFile;
    setFiles(nextFiles);
    setActiveFile(nextActive);
    setDirty(true);
    setSaveNotice("");
  };

  const manualSave = async () => {
    if (!codeProject || files.length === 0 || !activeFile) return;
    setSaving(true);
    setSaveError("");
    try {
      const project = await ideApi.saveCode({ active_file: activeFile, files });
      setCodeProject(project);
      setFiles(project.files);
      setActiveFile(project.active_file);
      setSaveNotice(`Saved at ${formatTimestamp(project.updated_at) || "now"}.`);
      setDirty(false);
    } catch (err) {
      setSaveError(err.message || "The code could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const ready = workspace?.status === "ready";
  const activeContent = files.find((file) => file.path === activeFile)?.content ?? "";
  const launchEnabled = Boolean(integration?.enabled && integration?.configured);

  return (
    <AppShell contentClassName="code-content">
        <PageHeader
          code="AGENT_RUNTIME / OPENHANDS"
          title="Coding workspace"
          description="Edit account-owned source files and open the managed runtime when execution is required."
          action={<span className={`status-pill ${ready ? "status-pill--live" : ""}`}>
            <span className="status-pill__dot" />
            {ready ? "Ready" : workspace?.status || "Not started"}
          </span>}
        />

        <section className="panel workspace-panel">
          {loading ? (
            <div className="ask__loading"><Spinner /> Loading coding workspace…</div>
          ) : error ? (
            <div className="alert alert--error" role="alert">{error}</div>
          ) : (
            <>
              {workspaceError && <div className="alert alert--error" role="alert">{workspaceError}</div>}
              {!integration?.enabled ? (
                <div className="workspace-state">
                  <h2 className="panel__title">Coding workspace is not enabled</h2>
                  <p className="panel__desc">
                    The OpenHands runtime is disabled, but your saved code still loads
                    from your account.
                  </p>
                </div>
              ) : !integration?.configured ? (
                <div className="workspace-state">
                  <h2 className="panel__title">Infrastructure connection required</h2>
                  <p className="panel__desc">
                    The OpenHands provisioner has not been configured yet.
                  </p>
                </div>
              ) : (
                <>
                  <div className="workspace-grid">
                    <div className="workspace-fact">
                      <span className="workspace-fact__label">Assigned user</span>
                      <strong>{user?.full_name}</strong>
                    </div>
                    <div className="workspace-fact">
                      <span className="workspace-fact__label">Department</span>
                      <strong>{user?.department_name || "Unassigned"}</strong>
                    </div>
                    <div className="workspace-fact">
                      <span className="workspace-fact__label">Isolation</span>
                      <strong>Per-user runtime</strong>
                    </div>
                  </div>

                  <div className="workspace-actions">
                    {ready ? (
                      <button type="button" className="btn btn--primary" onClick={launch} disabled={starting}>
                        {starting ? <><Spinner /> Opening…</> : <><Play size={17} aria-hidden="true" /> Open OpenHands</>}
                      </button>
                    ) : (
                      <button type="button" className="btn btn--primary" onClick={start} disabled={starting}>
                        {starting ? <><Spinner /> Connecting…</> : "Start coding"}
                      </button>
                    )}
                    {workspace?.external_id && (
                      <span className="workspace-id">Workspace {workspace.external_id}</span>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </section>

        <section className="panel editor-panel">
          <div className="editor-panel__head">
            <div>
              <h2 className="panel__title">Saved code</h2>
              <p className="panel__desc">
                Your files are stored in the database under your account and reload
                after login.
              </p>
            </div>
            <div className="editor-panel__status">
              {saveError && <span className="editor-status editor-status--error">{saveError}</span>}
              {!saveError && saveNotice && <span className="editor-status">{saveNotice}</span>}
              {!saveError && !saveNotice && dirty && <span className="editor-status">Unsaved changes</span>}
              {!saveError && !saveNotice && !dirty && <span className="editor-status">Saved</span>}
            </div>
          </div>

          {loading ? (
            <div className="ask__loading"><Spinner /> Loading editor…</div>
          ) : (
            <div className="editor-shell">
              <aside className="editor-files">
                <div className="editor-files__new">
                  <input
                    className="field__input editor-files__input"
                    value={newPath}
                    onChange={(event) => setNewPath(event.target.value)}
                    placeholder="src/new-file.js"
                  />
                  <button type="button" className="btn btn--ghost" onClick={addFile}>
                    <FilePlus2 size={16} aria-hidden="true" />
                    Add
                  </button>
                </div>

                <div className="editor-files__list">
                  {files.map((file) => (
                    <div
                      key={file.path}
                      className={`editor-file ${file.path === activeFile ? "editor-file--active" : ""}`}
                    >
                      <button
                        type="button"
                        className="editor-file__select"
                        onClick={() => selectFile(file.path)}
                      >
                        <Code2 size={15} aria-hidden="true" />
                        <span>{file.path}</span>
                      </button>
                      <button
                        type="button"
                        className="editor-file__delete"
                        onClick={() => removeFile(file.path)}
                        disabled={files.length <= 1}
                        title="Delete file"
                        aria-label={`Delete ${file.path}`}
                      >
                        <Trash2 size={15} aria-hidden="true" />
                      </button>
                    </div>
                  ))}
                </div>
              </aside>

              <div className="editor-main">
                <div className="editor-toolbar">
                  <div>
                    <strong>{activeFile || "No file selected"}</strong>
                    <span>{codeProject ? `Updated ${formatTimestamp(codeProject.updated_at) || "recently"}` : ""}</span>
                  </div>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={manualSave}
                    disabled={saving || !dirty}
                  >
                    {saving ? <Spinner /> : <Save size={16} aria-hidden="true" />}
                    {saving ? "Saving..." : "Save now"}
                  </button>
                </div>

                <textarea
                  className="editor-textarea"
                  value={activeContent}
                  onChange={(event) => updateContent(event.target.value)}
                  spellCheck={false}
                  autoCapitalize="off"
                  autoComplete="off"
                  autoCorrect="off"
                  placeholder="Write code here..."
                />
              </div>
            </div>
          )}
        </section>
    </AppShell>
  );
}
