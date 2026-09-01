import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Calculator,
  Download,
  FileSignature,
  MessageSquare,
  Plus,
  Presentation,
  Send,
  Trash2,
} from "lucide-react";
import AppShell from "../components/AppShell.jsx";
import Spinner from "../components/Spinner.jsx";
import { conversationsApi, ragApi } from "../services/auth.js";
import { approvalNotesApi } from "../services/approvalNotes.js";
import { downloadPresentation } from "../utils/presentation.js";

const REPORT_PARAM_KEYS = ["Amount", "Vendor", "Subject", "Justification", "Department", "Timeline"];

function ReportArtifact({ report }) {
  const navigate = useNavigate();
  const [typeId, setTypeId] = useState(report.matched_type_id ? String(report.matched_type_id) : "");
  const [title, setTitle] = useState(report.suggested_title || "");
  const [params, setParams] = useState(report.suggested_parameters || {});
  const [generating, setGenerating] = useState(false);
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  if (report.status === "unavailable") {
    return (
      <div className="report-artifact report-artifact--muted">
        <FileSignature size={18} aria-hidden="true" /> {report.prompt}
      </div>
    );
  }

  // Merge suggested params with the standard keys so all fields are offered.
  const keys = Array.from(new Set([...Object.keys(params), ...REPORT_PARAM_KEYS]));

  const generate = async () => {
    setError("");
    if (!typeId) return setError("Please choose an Approval Note type.");
    setGenerating(true);
    try {
      const cleanParams = Object.fromEntries(
        Object.entries(params).filter(([, v]) => v && String(v).trim())
      );
      const note = await approvalNotesApi.createNote({
        approval_note_type_id: Number(typeId),
        title: title.trim() || undefined,
        parameters: cleanParams,
      });
      setCreated(note);
    } catch (err) {
      setError(err.message || "Could not generate the Approval Note.");
    } finally {
      setGenerating(false);
    }
  };

  if (created) {
    return (
      <div className="report-artifact">
        <div className="report-artifact__head">
          <FileSignature size={20} strokeWidth={1.8} />
          <div>
            <strong>{created.title}</strong>
            <span>Approval Note ready | v{created.document_version} | opens in ONLYOFFICE</span>
          </div>
        </div>
        <div className="row-actions">
          <button className="btn btn--primary btn--sm" onClick={() => navigate(`/approval-notes/${created.id}/edit`)}>
            Open in editor
          </button>
          <button className="btn btn--sm" onClick={() => approvalNotesApi.downloadNote(created.id, `${created.title}.docx`)}>
            Download DOCX
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="report-artifact">
      <div className="report-artifact__head">
        <FileSignature size={20} strokeWidth={1.8} />
        <div><strong>Create Approval Note</strong><span>Confirm the details, then generate the document.</span></div>
      </div>
      {error && <div className="alert alert--error" role="alert">{error}</div>}
      <label className="field">
        <span className="field__label">Type</span>
        <select className="field__input" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
          <option value="" disabled>Select a type...</option>
          {report.available_types.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span className="field__label">Title</span>
        <input className="field__input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to the type name" />
      </label>
      <div className="field-row report-artifact__params">
        {keys.map((k) => (
          <label className="field" key={k}>
            <span className="field__label">{k}</span>
            <input className="field__input" value={params[k] || ""} onChange={(e) => setParams((p) => ({ ...p, [k]: e.target.value }))} />
          </label>
        ))}
      </div>
      <button className="btn btn--primary" onClick={generate} disabled={generating}>
        {generating ? <><Spinner /> Generating...</> : <><FileSignature size={16} aria-hidden="true" /> Generate Approval Note</>}
      </button>
    </div>
  );
}

function sourceLabel(message) {
  if (message.answer_source === "calculation") return "Calculated with fluids";
  if (message.answer_source === "general_knowledge") return "General model knowledge";
  if (message.answer_source === "unavailable") return "No answer source";
  return "Authorized knowledge";
}

function CalculationArtifact({ calculation }) {
  if (!calculation) return null;
  return (
    <div className="calculation-artifact">
      <div className="calculation-artifact__head">
        <span className="calculation-artifact__icon" aria-hidden="true">
          <Calculator size={20} strokeWidth={1.8} />
        </span>
        <div>
          <strong>{calculation.title}</strong>
          <span>fluids {calculation.library_version} | SI units</span>
        </div>
      </div>
      {calculation.outputs.length > 0 && (
        <dl className="calculation-results">
          {calculation.outputs.map((output) => (
            <div key={output.key}>
              <dt>{output.label}</dt>
              <dd>
                {Number(output.value).toLocaleString(undefined, { maximumSignificantDigits: 8 })}
                {output.unit ? ` ${output.unit}` : ""}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function AssistantMessage({ message, downloading, onDownload }) {
  const usesGeneralKnowledge = message.answer_source === "general_knowledge";
  const unavailable = message.answer_source === "unavailable";
  const calculation = message.answer_source === "calculation";
  return (
    <article className="chat-message chat-message--assistant">
      <div className="chat-message__meta">
        <span>SI / RESPONSE</span>
        <span className={`chat-source ${usesGeneralKnowledge ? "chat-source--general" : ""} ${calculation ? "chat-source--calculation" : ""}`}>
          {sourceLabel(message)}
        </span>
        {message.evidence_status && !calculation && (
          <span className={`badge badge--${message.evidence_status === "sufficient" ? "approved" : "pending"}`}>
            {message.evidence_status}
          </span>
        )}
      </div>
      <p className="chat-message__content">{message.content}</p>

      <CalculationArtifact calculation={message.calculation} />

      {message.report && <ReportArtifact report={message.report} />}

      {message.presentation && (
        <div className="presentation-artifact">
          <div className="presentation-artifact__icon" aria-hidden="true">
            <Presentation size={22} strokeWidth={1.8} />
          </div>
          <div className="presentation-artifact__body">
            <strong>{message.presentation.title}</strong>
            <span>
              {message.presentation.slide_count} slides | PowerPoint | {message.presentation.source_mode === "general_knowledge" ? "General knowledge" : "Authorized sources"}
            </span>
          </div>
          <button
            type="button"
            className="btn btn--primary presentation-artifact__download"
            onClick={() => onDownload(message)}
            disabled={downloading}
          >
            {downloading ? <Spinner /> : <Download size={17} aria-hidden="true" />}
            {downloading ? "Generating..." : "Download .pptx"}
          </button>
        </div>
      )}

      {message.citations?.length > 0 ? (
        <div className="sources">
          <div className="sources__title">Sources</div>
          <ul className="sources__list">
            {message.citations.map((citation) => (
              <li key={citation.citation_id}>
                <span className="sources__tag">{citation.citation_id}</span>
                {citation.title}
                {citation.page != null ? ` - Page ${citation.page}` : ""}
                {citation.section ? ` | ${citation.section}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : !calculation && (
        <p className="answer__note">
          {usesGeneralKnowledge
            ? "No matching authorized document was found. Verify important facts."
            : unavailable
              ? "No matching document was found and no general-knowledge LLM is configured."
              : "No validated document citations were produced for this answer."}
        </p>
      )}
    </article>
  );
}

export default function Dashboard() {
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState(null);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [error, setError] = useState("");
  const [downloadError, setDownloadError] = useState("");
  const chatScrollRef = useRef(null);

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const [providerStatus, existing] = await Promise.all([
          ragApi.status().catch(() => null),
          conversationsApi.list(),
        ]);
        if (!active) return;
        setStatus(providerStatus);
        let sessions = existing;
        if (sessions.length === 0) {
          const created = await conversationsApi.create();
          sessions = [created];
        }
        if (!active) return;
        setConversations(sessions);
        setActiveId(sessions[0].id);
      } catch (err) {
        if (active) setError(err.message || "Conversations could not be loaded.");
      } finally {
        if (active) setLoadingConversations(false);
      }
    }
    initialize();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!activeId) return;
    let active = true;
    setLoadingMessages(true);
    setError("");
    conversationsApi.messages(activeId)
      .then((items) => { if (active) setMessages(items); })
      .catch((err) => { if (active) setError(err.message || "Messages could not be loaded."); })
      .finally(() => { if (active) setLoadingMessages(false); });
    return () => { active = false; };
  }, [activeId]);

  useEffect(() => {
    const scroller = chatScrollRef.current;
    if (!scroller) return;
    scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const createConversation = async () => {
    setCreating(true);
    setError("");
    try {
      const created = await conversationsApi.create();
      setConversations((current) => [created, ...current]);
      setMessages([]);
      setActiveId(created.id);
    } catch (err) {
      setError(err.message || "A new conversation could not be created.");
    } finally {
      setCreating(false);
    }
  };

  const deleteConversation = async (conversation) => {
    if (!window.confirm(`Delete "${conversation.title}" and all of its messages?`)) return;
    setDeletingId(conversation.id);
    setError("");
    try {
      await conversationsApi.delete(conversation.id);
      let remaining = conversations.filter((item) => item.id !== conversation.id);
      if (remaining.length === 0) {
        remaining = [await conversationsApi.create()];
      }
      setConversations(remaining);
      if (activeId === conversation.id) {
        setMessages([]);
        setActiveId(remaining[0].id);
      }
    } catch (err) {
      setError(err.message || "The conversation could not be deleted.");
    } finally {
      setDeletingId(null);
    }
  };

  const ask = async (event) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || !activeId || sending) return;
    setQuestion("");
    setError("");
    setDownloadError("");
    const pendingUser = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, pendingUser]);
    setSending(true);
    try {
      const response = await ragApi.query(text, activeId);
      const assistant = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        ...response,
      };
      setMessages((current) => [...current, assistant]);
      setConversations((current) => {
        const selected = current.find((item) => item.id === activeId);
        if (!selected) return current;
        const updated = {
          ...selected,
          title: response.conversation_title || selected.title,
          message_count: selected.message_count + 2,
          updated_at: new Date().toISOString(),
        };
        return [updated, ...current.filter((item) => item.id !== activeId)];
      });
    } catch (err) {
      setMessages((current) => current.filter((message) => message.id !== pendingUser.id));
      setQuestion(text);
      setError(err.message || "The message could not be completed.");
    } finally {
      setSending(false);
    }
  };

  const downloadSlides = async (message) => {
    setDownloadingId(message.id);
    setDownloadError("");
    try {
      await downloadPresentation(message.presentation);
    } catch (err) {
      setDownloadError(err.message || "The presentation could not be generated.");
    } finally {
      setDownloadingId(null);
    }
  };

  const activeConversation = conversations.find((item) => item.id === activeId);

  return (
    <AppShell shellClassName="app-shell--conversation" contentClassName="content--conversation">
        <section className="conversation-window">
          <aside className="conversation-sidebar">
            <div className="conversation-sidebar__head">
              <strong>Conversations</strong>
              <button
                type="button"
                className="btn btn--icon conversation-new"
                onClick={createConversation}
                disabled={creating || sending}
                aria-label="New conversation"
                title="New conversation"
              >
                {creating ? <Spinner /> : <Plus size={18} aria-hidden="true" />}
              </button>
            </div>
            <div className="conversation-list">
              {loadingConversations ? (
                <div className="conversation-list__loading"><Spinner /> Loading...</div>
              ) : conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`conversation-item ${conversation.id === activeId ? "conversation-item--active" : ""}`}
                >
                  <button
                    type="button"
                    className="conversation-item__select"
                    onClick={() => setActiveId(conversation.id)}
                    disabled={sending}
                  >
                    <MessageSquare size={16} aria-hidden="true" />
                    <span>
                      <strong>{conversation.title}</strong>
                      <small>{conversation.message_count} messages</small>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="conversation-item__delete"
                    onClick={() => deleteConversation(conversation)}
                    disabled={deletingId === conversation.id || sending}
                    aria-label={`Delete ${conversation.title}`}
                    title="Delete conversation"
                  >
                    {deletingId === conversation.id ? <Spinner /> : <Trash2 size={15} aria-hidden="true" />}
                  </button>
                </div>
              ))}
            </div>
          </aside>

          <div className="chat-pane">
            <header className="chat-pane__head">
              <div>
                <h1>{activeConversation?.title || "New conversation"}</h1>
                <span>SESSION / PRIVATE</span>
              </div>
              {status && (
                <span
                  className={`status-pill ${status.llm_configured ? "status-pill--live" : ""}`}
                  title={`LLM: ${status.llm_provider} | embeddings: ${status.embedding_provider} | store: ${status.vector_store}`}
                >
                  <span className="status-pill__dot" />
                  {status.mode}
                </span>
              )}
            </header>

            <div ref={chatScrollRef} className="chat-scroll" aria-live="polite">
              {loadingMessages ? (
                <div className="chat-empty"><Spinner /> Loading messages...</div>
              ) : messages.length === 0 ? (
                <div className="chat-empty">
                  <MessageSquare size={28} aria-hidden="true" />
                  <strong>No messages yet</strong>
                </div>
              ) : messages.map((message) => (
                message.role === "user" ? (
                  <article key={message.id} className="chat-message chat-message--user">
                    <div className="chat-message__meta"><span>QUERY / YOU</span></div>
                    <p className="chat-message__content">{message.content}</p>
                  </article>
                ) : (
                  <AssistantMessage
                    key={message.id}
                    message={message}
                    downloading={downloadingId === message.id}
                    onDownload={downloadSlides}
                  />
                )
              ))}
              {sending && (
                <div className="chat-typing"><Spinner /> Working on your request...</div>
              )}
              <div aria-hidden="true" />
            </div>

            <div className="chat-composer-wrap">
              {error && <div className="alert alert--error" role="alert">{error}</div>}
              {downloadError && <div className="alert alert--error" role="alert">{downloadError}</div>}
              <form className="chat-composer" onSubmit={ask}>
                <textarea
                  rows={2}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder="Ask a question..."
                  disabled={!activeId || loadingMessages || sending}
                  aria-label="Message"
                />
                <button
                  type="submit"
                  className="btn btn--primary chat-composer__send"
                  disabled={!question.trim() || !activeId || loadingMessages || sending}
                  aria-label="Send message"
                  title="Send message"
                >
                  {sending ? <Spinner /> : <Send size={18} aria-hidden="true" />}
                </button>
              </form>
            </div>
          </div>
        </section>
    </AppShell>
  );
}
