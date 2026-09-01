"""Create the first administrator account.

Usage (interactive — prompts for a hidden password):
    python create_admin.py

Usage (non-interactive, e.g. for scripted local setup):
    python create_admin.py --name "Jane Admin" --email jane@example.com \
        --department Engineering
    # Password is still read from a hidden prompt unless --password is given.

No admin password is ever hard-coded. The account is created with
role=admin and status=approved.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select

from app.database import SessionLocal, init_db
from app.models.department import Department
from app.models.user import User, UserRole, UserStatus
from app.core.security import hash_password
from app.seed import seed_departments

MIN_PASSWORD_LENGTH = 8


def _resolve_department(db, value: str | None) -> Department | None:
    if value is None:
        return None
    # Accept either a numeric id or a department name.
    if value.isdigit():
        dept = db.get(Department, int(value))
    else:
        dept = db.scalar(
            select(Department).where(func.lower(Department.name) == value.strip().lower())
        )
    if dept is None:
        print(f"error: department {value!r} not found.", file=sys.stderr)
        sys.exit(2)
    return dept


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--name", help="Full name")
    parser.add_argument("--email", help="Email address")
    parser.add_argument("--password", help="Password (omit to be prompted securely)")
    parser.add_argument("--department", help="Department id or name (optional)")
    args = parser.parse_args()

    # Ensure schema + departments exist so an admin can be assigned one.
    init_db()
    db = SessionLocal()
    try:
        seed_departments(db)

        name = args.name or input("Full name: ").strip()
        email = (args.email or input("Email: ").strip()).lower()

        if not name or not email:
            print("error: name and email are required.", file=sys.stderr)
            sys.exit(2)

        existing = db.scalar(select(User).where(func.lower(User.email) == email))
        if existing is not None:
            print(f"error: a user with email {email!r} already exists.", file=sys.stderr)
            sys.exit(1)

        password = args.password
        if not password:
            password = getpass.getpass("Password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("error: passwords do not match.", file=sys.stderr)
                sys.exit(2)

        if len(password) < MIN_PASSWORD_LENGTH:
            print(
                f"error: password must be at least {MIN_PASSWORD_LENGTH} characters.",
                file=sys.stderr,
            )
            sys.exit(2)

        department = _resolve_department(db, args.department)

        admin = User(
            full_name=name,
            email=email,
            password_hash=hash_password(password),
            department_id=department.id if department else None,
            role=UserRole.admin,
            status=UserStatus.approved,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        dept_label = department.name if department else "(none)"
        print(
            f"Admin created: id={admin.id} email={admin.email} "
            f"role={admin.role.value} department={dept_label}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
