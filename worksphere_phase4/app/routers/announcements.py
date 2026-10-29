"""MODULE 23 - Internal Announcements System."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_staff
from ..models import Announcement, User
from ..schemas import AnnouncementCreate, AnnouncementOut, AnnouncementUpdate
from ..services.email_service import send_email_async
from ..services.notifications import notify

router = APIRouter(prefix="/api/announcements", tags=["Module 23 - Announcements"])


def _out(a: Announcement) -> AnnouncementOut:
    return AnnouncementOut(
        id=a.id,
        title=a.title,
        message=a.message,
        created_by=a.created_by,
        created_by_name=a.creator.display_name,
        created_at=a.created_at,
    )


@router.post("", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
def post_announcement(body: AnnouncementCreate, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    a = Announcement(title=body.title, message=body.message, created_by=user.id)
    db.add(a)
    recipients = db.scalars(select(User).where(User.is_active.is_(True), User.id != user.id))
    emails = notify(db, recipients, f"Announcement: {body.title}", body.message[:500], category="announcement")
    db.commit()
    db.refresh(a)
    send_email_async(emails, f"Announcement: {body.title}", body.message)
    return _out(a)


@router.get("", response_model=List[AnnouncementOut])
def list_announcements(
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Announcement).order_by(Announcement.created_at.desc(), Announcement.id.desc()).limit(limit).offset(offset)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Announcement.title.ilike(like) | Announcement.message.ilike(like))
    return [_out(a) for a in db.scalars(stmt)]


@router.get("/{announcement_id}", response_model=AnnouncementOut)
def get_announcement(announcement_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    a = db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found")
    return _out(a)


@router.put("/{announcement_id}", response_model=AnnouncementOut)
def update_announcement(
    announcement_id: int, body: AnnouncementUpdate, db: Session = Depends(get_db), _: User = Depends(require_staff)
):
    a = db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(a, field, value)
    db.commit()
    db.refresh(a)
    return _out(a)


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(announcement_id: int, db: Session = Depends(get_db), _: User = Depends(require_staff)):
    a = db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found")
    db.delete(a)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
