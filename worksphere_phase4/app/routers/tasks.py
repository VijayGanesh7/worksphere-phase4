"""MODULE 24 - Task Assignment & Tracking (internal)."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_owner_or_staff, current_employee, get_current_user, get_employee_or_404, is_staff, require_staff
from ..enums import TaskStatus
from ..models import Task, User
from ..schemas import TaskCreate, TaskOut, TaskStatusUpdate, TaskSummary, TaskUpdate
from ..services.email_service import send_email_async
from ..services.notifications import notify

router = APIRouter(prefix="/api/tasks", tags=["Module 24 - Tasks"])


def _out(t: Task) -> TaskOut:
    return TaskOut(
        id=t.id,
        assigned_to=t.assigned_to,
        assignee_name=t.assignee.full_name,
        title=t.title,
        description=t.description,
        due_date=t.due_date,
        status=t.status,
        is_overdue=t.status == TaskStatus.PENDING and t.due_date < date.today(),
    )


def _summary(db: Session, employee_id: Optional[int]) -> TaskSummary:
    def count(*conds) -> int:
        q = select(func.count()).select_from(Task).where(*conds)
        if employee_id is not None:
            q = q.where(Task.assigned_to == employee_id)
        return db.scalar(q) or 0

    pending = count(Task.status == TaskStatus.PENDING)
    return TaskSummary(
        total=count(),
        pending=pending,
        completed=count(Task.status == TaskStatus.COMPLETED),
        overdue=count(Task.status == TaskStatus.PENDING, Task.due_date < date.today()),
    )


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def assign_task(body: TaskCreate, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    emp = get_employee_or_404(db, body.assigned_to)
    t = Task(assigned_to=emp.id, title=body.title, description=body.description, due_date=body.due_date)
    db.add(t)
    emails = notify(db, [emp.user], "New task assigned", f"{body.title} (due {body.due_date})", category="task")
    db.commit()
    db.refresh(t)
    send_email_async(emails, "New task assigned", f"{body.title} (due {body.due_date})")
    return _out(t)


@router.get("/summary", response_model=TaskSummary)
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """HR/Admin see organisation-wide numbers; employees see only their own."""
    return _summary(db, None if is_staff(user) else current_employee(user).id)


@router.get("/me", response_model=List[TaskOut])
def my_tasks(
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Task).where(Task.assigned_to == current_employee(user).id).order_by(Task.due_date, Task.id)
    if status_filter:
        q = q.where(Task.status == status_filter)
    return [_out(t) for t in db.scalars(q)]


@router.get("", response_model=List[TaskOut])
def list_tasks(
    assigned_to: Optional[int] = None,
    status_filter: Optional[TaskStatus] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Task).order_by(Task.due_date, Task.id).limit(limit).offset(offset)
    if is_staff(user):
        if assigned_to:
            q = q.where(Task.assigned_to == assigned_to)
    else:  # ownership: employees can only ever list their own tasks
        q = q.where(Task.assigned_to == current_employee(user).id)
    if status_filter:
        q = q.where(Task.status == status_filter)
    return [_out(t) for t in db.scalars(q)]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    assert_owner_or_staff(user, t.assigned_to)
    return _out(t)


@router.put("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("assigned_to") is not None:
        get_employee_or_404(db, data["assigned_to"])
    for field, value in data.items():
        if value is not None or field == "description":
            setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return _out(t)


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_status(
    task_id: int, body: TaskStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    assert_owner_or_staff(user, t.assigned_to)
    t.status = body.status
    db.commit()
    db.refresh(t)
    return _out(t)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    t = db.get(Task, task_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    db.delete(t)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
