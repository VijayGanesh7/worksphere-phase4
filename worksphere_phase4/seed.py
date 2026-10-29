"""Create tables and demo accounts.  Usage:  python seed.py

Passwords are never hard-coded: set SEED_ADMIN_PASSWORD in .env, or a random one is generated and printed once.
HR and employee demo accounts get random passwords that are printed once.
"""
import os
import secrets

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.enums import Role
from app.models import Employee, User, UserPreference
from app.routers.onboarding import create_default_checklist
from app.security import hash_password


def _pw() -> str:
    return secrets.token_urlsafe(9) + "aA1"  # satisfies the strength rule


def main() -> None:
    Base.metadata.create_all(bind=engine)
    accounts = [
        ("admin@worksphere.local", os.getenv("SEED_ADMIN_PASSWORD") or _pw(), Role.ADMIN, "Admin User", "Administration"),
        ("hr@worksphere.local", _pw(), Role.HR, "Helen HR", "Human Resources"),
        ("employee@worksphere.local", _pw(), Role.EMPLOYEE, "Eddie Employee", "Engineering"),
    ]
    with SessionLocal() as db:
        for email, password, role, name, dept in accounts:
            if db.scalar(select(User).where(User.email == email)):
                print(f"exists   {email}")
                continue
            user = User(email=email, hashed_password=hash_password(password), role=role)
            user.employee = Employee(full_name=name, department=dept, designation=role.value.title())
            user.preferences = UserPreference()
            db.add(user)
            db.flush()
            if role == Role.EMPLOYEE:
                create_default_checklist(db, user.employee)
            print(f"created  {email}  password: {password}")
        db.commit()
    print("\nSave these passwords now - they are not stored anywhere in plain text.")


if __name__ == "__main__":
    main()
