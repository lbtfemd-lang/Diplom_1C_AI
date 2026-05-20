import os
import json
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
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from passlib.context import CryptContext
from jose import JWTError, jwt
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kanban.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
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


class AuthService:
    def __init__(self):
        self._seed_if_empty()

    def _get_session(self):
        return SessionLocal()

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

    def _seed_if_empty(self):
        session = self._get_session()
        try:
            if session.query(UserDB).count() > 0:
                return

            print("Seeding demo data...")

            departments = [
                DepartmentDB(name="Продажи"),
                DepartmentDB(name="Закупки"),
                DepartmentDB(name="Склад"),
                DepartmentDB(name="IT"),
            ]
            session.add_all(departments)
            session.flush()

            users = [
                UserDB(
                    username="admin",
                    password_hash=self.hash_password("admin"),
                    full_name="Администратор Системы",
                    role="admin",
                    department_id=departments[3].id,
                    avatar_color=self._avatar_color_for_name("admin"),
                ),
                UserDB(
                    username="ivanov",
                    password_hash=self.hash_password("123456"),
                    full_name="Иванов Алексей Сергеевич",
                    role="manager",
                    department_id=departments[0].id,
                    avatar_color=self._avatar_color_for_name("ivanov"),
                ),
                UserDB(
                    username="petrov",
                    password_hash=self.hash_password("123456"),
                    full_name="Петров Дмитрий Иванович",
                    role="manager",
                    department_id=departments[1].id,
                    avatar_color=self._avatar_color_for_name("petrov"),
                ),
                UserDB(
                    username="sidorova",
                    password_hash=self.hash_password("123456"),
                    full_name="Сидорова Мария Петровна",
                    role="employee",
                    department_id=departments[2].id,
                    avatar_color=self._avatar_color_for_name("sidorova"),
                ),
                UserDB(
                    username="1c_service",
                    password_hash=self.hash_password("1c_service_2024"),
                    full_name="1С:Предприятие (сервисный аккаунт)",
                    role="admin",
                    department_id=departments[3].id,
                    avatar_color=self._avatar_color_for_name("1c_service"),
                ),
                UserDB(
                    username="test",
                    password_hash=self.hash_password("test"),
                    full_name="Тестовый Пользователь",
                    role="employee",
                    department_id=departments[0].id,
                    avatar_color=self._avatar_color_for_name("test"),
                ),
            ]
            session.add_all(users)

            departments[0].head_user_id = users[1].id
            departments[1].head_user_id = users[2].id
            departments[3].head_user_id = users[0].id

            session.commit()
            print("Demo data seeded: 4 departments, 6 users.")
        except Exception as e:
            session.rollback()
            print(f"Seed error: {e}")
        finally:
            session.close()

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        session = self._get_session()
        try:
            user = session.query(UserDB).filter_by(username=username, is_active=True).first()
            if not user or not self.verify_password(password, user.password_hash):
                return None
            return self._user_to_dict(user)
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
