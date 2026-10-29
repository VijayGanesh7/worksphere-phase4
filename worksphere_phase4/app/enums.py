from enum import Enum


class Role(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    HR = "HR"
    ADMIN = "ADMIN"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class ResignationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


STAFF_ROLES = (Role.HR, Role.ADMIN)
