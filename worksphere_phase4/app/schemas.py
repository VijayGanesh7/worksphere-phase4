"""Pydantic request/response models. Every input is validated and length-limited here."""
import re
from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .enums import ResignationStatus, Role, TaskStatus

Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9+()\-\s]{7,20}$")]


def check_password_strength(value: str) -> str:
    if len(value) < 8 or len(value) > 128:
        raise ValueError("Password must be 8-128 characters long")
    if not (re.search(r"[a-z]", value) and re.search(r"[A-Z]", value) and re.search(r"\d", value)):
        raise ValueError("Password must contain upper-case, lower-case and a digit")
    return value


StrongPassword = Annotated[str, AfterValidator(check_password_strength)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: Email
    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserOut(BaseModel):
    id: int
    email: str
    role: Role
    is_active: bool
    employee_id: Optional[int] = None
    full_name: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterRequest(BaseModel):
    email: Email
    password: StrongPassword
    full_name: Name
    role: Role = Role.EMPLOYEE
    department: Optional[ShortText] = None
    designation: Optional[ShortText] = None
    phone: Optional[Phone] = None


class DirectoryEntry(BaseModel):
    id: int
    full_name: str
    department: Optional[str] = None


# ---------- Module 21: Onboarding ----------
class OnboardingCreate(BaseModel):
    employee_id: Annotated[int, Field(gt=0)]
    task_name: ShortText
    due_date: date

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("due_date cannot be in the past")
        return v


class OnboardingStatusUpdate(BaseModel):
    status: TaskStatus


class OnboardingOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    task_name: str
    status: TaskStatus
    due_date: date
    is_overdue: bool


class OnboardingProgress(BaseModel):
    employee_id: int
    total: int
    completed: int
    pending: int
    percent: int


# ---------- Module 22: Resignation ----------
class ResignationCreate(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)]
    notice_period: Annotated[int, Field(ge=0, le=180, description="Notice period in days")]


class ResignationDecision(BaseModel):
    status: ResignationStatus

    @field_validator("status")
    @classmethod
    def decision_only(cls, v: ResignationStatus) -> ResignationStatus:
        if v == ResignationStatus.PENDING:
            raise ValueError("status must be APPROVED or REJECTED")
        return v


class ResignationOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    reason: str
    notice_period: int
    status: ResignationStatus
    created_at: datetime
    last_working_day: date
    days_remaining: Optional[int] = None
    exit_stage: str  # UNDER_REVIEW | SERVING_NOTICE | EXITED | REJECTED


# ---------- Module 23: Announcements ----------
class AnnouncementCreate(BaseModel):
    title: ShortText
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class AnnouncementUpdate(BaseModel):
    title: Optional[ShortText] = None
    message: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]] = None


class AnnouncementOut(BaseModel):
    id: int
    title: str
    message: str
    created_by: int
    created_by_name: str
    created_at: datetime


# ---------- Module 24: Tasks ----------
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class TaskCreate(BaseModel):
    assigned_to: Annotated[int, Field(gt=0, description="Employee id")]
    title: ShortText
    description: Optional[Description] = None
    due_date: date

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("due_date cannot be in the past")
        return v


class TaskUpdate(BaseModel):
    title: Optional[ShortText] = None
    description: Optional[Description] = None
    due_date: Optional[date] = None
    assigned_to: Optional[Annotated[int, Field(gt=0)]] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskOut(BaseModel):
    id: int
    assigned_to: int
    assignee_name: str
    title: str
    description: Optional[str] = None
    due_date: date
    status: TaskStatus
    is_overdue: bool


class TaskSummary(BaseModel):
    total: int
    pending: int
    completed: int
    overdue: int


# ---------- Module 25: Integrations ----------
class CalendarEvent(BaseModel):
    uid: str
    title: str
    date: date
    kind: str
    google_calendar_url: str


class IntegrationStatus(BaseModel):
    email_enabled: bool
    reports: List[str]
    formats: List[str]


# ---------- Module 26: Feedback ----------
class FeedbackCreate(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    rating: Annotated[int, Field(ge=1, le=5)]


class FeedbackOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    message: str
    rating: int
    created_at: datetime


class FeedbackStats(BaseModel):
    count: int
    average_rating: float
    distribution: dict  # {"1": n, ... "5": n}


# ---------- Module 27: Profile & settings ----------
class ProfileOut(BaseModel):
    user_id: int
    email: str
    role: Role
    employee_id: Optional[int] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    date_joined: Optional[date] = None


class ProfileUpdate(BaseModel):
    full_name: Optional[Name] = None
    phone: Optional[Phone] = None


class PasswordChange(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: StrongPassword


class PreferencesOut(ORM):
    email_notifications: bool
    in_app_notifications: bool
    announcement_alerts: bool
    task_alerts: bool


class PreferencesUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    in_app_notifications: Optional[bool] = None
    announcement_alerts: Optional[bool] = None
    task_alerts: Optional[bool] = None
