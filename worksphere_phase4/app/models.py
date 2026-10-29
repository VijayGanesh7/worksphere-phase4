"""SQLAlchemy models.

Phase 4 adds: Onboarding, Resignation, Announcement, Task, Feedback (+ UserPreference for Module 27).
User, Employee and Notification are the Phase 1-3 tables the new modules depend on; if your existing
project already defines them, keep yours and just make sure the column names used here exist.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .enums import ResignationStatus, Role, TaskStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(e):
    return Enum(e, native_enum=False, length=20)


# ---------------- Existing tables (Phase 1-3) ----------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role), default=Role.EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    employee: Mapped[Optional["Employee"]] = relationship(back_populates="user", uselist=False)
    preferences: Mapped[Optional["UserPreference"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.employee.full_name if self.employee else self.email


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    date_joined: Mapped[date] = mapped_column(Date, default=date.today)

    user: Mapped[User] = relationship(back_populates="employee")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ---------------- New tables (Phase 4) ----------------
class Onboarding(Base):
    __tablename__ = "onboarding"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    task_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.PENDING, index=True)
    due_date: Mapped[date] = mapped_column(Date)

    employee: Mapped[Employee] = relationship()


class Resignation(Base):
    __tablename__ = "resignations"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    notice_period: Mapped[int] = mapped_column(Integer)  # days
    status: Mapped[ResignationStatus] = mapped_column(
        _enum(ResignationStatus), default=ResignationStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    employee: Mapped[Employee] = relationship()


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    creator: Mapped[User] = relationship()


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    assigned_to: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.PENDING, index=True)

    assignee: Mapped[Employee] = relationship()


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    employee: Mapped[Employee] = relationship()


class UserPreference(Base):
    """Notification preferences (Module 27)."""

    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    in_app_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    announcement_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    task_alerts: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="preferences")
