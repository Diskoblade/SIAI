import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Download, Save } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "../components/AppShell.jsx";
import Spinner from "../components/Spinner.jsx";
import OnlyOfficeEditor from "../components/OnlyOfficeEditor.jsx";
import { approvalNotesApi } from "../services/approvalNotes.js";

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export default function ApprovalNoteEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const editorDirtyRef = useRef(false);
  const [note, setNote] = useState(null);
  const [editor, setEditor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editorReady, setEditorReady] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState("Opening editor...");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [nextNote, config] = await Promise.all([
          approvalNotesApi.getNote(id),
          approvalNotesApi.editorConfig(id),
        ]);
        if (!active) return;
        setNote(nextNote);
        setEditor(config);
      } catch (err) {
        if (active) setError(err.message || "Could not open the document.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [id]);

  const handleEditorReady = useCallback((ready = true) => {
    setEditorReady(ready);
    if (ready) setSaveNotice("Editor ready. Changes are saved to your account.");
  }, []);

  const handleDirtyChange = useCallback((dirty) => {
    editorDirtyRef.current = dirty;
    if (dirty) {
      setHasChanges(true);
      setSaveNotice("Unsaved changes");
    } else {
      setSaveNotice((current) => (
        current === "Unsaved changes" ? "Changes buffered. Select Save to persist now." : current
      ));
    }
  }, []);

  const saveChanges = useCallback(async () => {
    if (!note || !editorReady || saving) return false;
    const previousVersion = note.document_version;
    setSaving(true);
    setError("");
    setSaveNotice("Saving changes...");

    try {
      const syncDeadline = Date.now() + 4000;
      while (editorDirtyRef.current && Date.now() < syncDeadline) {
        await sleep(250);
      }

      const documentKey = editor.config.document.key;
      let result = await approvalNotesApi.forceSave(note.id, documentKey);
      if (!result.accepted && result.error_code === 4 && hasChanges) {
        await sleep(1000);
        result = await approvalNotesApi.forceSave(note.id, documentKey);
      }

      if (!result.accepted) {
        const latest = await approvalNotesApi.getNote(note.id);
        setNote(latest);
        setHasChanges(false);
        setSaveNotice(result.message);
        return true;
      }

      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        await sleep(600);
        const latest = await approvalNotesApi.getNote(note.id);
        if (latest.document_version > previousVersion) {
          setNote(latest);
          setHasChanges(false);
          setSaveNotice(`Saved as version ${latest.document_version}.`);
          return true;
        }
      }
      throw new Error("ONLYOFFICE accepted the save, but storage did not confirm it in time.");
    } catch (err) {
      setError(err.message || "The document could not be saved.");
      setSaveNotice("Save failed");
      return false;
    } finally {
      setSaving(false);
    }
  }, [editor, editorReady, hasChanges, note, saving]);

  const handleBack = async () => {
    if (await saveChanges()) navigate("/approval-notes");
  };

  const handleDownload = async () => {
    if (!note || !(await saveChanges())) return;
    await approvalNotesApi.downloadNote(note.id, `${note.title}.docx`);
  };

  return (
    <AppShell
      shellClassName="app-shell--document-editor"
      contentClassName="content--document-editor"
    >
      <section className="panel document-editor">
        <div className="panel__head panel__head--row document-editor__head">
          <div>
            <h1 className="panel__title">{note ? note.title : "Approval Note"}</h1>
            <p className="panel__desc">
              Edit the generated copy on your letterhead. The master template remains unchanged.
            </p>
            <p className={`document-save-state ${hasChanges ? "document-save-state--dirty" : ""}`} role="status">
              {saving && <Spinner />} {saveNotice}
            </p>
          </div>
          <div className="row-actions">
            <button className="btn btn--ghost btn--sm" type="button" onClick={handleBack} disabled={!editorReady || saving}>
              <ArrowLeft size={15} aria-hidden="true" /> Back
            </button>
            <button className="btn btn--ghost btn--sm" type="button" onClick={saveChanges} disabled={!editorReady || saving}>
              <Save size={15} aria-hidden="true" /> Save
            </button>
            <button className="btn btn--sm btn--primary" type="button" onClick={handleDownload} disabled={!editorReady || saving || !note}>
              <Download size={15} aria-hidden="true" /> Download DOCX
            </button>
          </div>
        </div>

        {loading && <div className="ask__loading"><Spinner /> Opening editor...</div>}
        {error && (
          <div className="alert alert--error document-editor__error" role="alert">
            {error}
          </div>
        )}
        {!loading && editor && (
          <OnlyOfficeEditor
            apiJsUrl={editor.document_server_api_js}
            config={editor.config}
            onDirtyChange={handleDirtyChange}
            onReady={handleEditorReady}
            onError={(err) => setError(err.message)}
          />
        )}
      </section>
    </AppShell>
  );
}
