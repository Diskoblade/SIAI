import { useEffect, useState } from "react";
import AppShell from "../components/AppShell.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Spinner from "../components/Spinner.jsx";
import { ragApi } from "../services/auth.js";

export default function Recent() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    ragApi
      .history()
      .then(setItems)
      .catch((err) => setError(err.message || "Could not load history."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <AppShell>
        <PageHeader
          code="AUDIT_LOG / QUERY_HISTORY"
          title="Recent activity"
          description="Your recent questions, answer source, and document usage."
        />
        <section className="panel">
          <div className="panel__head">
            <h2 className="panel__title">Query registry</h2>
            <p className="panel__desc">Chronological retrieval and response records.</p>
          </div>
          {loading ? (
            <div className="ask__loading"><Spinner /> Loading…</div>
          ) : error ? (
            <div className="alert alert--error">{error}</div>
          ) : items.length === 0 ? (
            <p className="empty">You haven&apos;t asked anything yet.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Question</th><th>Docs used</th><th>Source</th><th>When</th></tr>
                </thead>
                <tbody>
                  {items.map((it) => (
                    <tr key={it.id}>
                      <td>{it.question}</td>
                      <td className="cell--muted">{it.documents_count}</td>
                      <td>
                        <span className={`badge badge--${it.response_status === "sufficient" ? "approved" : "pending"}`}>
                          {it.response_status}
                        </span>
                      </td>
                      <td className="cell--muted">{new Date(it.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
    </AppShell>
  );
}
