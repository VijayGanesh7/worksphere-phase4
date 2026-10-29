"""Creates in-app notifications and returns the emails to notify, honouring user preferences."""
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Notification, User, UserPreference


def notify(db: Session, users: Iterable[User], title: str, message: str, category: str = "general") -> List[str]:
    """Add Notification rows (caller commits) and return email addresses that should also get an email.

    category: "general" (always delivered), "announcement" or "task" (can be muted in preferences).
    """
    users = list(users)
    if not users:
        return []
    prefs = {
        p.user_id: p
        for p in db.scalars(select(UserPreference).where(UserPreference.user_id.in_([u.id for u in users])))
    }
    emails: List[str] = []
    for u in users:
        p = prefs.get(u.id)
        in_app = p.in_app_notifications if p else True
        email = p.email_notifications if p else True
        if category != "general" and p is not None and not getattr(p, f"{category}_alerts", True):
            continue
        if in_app:
            db.add(Notification(user_id=u.id, title=title[:200], message=message))
        if email:
            emails.append(u.email)
    return emails
