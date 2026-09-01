// Small inline loading indicator, and a full-page variant.
export default function Spinner({ full = false, label = "Loading…", small = false }) {
  const spinner = <span className={`spinner ${small ? "spinner--sm" : ""}`} aria-hidden="true" />;
  if (!full) return spinner;
  return (
    <div className="page-loader" role="status" aria-live="polite">
      {spinner}
      <p>{label}</p>
    </div>
  );
}
