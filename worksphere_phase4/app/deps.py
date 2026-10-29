"""Authentication, role-based authorization and ownership helpers."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .enums import STAFF_ROLES, Role
from .models import Employee, User
from .schemas import UserOut
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    unauth = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if creds is None:
        raise unauth
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise unauth
    try:
        user = db.get(User, int(payload["sub"]))
    except (ValueError, TypeError):
        raise unauth
    if user is None or not user.is_active:
        raise unauth
    return user


def require_roles(*roles: Role):
    """Dependency factory: only the listed roles may call the endpoint."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission for this action")
        return user

    return checker


require_staff = require_roles(*STAFF_ROLES)


def is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def current_employee(user: User) -> Employee:
    if user.employee is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No employee profile is linked to this account")
    return user.employee


def assert_owner_or_staff(user: User, employee_id: int) -> None:
    """Ownership validation: employees may only touch records that belong to them."""
    if is_staff(user):
        return
    if user.employee is None or user.employee.id != employee_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only access your own records")


def get_employee_or_404(db: Session, employee_id: int) -> Employee:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return emp


def staff_users(db: Session) -> list:
    return list(db.scalars(select(User).where(User.role.in_(STAFF_ROLES), User.is_active.is_(True))))


def user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        employee_id=user.employee.id if user.employee else None,
        full_name=user.employee.full_name if user.employee else None,
    )
