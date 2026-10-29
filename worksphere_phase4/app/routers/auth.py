"""JWT login plus admin-only user creation and a staff employee directory."""
import time
from collections import defaultdict
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles, require_staff, user_to_out
from ..enums import Role
from ..models import Employee, User, UserPreference
from ..schemas import DirectoryEntry, LoginRequest, RegisterRequest, TokenResponse, UserOut
from ..security import create_access_token, hash_password, verify_password
from .onboarding import create_default_checklist

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Simple in-memory brute-force guard (per process). Use Redis or a gateway limiter when running multiple workers.
_MAX_FAILS, _WINDOW = 5, 15 * 60
_fails: dict = defaultdict(list)
_DUMMY_HASH = hash_password("not-a-real-password")


def _locked(key: str) -> bool:
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < _WINDOW]
    return len(_fails[key]) >= _MAX_FAILS


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    key = f"{body.email}|{request.client.host if request.client else '?'}"
    if _locked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again later.")
    user = db.scalar(select(User).where(User.email == body.email))
    # Always run one hash verification so response time doesn't reveal whether the email exists.
    ok = verify_password(body.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        _fails[key].append(time.time())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    _fails.pop(key, None)
    return TokenResponse(access_token=create_access_token(user.id), user=user_to_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_to_out(user)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.ADMIN))):
    """Admin creates an account + employee profile; a standard onboarding checklist is assigned automatically."""
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    user = User(email=body.email, hashed_password=hash_password(body.password), role=body.role)
    user.employee = Employee(
        full_name=body.full_name, phone=body.phone, department=body.department, designation=body.designation
    )
    user.preferences = UserPreference()
    db.add(user)
    db.flush()
    create_default_checklist(db, user.employee)
    db.commit()
    db.refresh(user)
    return user_to_out(user)


@router.get("/employees", response_model=List[DirectoryEntry])
def employee_directory(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    """Minimal employee list for HR/Admin dropdowns (assigning tasks, onboarding)."""
    rows = db.scalars(select(Employee).join(User).where(User.is_active.is_(True)).order_by(Employee.full_name))
    return [DirectoryEntry(id=e.id, full_name=e.full_name, department=e.department) for e in rows]
