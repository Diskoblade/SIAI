"""Seed a few sample documents across departments (demo / manual testing).

Includes department-only, common, and shared (multi-department) documents so
cross-department isolation can be demonstrated. Idempotent by title.
"""

from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models.document import Document
from app.rag import ingestion

# (title, access_scope, department_slug_for_owner, text)
SAMPLE_DOCS: list[tuple[str, list[str], str | None, str]] = [
    (
        "Finance Approval Policy 2026",
        ["finance"],
        "finance",
        "Approval Limits\n\n"
        "Infrastructure projects require administrative approval. The financial "
        "sanction limit for a departmental officer is set at five crore rupees. "
        "Expenditure above this project expenditure threshold must be escalated "
        "to the finance controller for delegation of financial powers.",
    ),
    (
        "HR Leave and Conduct Policy 2026",
        ["hr"],
        "hr",
        "Leave Policy\n\n"
        "Employees are entitled to thirty days of earned leave per year. "
        "Disciplinary conduct matters are handled confidentially by the HR "
        "department and are not shared with other departments.",
    ),
    (
        "Legal Contract Review Guidelines",
        ["legal"],
        "legal",
        "Contract Clauses\n\n"
        "All third-party contracts must include an indemnity clause and a "
        "termination-for-convenience clause reviewed by the legal department.",
    ),
    (
        "Engineering Deployment Standard",
        ["engineering"],
        "engineering",
        "Deployment Process\n\n"
        "Production deployments require a signed change request, a passing test "
        "suite, and a rollback plan approved by the engineering lead.",
    ),
    (
        "Employee Code of Conduct (Common)",
        ["common"],
        None,
        "Code of Conduct\n\n"
        "All personnel across every department must act with integrity, protect "
        "confidential information, and follow the organization's security policy.",
    ),
    (
        "Finance-Legal Procurement Compliance (Shared)",
        ["finance", "legal"],
        "finance",
        "Procurement Compliance\n\n"
        "Procurement above the approval limit requires joint sign-off from the "
        "finance and legal departments to ensure contractual and financial "
        "compliance before award.",
    ),
]


def seed_sample_documents(db) -> int:
    created = 0
    for title, scope, dept_slug, text in SAMPLE_DOCS:
        if db.scalar(select(Document).where(Document.title == title)) is not None:
            continue
        owner_dept_id = _department_id_for_slug(db, dept_slug) if dept_slug else None
        ingestion.ingest_text(
            db,
            title=title,
            text=text,
            access_scope=scope,
            owner_department_id=owner_dept_id,
        )
        created += 1
    return created


def _department_id_for_slug(db, slug: str) -> int | None:
    from app.models.department import Department
    from app.services.authorization_service import department_scope

    for dept in db.scalars(select(Department)):
        if department_scope(dept) == slug:
            return dept.id
    return None


def run() -> None:
    init_db()
    db = SessionLocal()
    try:
        created = seed_sample_documents(db)
        print(f"Sample documents: {created} created.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
