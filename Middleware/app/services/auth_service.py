import os
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    """Naive UTC datetime для совместимости со схемой SQLite без tzinfo.

    Заменяет deprecated datetime.utcnow() (удаляется в Python 3.13+) на
    timezone-aware now(UTC) с последующим сбросом tzinfo. Семантика
    наивного UTC сохраняется, что важно для существующих SQLAlchemy-моделей
    и сравнений с DateTime-колонками без часового пояса.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
from typing import Optional, List

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv

from app.core.db import enable_sqlite_wal

load_dotenv()

logger = logging.getLogger(__name__)

def get_sqlite_db_path() -> str:
    env_path = os.getenv("SQLITE_DB_PATH")
    if env_path:
        p = os.path.abspath(env_path)
    else:
        p = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kanban.db"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p

DB_PATH = get_sqlite_db_path()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
enable_sqlite_wal(engine)
SessionLocal = sessionmaker(bind=engine)
class Base(DeclarativeBase):
    pass

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_jwt_secret_raw = os.getenv("JWT_SECRET", "")
JWT_SECRET = _jwt_secret_raw if _jwt_secret_raw else secrets.token_hex(32)
if not _jwt_secret_raw:
    logger.warning("JWT_SECRET not set — using random secret (tokens invalid after restart)")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

AVATAR_COLORS = [
    "#ef4444", "#f97316", "#f59e0b", "#84cc16", "#22c55e",
    "#14b8a6", "#06b6d4", "#3b82f6", "#6366f1", "#8b5cf6",
    "#a855f7", "#d946ef", "#ec4899", "#f43f5e",
]


class DepartmentDB(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    head_user_id = Column(Integer, nullable=True)
    parent_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="employee")
    department_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    avatar_color = Column(String(10), nullable=False, default="#3b82f6")
    created_at = Column(DateTime, nullable=False, default=_utcnow)


Base.metadata.create_all(engine)


ROLE_PERMISSIONS = {
    "admin": {"*"},
    "director": {"*"},
    "cfo": {
        "analytics:read", "financial:read", "debt:read", "debt:write",
        "compliance:read", "compliance:write", "margin:read", "margin:write",
        "stock:read", "kanban:read", "kanban:write"
    },
    "manager": {
        "kanban:read", "kanban:write", "margin:read", "stock:read", "debt:read"
    },
    "warehouse": {
        "stock:read", "stock:write", "kanban:read", "kanban:write"
    },
    "employee": {
        "kanban:read", "tasks:own"
    }
}


class AuthService:
    def __init__(self):
        self._seed_default_users()

    def _get_session(self):
        return SessionLocal()

    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(role, set())
        return "*" in perms or permission in perms

    @staticmethod
    def can_access_financials(role: str) -> bool:
        return role in ("director", "cfo", "admin")

    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def create_access_token(data: dict) -> str:
        to_encode = data.copy()
        expire = _utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
        to_encode["exp"] = expire
        return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except JWTError:
            return None

    @staticmethod
    def _avatar_color_for_name(name: str) -> str:
        h = hash(name) % len(AVATAR_COLORS)
        return AVATAR_COLORS[h]

    def _seed_default_users(self):
        """Гарантирует наличие всех ключевых ролей и пользователей для бизнес-сценариев."""
        session = self._get_session()
        try:
            # 1. Создаем или находим подразделения
            dept_names = ["Дирекция", "Финансовый отдел", "Продажи", "Закупки", "Склад", "IT"]
            dept_map = {}
            for d_name in dept_names:
                dept = session.query(DepartmentDB).filter_by(name=d_name).first()
                if not dept:
                    dept = DepartmentDB(name=d_name)
                    session.add(dept)
                    session.flush()
                dept_map[d_name] = dept.id

            # 2. Список обязательных пользователей системы
            default_users = [
                {
                    "username": "director",
                    "password": "director123",
                    "full_name": "Абдулов Ринат Фаридович",
                    "role": "director",
                    "department_id": dept_map.get("Дирекция"),
                },
                {
                    "username": "cfo",
                    "password": "cfo123",
                    "full_name": "Филиппова Елена Анатольевна",
                    "role": "cfo",
                    "department_id": dept_map.get("Финансовый отдел"),
                },
                {
                    "username": "manager",
                    "password": "manager123",
                    "full_name": "Иванов Алексей Сергеевич",
                    "role": "manager",
                    "department_id": dept_map.get("Продажи"),
                },
                {
                    "username": "warehouse",
                    "password": "warehouse123",
                    "full_name": "Сидорова Мария Петровна",
                    "role": "warehouse",
                    "department_id": dept_map.get("Склад"),
                },
                {
                    "username": "employee",
                    "password": "employee123",
                    "full_name": "Тестов Тимур Павлович",
                    "role": "employee",
                    "department_id": dept_map.get("Продажи"),
                },
                {
                    "username": "admin",
                    "password": "admin",
                    "full_name": "Администратор Системы",
                    "role": "admin",
                    "department_id": dept_map.get("IT"),
                },
                {
                    "username": "accountant",
                    "password": "buh123",
                    "full_name": "Смирнова Ольга Викторовна (Главбух)",
                    "role": "cfo",
                    "department_id": dept_map.get("Финансовый отдел"),
                },
                {
                    "username": "1c_service",
                    "password": "1c_service_2024",
                    "full_name": "1С:Предприятие (сервисный транспорт)",
                    "role": "service_bridge",
                    "department_id": dept_map.get("IT"),
                },
            ]

            for u_data in default_users:
                existing = session.query(UserDB).filter_by(username=u_data["username"]).first()
                if not existing:
                    user = UserDB(
                        username=u_data["username"],
                        password_hash=self.hash_password(u_data["password"]),
                        full_name=u_data["full_name"],
                        role=u_data["role"],
                        department_id=u_data["department_id"],
                        avatar_color=self._avatar_color_for_name(u_data["username"]),
                    )
                    session.add(user)
                # Existing accounts belong to the administrator. Never restore
                # a revoked role or overwrite credentials during startup.

            session.commit()
            logger.info("Default roles & users verified: director, cfo, accountant, manager, warehouse, employee, admin, service_bridge.")
        except Exception as e:
            session.rollback()
            logger.error("Seed error: %s", e)
        finally:
            session.close()

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(username=username, is_active=True).first()
            if not user:
                return None
            if not self.verify_password(password, user.password_hash):
                return None
            return self._user_to_dict(user)
        finally:
            session.close()

    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """Смена пароля пользователя с обязательной верификацией текущего пароля."""
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(id=user_id).first()
            if not user:
                return False
            if not self.verify_password(old_password, user.password_hash):
                return False
            user.password_hash = self.hash_password(new_password)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(id=user_id).first()
            return self._user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_username(self, username: str) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(username=username).first()
            return self._user_to_dict(user) if user else None
        finally:
            session.close()

    def create_user(self, username: str, password: str, full_name: str,
                    role: str = "employee", department_id: int = None) -> dict:
        session = self._get_session()
        try:
            existing = session.query(UserDB).filter_by(username=username).first()
            if existing:
                raise ValueError(f"Username '{username}' already exists")

            user = UserDB(
                username=username,
                password_hash=self.hash_password(password),
                full_name=full_name,
                role=role,
                department_id=department_id,
                avatar_color=self._avatar_color_for_name(username),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self._user_to_dict(user)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_user(self, user_id: int, **kwargs) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(id=user_id).first()
            if not user:
                return None
            if "password" in kwargs and kwargs["password"]:
                kwargs["password_hash"] = self.hash_password(kwargs.pop("password"))
            elif "password" in kwargs:
                del kwargs["password"]

            for key, value in kwargs.items():
                if value is not None and hasattr(user, key):
                    setattr(user, key, value)

            session.commit()
            session.refresh(user)
            return self._user_to_dict(user)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_user(self, user_id: int) -> bool:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(id=user_id).first()
            if not user:
                return False
            session.delete(user)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def list_users(self, department_id: int = None) -> List[dict]:
        session = self._get_session()
        try:
            q = session.query(UserDB)
            if department_id is not None:
                q = q.filter_by(department_id=department_id)
            users = q.order_by(UserDB.full_name).all()
            return [self._user_to_dict(u) for u in users]
        finally:
            session.close()

    def _user_to_dict(self, user: UserDB) -> dict:
        dept_name = None
        if user.department_id:
            session = self._get_session()
            try:
                dept = session.query(DepartmentDB).filter_by(id=user.department_id).first()
                dept_name = dept.name if dept else None
            finally:
                session.close()

        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "department_id": user.department_id,
            "department_name": dept_name,
            "is_active": user.is_active,
            "avatar_color": user.avatar_color,
            "created_at": user.created_at.isoformat() if user.created_at else "",
        }

    def get_departments(self) -> List[dict]:
        session = self._get_session()
        try:
            depts = session.query(DepartmentDB).order_by(DepartmentDB.name).all()
            return [self._dept_to_dict(d, session) for d in depts]
        finally:
            session.close()

    def get_department(self, dept_id: int) -> Optional[dict]:
        session = self._get_session()
        try:
            dept = session.query(DepartmentDB).filter_by(id=dept_id).first()
            return self._dept_to_dict(dept, session) if dept else None
        finally:
            session.close()

    def create_department(self, name: str, head_user_id: int = None, parent_id: int = None) -> dict:
        session = self._get_session()
        try:
            dept = DepartmentDB(name=name, head_user_id=head_user_id, parent_id=parent_id)
            session.add(dept)
            session.commit()
            session.refresh(dept)
            return self._dept_to_dict(dept, session)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def update_department(self, dept_id: int, **kwargs) -> Optional[dict]:
        session = self._get_session()
        try:
            dept = session.query(DepartmentDB).filter_by(id=dept_id).first()
            if not dept:
                return None
            for key, value in kwargs.items():
                if value is not None and hasattr(dept, key):
                    setattr(dept, key, value)
            session.commit()
            session.refresh(dept)
            return self._dept_to_dict(dept, session)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_department(self, dept_id: int) -> bool:
        session = self._get_session()
        try:
            dept = session.query(DepartmentDB).filter_by(id=dept_id).first()
            if not dept:
                return False
            session.query(UserDB).filter_by(department_id=dept_id).update({"department_id": None})
            session.delete(dept)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _dept_to_dict(self, dept: DepartmentDB, session) -> dict:
        head_name = None
        if dept.head_user_id:
            head = session.query(UserDB).filter_by(id=dept.head_user_id).first()
            head_name = head.full_name if head else None

        parent_name = None
        if dept.parent_id:
            parent = session.query(DepartmentDB).filter_by(id=dept.parent_id).first()
            parent_name = parent.name if parent else None

        employee_count = session.query(UserDB).filter_by(department_id=dept.id).count()

        return {
            "id": dept.id,
            "name": dept.name,
            "head_user_id": dept.head_user_id,
            "head_name": head_name,
            "parent_id": dept.parent_id,
            "parent_name": parent_name,
            "employee_count": employee_count,
        }

auth_service = AuthService()
