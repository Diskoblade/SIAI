export default function PageHeader({ code, title, description, action = null }) {
  return (
    <header className="page-header">
      <div className="page-header__identity">
        <span className="page-header__code">{code}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
}
