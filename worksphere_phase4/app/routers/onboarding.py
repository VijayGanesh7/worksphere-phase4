"""MODULE 21 - Employee Onboarding System."""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    assert_owner_or_staff,
    current_employee,
    get_current_user,
    get_employee_or_404,
    is_staff,
    require_staff,
)
from ..enums import TaskStatus
from ..models import Employee, Onboarding, User
from ..schemas import OnboardingCreate, OnboardingOut, OnboardingProgress, OnboardingStatusUpdate
from ..services.email_service import send_email_async
from ..services.notifications import notify

router = APIRouter(prefix="/api/onboarding", tags=["Module 21 - Onboarding"])

# (task name, due in N days)
DEFAULT_CHECKLIST = [
    ("Sign and return the offer letter", 1),
    ("Upload ID and address proof", 3),
    ("Complete bank and tax details", 5),
    ("Set up work email and accounts", 2),
    ("Read the employee handbook", 7),
    ("Meet your manager and onboarding buddy", 3),
    ("Complete compliance training", 14),
]


def _out(t: Onboarding) -> OnboardingOut:
    return OnboardingOut(
        id=t.id,
        employee_id=t.employee_id,
        employee_name=t.employee.full_name,
        task_name=t.task_name,
        status=t.status,
        due_date=t.due_date,
        is_overdue=t.status == TaskStatus.PENDING and t.due_date < date.today(),
    )


def _progress(db: Session, employee_id: int) -> OnboardingProgress:
    total = db.scalar(select(func.count()).select_from(Onboarding).where(Onboarding.employee_id == employee_id)) or 0
    done = (
        db.scalar(
            select(func.count())
            .select_from(Onboarding)
            .where(Onboarding.employee_id == employee_id, Onboarding.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    return OnboardingProgress(
        employee_id=employee_id,
        total=total,
        completed=done,
        pending=total - done,
        percent=round(done * 100 / total) if total else 0,
    )


def create_default_checklist(db: Session, employee: Employee) -> List[Onboarding]:
    """Adds the standard checklist, skipping tasks the employee already has. Caller commits."""
    existing = set(db.scalars(select(Onboarding.task_name).where(Onboarding.employee_id == employee.id)))
    created = []
    for name, days in DEFAULT_CHECKLIST:
        if name in existing:
            continue
        item = Onboarding(
            employee_id=employee.id, task_name=name, due_date=date.today() + timedelta(days=days)
        )
        db.add(item)
        created.append(item)
    return created


@router.post("", response_model=OnboardingOut, status_code=status.HTTP_201_CREATED)
def assign_task(body: OnboardingCreate, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    emp = get_employee_or_404(db, body.employee_id)
    item = Onboarding(employee_id=emp.id, task_name=body.task_name, due_date=body.due_date)
    db.add(item)
    emails = notify(db, [emp.user], "New onboarding task", f"{body.task_name} (due {body.due_date})")
    db.commit()
    db.refresh(item)
    send_email_async(emails, "New onboarding task", f"{body.task_name} (due {body.due_date})")
    return _out(item)


@router.post(
    "/employee/{employee_id}/default-checklist", response_model=List[OnboardingOut], status_code=status.HTTP_201_CREATED
)
def assign_default_checklist(employee_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    emp = get_employee_or_404(db, employee_id)
    items = create_default_checklist(db, emp)
    if items:
        notify(db, [emp.user], "Onboarding checklist assigned", f"{len(items)} onboarding tasks are waiting for you.")
    db.commit()
    for i in items:
        db.refresh(i)
    return [_out(i) for i in items]


@router.get("/me", response_model=List[OnboardingOut])
def my_checklist(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = current_employee(user)
    rows = db.scalars(select(Onboarding).where(Onboarding.employee_id == emp.id).order_by(Onboarding.due_date, Onboarding.id))
    return [_out(r) for r in rows]


@router.get("/me/progress", response_model=OnboardingProgress)
def my_progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _progress(db, current_employee(user).id)


@router.get("", response_model=List[OnboardingOut])
def list_all(
    employee_id: Optional[int] = None,
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    q = select(Onboarding).order_by(Onboarding.due_date, Onboarding.id).limit(limit).offset(offset)
    if employee_id:
        q = q.where(Onboarding.employee_id == employee_id)
    if status_filter:
        q = q.where(Onboarding.status == status_filter)
    return [_out(r) for r in db.scalars(q)]


@router.get("/employee/{employee_id}", response_model=List[OnboardingOut])
def employee_checklist(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_owner_or_staff(user, employee_id)
    get_employee_or_404(db, employee_id)
    rows = db.scalars(select(Onboarding).where(Onboarding.employee_id == employee_id).order_by(Onboarding.due_date, Onboarding.id))
    return [_out(r) for r in rows]


@router.get("/employee/{employee_id}/progress", response_model=OnboardingProgress)
def employee_progress(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_owner_or_staff(user, employee_id)
    get_employee_or_404(db, employee_id)
    return _progress(db, employee_id)


@router.patch("/{task_id}/status", response_model=OnboardingOut)
def update_status(
    task_id: int, body: OnboardingStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    item = db.get(Onboarding, task_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding task not found")
    assert_owner_or_staff(user, item.employee_id)
    item.status = body.status
    db.commit()
    db.refresh(item)
    return _out(item)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    item = db.get(Onboarding, task_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Onboarding task not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
