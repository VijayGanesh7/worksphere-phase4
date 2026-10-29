"""MODULE 22 - Resignation & Exit Management."""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_owner_or_staff, current_employee, get_current_user, require_staff, staff_users
from ..enums import ResignationStatus
from ..models import Resignation, User
from ..schemas import ResignationCreate, ResignationDecision, ResignationOut
from ..services.email_service import send_email_async
from ..services.notifications import notify

router = APIRouter(prefix="/api/resignations", tags=["Module 22 - Resignation & Exit"])


def _out(r: Resignation) -> ResignationOut:
    last_day = r.created_at.date() + timedelta(days=r.notice_period)
    today = date.today()
    if r.status == ResignationStatus.PENDING:
        stage, remaining = "UNDER_REVIEW", None
    elif r.status == ResignationStatus.REJECTED:
        stage, remaining = "REJECTED", None
    elif today <= last_day:
        stage, remaining = "SERVING_NOTICE", (last_day - today).days
    else:
        stage, remaining = "EXITED", 0
    return ResignationOut(
        id=r.id,
        employee_id=r.employee_id,
        employee_name=r.employee.full_name,
        reason=r.reason,
        notice_period=r.notice_period,
        status=r.status,
        created_at=r.created_at,
        last_working_day=last_day,
        days_remaining=remaining,
        exit_stage=stage,
    )


@router.post("", response_model=ResignationOut, status_code=status.HTTP_201_CREATED)
def submit_resignation(body: ResignationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = current_employee(user)
    open_one = db.scalar(
        select(Resignation).where(
            Resignation.employee_id == emp.id,
            Resignation.status.in_([ResignationStatus.PENDING, ResignationStatus.APPROVED]),
        )
    )
    if open_one:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an active resignation")
    r = Resignation(employee_id=emp.id, reason=body.reason, notice_period=body.notice_period)
    db.add(r)
    subject = "Resignation submitted"
    text = f"{emp.full_name} has submitted a resignation ({body.notice_period}-day notice). Please review it."
    emails = notify(db, [u for u in staff_users(db) if u.id != user.id], subject, text)
    db.commit()
    db.refresh(r)
    send_email_async(emails, subject, text)
    return _out(r)


@router.get("/me", response_model=List[ResignationOut])
def my_resignations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = current_employee(user)
    rows = db.scalars(select(Resignation).where(Resignation.employee_id == emp.id).order_by(Resignation.created_at.desc()))
    return [_out(r) for r in rows]


@router.get("", response_model=List[ResignationOut])
def list_resignations(
    status_filter: Optional[ResignationStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    q = select(Resignation).order_by(Resignation.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        q = q.where(Resignation.status == status_filter)
    return [_out(r) for r in db.scalars(q)]


@router.get("/{resignation_id}", response_model=ResignationOut)
def get_resignation(resignation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Resignation, resignation_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resignation not found")
    assert_owner_or_staff(user, r.employee_id)
    return _out(r)


@router.patch("/{resignation_id}/decision", response_model=ResignationOut)
def decide(
    resignation_id: int, body: ResignationDecision, db: Session = Depends(get_db), user: User = Depends(require_staff)
):
    r = db.get(Resignation, resignation_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resignation not found")
    if r.employee_id == (user.employee.id if user.employee else None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot decide your own resignation")
    if r.status != ResignationStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "This resignation has already been decided")
    r.status = body.status
    subject = f"Your resignation was {body.status.value.lower()}"
    text = f"Your resignation request has been {body.status.value.lower()} by HR."
    emails = notify(db, [r.employee.user], subject, text)
    db.commit()
    db.refresh(r)
    send_email_async(emails, subject, text)
    return _out(r)


@router.delete("/{resignation_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw(resignation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Resignation, resignation_id)
    emp = user.employee
    if r is None or emp is None or r.employee_id != emp.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resignation not found")
    if r.status != ResignationStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only pending resignations can be withdrawn")
    db.delete(r)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
