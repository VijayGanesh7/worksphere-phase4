"""MODULE 27 - Profile & Settings Management."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User, UserPreference
from ..schemas import PasswordChange, PreferencesOut, PreferencesUpdate, ProfileOut, ProfileUpdate
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api/profile", tags=["Module 27 - Profile & Settings"])


def _profile(user: User) -> ProfileOut:
    e = user.employee
    return ProfileOut(
        user_id=user.id,
        email=user.email,
        role=user.role,
        employee_id=e.id if e else None,
        full_name=e.full_name if e else None,
        phone=e.phone if e else None,
        department=e.department if e else None,
        designation=e.designation if e else None,
        date_joined=e.date_joined if e else None,
    )


def _prefs(db: Session, user: User) -> UserPreference:
    prefs = user.preferences
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        db.flush()
    return prefs


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user)):
    return _profile(user)


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Users may edit only their own name and phone. Email, role and department are HR-managed."""
    if user.employee is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No employee profile is linked to this account")
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user.employee, field, value)
    db.commit()
    db.refresh(user)
    return _profile(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must differ from the current one")
    user.hashed_password = hash_password(body.new_password)
    db.commit()


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prefs = _prefs(db, user)
    db.commit()
    return prefs


@router.put("/preferences", response_model=PreferencesOut)
def update_preferences(body: PreferencesUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    prefs = _prefs(db, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(prefs, field, value)
    db.commit()
    db.refresh(prefs)
    return prefs
