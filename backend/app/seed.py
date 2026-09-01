"""Idempotent department seeding.

Runs on startup (and can be run standalone). Inserts the standard departments
and their VectorDB collection names if they are not already present.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models.department import Department

# (name, vector_collection)
DEFAULT_DEPARTMENTS: list[tuple[str, str]] = [
    ("Finance", "dept_finance"),
    ("HR", "dept_hr"),
    ("Legal", "dept_legal"),
    ("Engineering", "dept_engineering"),
    ("Administration", "dept_administration"),
]


def seed_departments(db: Session) -> int:
    """Insert any missing default departments. Returns the number created."""
    created = 0
    for name, collection in DEFAULT_DEPARTMENTS:
        exists = db.scalar(select(Department).where(Department.name == name))
        if exists is None:
            db.add(Department(name=name, vector_collection=collection))
            created += 1
    if created:
        db.commit()
    return created


def run() -> None:
    """Entry point for `python -m app.seed`."""
    init_db()
    db = SessionLocal()
    try:
        created = seed_departments(db)
        print(f"Seed complete. {created} department(s) created.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
