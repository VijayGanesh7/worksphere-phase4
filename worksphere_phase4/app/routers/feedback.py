"""MODULE 26 - Employee Feedback System."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_employee, get_current_user, require_staff
from ..models import Feedback, User
from ..schemas import FeedbackCreate, FeedbackOut, FeedbackStats

router = APIRouter(prefix="/api/feedback", tags=["Module 26 - Feedback"])


def _out(f: Feedback) -> FeedbackOut:
    return FeedbackOut(
        id=f.id,
        employee_id=f.employee_id,
        employee_name=f.employee.full_name,
        message=f.message,
        rating=f.rating,
        created_at=f.created_at,
    )


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def submit_feedback(body: FeedbackCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    f = Feedback(employee_id=current_employee(user).id, message=body.message, rating=body.rating)
    db.add(f)
    db.commit()
    db.refresh(f)
    return _out(f)


@router.get("/me", response_model=List[FeedbackOut])
def my_feedback(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(Feedback).where(Feedback.employee_id == current_employee(user).id).order_by(Feedback.created_at.desc())
    )
    return [_out(f) for f in rows]


@router.get("/stats", response_model=FeedbackStats)
def stats(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    counts = dict(db.execute(select(Feedback.rating, func.count()).group_by(Feedback.rating)).all())
    total = sum(counts.values())
    avg = sum(r * c for r, c in counts.items()) / total if total else 0.0
    return FeedbackStats(
        count=total, average_rating=round(avg, 2), distribution={str(i): counts.get(i, 0) for i in range(1, 6)}
    )


@router.get("", response_model=List[FeedbackOut])
def list_feedback(
    rating: Optional[int] = Query(None, ge=1, le=5),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
):
    q = select(Feedback).order_by(Feedback.created_at.desc(), Feedback.id.desc()).limit(limit).offset(offset)
    if rating:
        q = q.where(Feedback.rating == rating)
    return [_out(f) for f in db.scalars(q)]
