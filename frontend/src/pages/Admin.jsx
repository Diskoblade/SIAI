import { useCallback, useEffect, useMemo, useState } from "react";
import AppShell from "../components/AppShell.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Spinner from "../components/Spinner.jsx";
import { adminApi, departmentsApi } from "../services/auth.js";

const STATUS_FILTERS = ["all", "pending", "approved", "rejected", "disabled"];
const ROLES = ["user", "manager", "admin"];

export default function Admin() {
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState("");

  const deptById = useMemo(() => {
    const m = new Map();
    departments.forEach((d) => m.set(d.id, d.name));
    return m;
  }, [departments]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await adminApi.listUsers(filter === "all" ? "" : filter);
      setUsers(list);
    } catch (err) {
      setError(err.message || "Could not load users.");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    departmentsApi.list().then(setDepartments).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const patch = async (userId, changes) => {
    setBusyId(userId);
    setNotice("");
    setError("");
    try {
      const updated = await adminApi.updateUser(userId, changes);
      setNotice(`Updated ${updated.email}.`);
      // Reflect the change locally; if it no longer matches the filter, reload.
      await load();
    } catch (err) {
      setError(err.message || "Update failed.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppShell>
        <PageHeader
          code="ACCESS_CONTROL / USER_REGISTRY"
          title="User administration"
          description="Approve access, assign departments, and manage roles through server-authorized controls."
        />
        <section className="panel">
          <div className="panel__head panel__head--row">
            <div>
              <h2 className="panel__title">User registry</h2>
              <p className="panel__desc">Filter and update organizational identities.</p>
            </div>
            <div className="filters">
              {STATUS_FILTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`chip ${filter === s ? "chip--active" : ""}`}
                  onClick={() => setFilter(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {notice && <div className="alert alert--success" role="status">{notice}</div>}
          {error && <div className="alert alert--error" role="alert">{error}</div>}

          {loading ? (
            <div className="ask__loading"><Spinner /> Loading users…</div>
          ) : users.length === 0 ? (
            <p className="empty">No users match this filter.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Department</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className={busyId === u.id ? "row--busy" : ""}>
                      <td>{u.full_name}</td>
                      <td className="cell--muted">{u.email}</td>
                      <td>
                        <select
                          className="mini-select"
                          value={u.department_id ?? ""}
                          disabled={busyId === u.id}
                          onChange={(e) =>
                            patch(u.id, { department_id: Number(e.target.value) })
                          }
                        >
                          <option value="" disabled>
                            Unassigned
                          </option>
                          {departments.map((d) => (
                            <option key={d.id} value={d.id}>
                              {d.name}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          className="mini-select"
                          value={u.role}
                          disabled={busyId === u.id}
                          onChange={(e) => patch(u.id, { role: e.target.value })}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <span className={`badge badge--${u.status}`}>{u.status}</span>
                      </td>
                      <td className="cell--muted">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="btn btn--sm btn--success"
                            disabled={busyId === u.id || u.status === "approved"}
                            onClick={() => patch(u.id, { status: "approved" })}
                          >
                            Approve
                          </button>
                          <button
                            className="btn btn--sm btn--warn"
                            disabled={busyId === u.id || u.status === "rejected"}
                            onClick={() => patch(u.id, { status: "rejected" })}
                          >
                            Reject
                          </button>
                          <button
                            className="btn btn--sm btn--danger"
                            disabled={busyId === u.id || u.status === "disabled"}
                            onClick={() => patch(u.id, { status: "disabled" })}
                          >
                            Disable
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
    </AppShell>
  );
}
