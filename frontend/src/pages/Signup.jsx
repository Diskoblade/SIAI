import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout from "../components/AuthLayout.jsx";
import Spinner from "../components/Spinner.jsx";
import { authApi, departmentsApi } from "../services/auth.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Signup() {
  const [departments, setDepartments] = useState([]);
  const [deptLoading, setDeptLoading] = useState(true);
  const [deptError, setDeptError] = useState("");

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm: "",
    department_id: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    departmentsApi
      .list()
      .then(setDepartments)
      .catch(() => setDeptError("Could not load departments. Is the backend running?"))
      .finally(() => setDeptLoading(false));
  }, []);

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const validate = () => {
    if (!form.full_name.trim()) return "Full name is required.";
    if (!EMAIL_RE.test(form.email.trim())) return "Please enter a valid email address.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    if (form.password !== form.confirm) return "Passwords do not match.";
    if (!form.department_id) return "Please select a department.";
    return "";
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    setSubmitting(true);
    try {
      await authApi.signup({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        department_id: Number(form.department_id),
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message || "Could not create your account.");
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <AuthLayout heading="Account created" sub="One more step before you can sign in.">
        <div className="alert alert--success" role="status">
          <strong>Account created successfully.</strong>
          <br />
          Your account is waiting for administrator approval. You&apos;ll be able to log in
          once an administrator reviews and approves your access.
        </div>
        <p className="auth__foot">
          <Link to="/login">Return to sign in</Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout heading="Create account" sub="Request access to your department's knowledge base.">
      <form className="form" onSubmit={handleSubmit} noValidate>
        {error && <div className="alert alert--error" role="alert">{error}</div>}
        {deptError && <div className="alert alert--error" role="alert">{deptError}</div>}

        <label className="field">
          <span className="field__label">Full name</span>
          <input
            type="text"
            className="field__input"
            value={form.full_name}
            onChange={update("full_name")}
            placeholder="Rahul Kumar"
            required
          />
        </label>

        <label className="field">
          <span className="field__label">Email</span>
          <input
            type="email"
            className="field__input"
            value={form.email}
            autoComplete="email"
            onChange={update("email")}
            placeholder="you@department.gov"
            required
          />
        </label>

        <div className="field-row">
          <label className="field">
            <span className="field__label">Password</span>
            <div className="field__password">
              <input
                type={showPassword ? "text" : "password"}
                className="field__input"
                value={form.password}
                autoComplete="new-password"
                onChange={update("password")}
                placeholder="Min. 8 characters"
                required
              />
              <button
                type="button"
                className="field__toggle"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <label className="field">
            <span className="field__label">Confirm password</span>
            <input
              type={showPassword ? "text" : "password"}
              className="field__input"
              value={form.confirm}
              autoComplete="new-password"
              onChange={update("confirm")}
              placeholder="Re-enter password"
              required
            />
          </label>
        </div>

        <label className="field">
          <span className="field__label">Requested department</span>
          {deptLoading ? (
            <div className="field__loading"><Spinner small /> Loading departments…</div>
          ) : (
            <select
              className="field__input"
              value={form.department_id}
              onChange={update("department_id")}
              required
            >
              <option value="" disabled>
                Select a department
              </option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
          <span className="field__hint">
            Your request will be reviewed. An administrator confirms or adjusts your department
            before access is granted.
          </span>
        </label>

        <button
          type="submit"
          className="btn btn--primary btn--block"
          disabled={submitting || deptLoading}
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="auth__foot">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </AuthLayout>
  );
}
