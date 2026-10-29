"""MODULE 25 - Third-party integrations: email, calendar, report export (CSV/PDF)."""
from datetime import date, timedelta
from typing import Callable, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import current_employee, get_current_user, require_roles, require_staff
from ..enums import ResignationStatus, Role, TaskStatus
from ..models import Announcement, Employee, Feedback, Onboarding, Resignation, Task, User
from ..schemas import CalendarEvent, IntegrationStatus
from ..services import calendar_service, exporters
from ..services.email_service import send_email

router = APIRouter(prefix="/api/integrations", tags=["Module 25 - Integrations"])


# ---------------- Reports ----------------
def _employees(db):
    rows = db.scalars(select(Employee).order_by(Employee.id))
    return ["ID", "Name", "Email", "Role", "Department", "Designation", "Phone", "Joined"], [
        [e.id, e.full_name, e.user.email, e.user.role.value, e.department, e.designation, e.phone, e.date_joined]
        for e in rows
    ]


def _onboarding(db):
    rows = db.scalars(select(Onboarding).order_by(Onboarding.employee_id, Onboarding.due_date))
    return ["ID", "Employee", "Task", "Status", "Due date"], [
        [r.id, r.employee.full_name, r.task_name, r.status.value, r.due_date] for r in rows
    ]


def _resignations(db):
    rows = db.scalars(select(Resignation).order_by(Resignation.created_at.desc()))
    return ["ID", "Employee", "Reason", "Notice (days)", "Status", "Submitted", "Last working day"], [
        [
            r.id,
            r.employee.full_name,
            r.reason,
            r.notice_period,
            r.status.value,
            r.created_at.date(),
            r.created_at.date() + timedelta(days=r.notice_period),
        ]
        for r in rows
    ]


def _tasks(db):
    rows = db.scalars(select(Task).order_by(Task.due_date))
    return ["ID", "Assigned to", "Title", "Status", "Due date"], [
        [t.id, t.assignee.full_name, t.title, t.status.value, t.due_date] for t in rows
    ]


def _feedback(db):
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()))
    return ["ID", "Employee", "Rating", "Message", "Submitted"], [
        [f.id, f.employee.full_name, f.rating, f.message, f.created_at.date()] for f in rows
    ]


def _announcements(db):
    rows = db.scalars(select(Announcement).order_by(Announcement.created_at.desc()))
    return ["ID", "Title", "Posted by", "Posted on"], [
        [a.id, a.title, a.creator.display_name, a.created_at.date()] for a in rows
    ]


REPORTS: Dict[str, Tuple[str, Callable]] = {
    "employees": ("Employee Directory", _employees),
    "onboarding": ("Onboarding Progress", _onboarding),
    "resignations": ("Resignations", _resignations),
    "tasks": ("Tasks", _tasks),
    "feedback": ("Employee Feedback", _feedback),
    "announcements": ("Announcements", _announcements),
}


@router.get("/status", response_model=IntegrationStatus)
def integration_status(_: User = Depends(get_current_user)):
    return IntegrationStatus(email_enabled=settings.email_enabled, reports=list(REPORTS), formats=["csv", "pdf"])


@router.get("/export/{report}")
def export_report(
    report: str,
    format: str = Query("csv", pattern="^(csv|pdf)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    if report not in REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown report. Choose one of: {', '.join(REPORTS)}")
    title, fetch = REPORTS[report]
    headers, rows = fetch(db)
    stamp = date.today().isoformat()
    if format == "csv":
        content, media = exporters.to_csv(headers, rows), "text/csv; charset=utf-8"
    else:
        content, media = exporters.to_pdf(title, headers, rows), "application/pdf"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="worksphere-{report}-{stamp}.{format}"'},
    )


# ---------------- Email ----------------
@router.post("/email/test")
def send_test_email(admin: User = Depends(require_roles(Role.ADMIN))):
    """Sends a test message to the calling admin's own address to verify SMTP settings."""
    sent = send_email([admin.email], "WorkSphere test email", "Your WorkSphere email integration works.")
    return {"email_enabled": settings.email_enabled, "sent": sent}


# ---------------- Calendar ----------------
def _events_for(db: Session, user: User) -> List[dict]:
    emp = current_employee(user)
    events: List[dict] = []
    for t in db.scalars(select(Task).where(Task.assigned_to == emp.id, Task.status == TaskStatus.PENDING)):
        events.append({"uid": f"task-{t.id}", "title": f"Task due: {t.title}", "date": t.due_date, "kind": "Task"})
    for o in db.scalars(select(Onboarding).where(Onboarding.employee_id == emp.id, Onboarding.status == TaskStatus.PENDING)):
        events.append({"uid": f"onb-{o.id}", "title": f"Onboarding: {o.task_name}", "date": o.due_date, "kind": "Onboarding"})
    for r in db.scalars(
        select(Resignation).where(Resignation.employee_id == emp.id, Resignation.status == ResignationStatus.APPROVED)
    ):
        events.append(
            {
                "uid": f"exit-{r.id}",
                "title": "Last working day",
                "date": r.created_at.date() + timedelta(days=r.notice_period),
                "kind": "Exit",
            }
        )
    events.sort(key=lambda e: e["date"])
    return events


@router.get("/calendar/events", response_model=List[CalendarEvent])
def calendar_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [
        CalendarEvent(
            uid=e["uid"],
            title=e["title"],
            date=e["date"],
            kind=e["kind"],
            google_calendar_url=calendar_service.google_calendar_url(e["title"], e["date"], "From WorkSphere HRMS"),
        )
        for e in _events_for(db, user)
    ]


@router.get("/calendar/ics")
def calendar_ics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Download an .ics file - import it into Google Calendar, Outlook or Apple Calendar."""
    return Response(
        content=calendar_service.build_ics(_events_for(db, user)),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="worksphere.ics"'},
    )
