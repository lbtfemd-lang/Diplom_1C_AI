from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: UserRole = UserRole.EMPLOYEE
    department_id: Optional[int] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    is_active: bool
    avatar_color: str
    created_at: str


class DepartmentCreate(BaseModel):
    name: str
    head_user_id: Optional[int] = None
    parent_id: Optional[int] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    head_user_id: Optional[int] = None
    parent_id: Optional[int] = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    head_user_id: Optional[int] = None
    head_name: Optional[str] = None
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    employee_count: int = 0


class NotificationResponse(BaseModel):
    id: int
    title: str
    priority: str
    assignee: Optional[str] = None
    column: str
    created_at: str


LoginResponse.model_rebuild()
