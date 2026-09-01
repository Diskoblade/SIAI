import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import AuthLayout from "../components/AuthLayout.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo = location.state?.from?.pathname || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err.message || "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthLayout heading="Sign in" sub="Access your department's secure knowledge base.">
      <form className="form" onSubmit={handleSubmit} noValidate>
        {error && <div className="alert alert--error" role="alert">{error}</div>}

        <label className="field">
          <span className="field__label">Email</span>
          <input
            type="email"
            className="field__input"
            value={email}
            autoComplete="username"
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@department.gov"
            required
          />
        </label>

        <label className="field">
          <span className="field__label">Password</span>
          <div className="field__password">
            <input
              type={showPassword ? "text" : "password"}
              className="field__input"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
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

        <button type="submit" className="btn btn--primary btn--block" disabled={submitting}>
          {submitting ? "Signing in…" : "Log in"}
        </button>
      </form>

      <p className="auth__foot">
        Don&apos;t have an account? <Link to="/signup">Create one</Link>
      </p>
    </AuthLayout>
  );
}
