import os
import json
from datetime import datetime, date, timezone


def _utcnow() -> datetime:
    """Naive UTC datetime для совместимости со схемой SQLite без tzinfo.

    Заменяет deprecated datetime.utcnow() (удаляется в Python 3.13+) на
    timezone-aware now(UTC) с последующим сбросом tzinfo. Семантика
    наивного UTC сохраняется, что важно для существующих SQLAlchemy-моделей
    и сравнений с DateTime-колонками без часового пояса.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, and_, or_
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from typing import List, Optional, Dict

from app.core.db import enable_sqlite_wal

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


class KanbanTaskDB(Base):
    __tablename__ = "kanban_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    column = Column(String(50), nullable=False, default="todo")
    priority = Column(String(20), nullable=False, default="medium")
    assignee = Column(String(200), nullable=True)
    due_date = Column(String(20), nullable=True)
    tags = Column(Text, nullable=True)
    source = Column(String(50), nullable=False, default="web")
    department_id = Column(Integer, nullable=True)
    created_by = Column(String(100), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    synced_1c = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)


Base.metadata.create_all(engine)


def _is_overdue(due_date_str: Optional[str]) -> bool:
    if not due_date_str:
        return False
    try:
        due = date.fromisoformat(due_date_str[:10])
        return due < date.today()
    except Exception:
        return False


def _avatar_color_for_name(name: str) -> str:
    if not name:
        return "#6b7280"
    colors = [
        "#ef4444", "#f97316", "#f59e0b", "#84cc16", "#22c55e",
        "#14b8a6", "#06b6d4", "#3b82f6", "#6366f1", "#8b5cf6",
        "#a855f7", "#d946ef", "#ec4899", "#f43f5e",
    ]
    return colors[hash(name) % len(colors)]


class KanbanService:
    def _get_session(self):
        return SessionLocal()

    def _task_to_dict(self, task: KanbanTaskDB, dept_name: str = None, assignee_color: str = None) -> dict:
        tags = []
        if task.tags:
            try:
                tags = json.loads(task.tags)
            except Exception:
                tags = [t.strip() for t in task.tags.split(",") if t.strip()]

        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "column": task.column,
            "priority": task.priority,
            "assignee": task.assignee,
            "assignee_color": assignee_color or _avatar_color_for_name(task.assignee or ""),
            "due_date": task.due_date,
            "tags": tags,
            "source": task.source,
            "department_id": task.department_id,
            "department_name": dept_name,
            "created_by": task.created_by,
            "position": task.position,
            "is_overdue": _is_overdue(task.due_date),
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
        }

    def _enrich_task(self, task: KanbanTaskDB, session) -> dict:
        dept_name = None
        if task.department_id:
            from app.services.auth_service import DepartmentDB
            dept = session.query(DepartmentDB).filter_by(id=task.department_id).first()
            dept_name = dept.name if dept else None
        return self._task_to_dict(task, dept_name=dept_name)

    def _enrich_tasks(self, tasks: list, session) -> list:
        return [self._enrich_task(t, session) for t in tasks]

    def create_task(self, title: str, description: str = None, column: str = "todo",
                    priority: str = "medium", assignee: str = None, due_date: str = None,
                    tags: List[str] = None, source: str = "web",
                    department_id: int = None, created_by: str = None) -> dict:
        session = self._get_session()
        try:
            max_pos = session.query(KanbanTaskDB).filter_by(column=column).count()
            tags_json = json.dumps(tags, ensure_ascii=False) if tags else None

            task = KanbanTaskDB(
                title=title,
                description=description,
                column=column,
                priority=priority,
                assignee=assignee,
                due_date=due_date,
                tags=tags_json,
                source=source,
                department_id=department_id,
                created_by=created_by,
                position=max_pos,
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return self._enrich_task(task, session)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_all_tasks(self) -> List[dict]:
        session = self._get_session()
        try:
            tasks = session.query(KanbanTaskDB).order_by(KanbanTaskDB.column, KanbanTaskDB.position).all()
            return self._enrich_tasks(tasks, session)
        finally:
            session.close()

    @staticmethod
    def _visible_tasks(q, role, department_id, username):
        if role in ("admin", "director", "cfo"):
            return q
        if role not in ("employee", "service_bridge", "manager", "warehouse") or not username:
            return q.filter(False)
        own = or_(KanbanTaskDB.assignee == username, KanbanTaskDB.created_by == username)
        if role in ("manager", "warehouse") and department_id is not None:
            return q.filter(or_(own, KanbanTaskDB.department_id == department_id))
        return q.filter(own)

    def can_access_task(self, task_id, user):
        session = self._get_session()
        try:
            q = session.query(KanbanTaskDB).filter_by(id=task_id)
            return self._visible_tasks(q, user.get("role"), user.get("department_id"),
                                       user.get("username")).first() is not None
        finally:
            session.close()

    def get_tasks_for_user(self, user_id: int, role: str, department_id: int = None,
                           username: str = None, filter_dept: int = None,
                           filter_assignee: str = None, filter_priority: str = None) -> List[dict]:
        session = self._get_session()
        try:
            q = session.query(KanbanTaskDB)

            q = self._visible_tasks(q, role, department_id, username)

            if filter_dept is not None:
                q = q.filter(KanbanTaskDB.department_id == filter_dept)
            if filter_assignee:
                q = q.filter(KanbanTaskDB.assignee == filter_assignee)
            if filter_priority:
                q = q.filter(KanbanTaskDB.priority == filter_priority)

            tasks = q.order_by(KanbanTaskDB.column, KanbanTaskDB.position).all()
            return self._enrich_tasks(tasks, session)
        finally:
            session.close()

    def get_task(self, task_id: int) -> Optional[dict]:
        session = self._get_session()
        try:
            task = session.query(KanbanTaskDB).filter_by(id=task_id).first()
            return self._enrich_task(task, session) if task else None
        finally:
            session.close()

    def update_task(self, task_id: int, **kwargs) -> Optional[dict]:
        session = self._get_session()
        try:
            task = session.query(KanbanTaskDB).filter_by(id=task_id).first()
            if not task:
                return None

            if "tags" in kwargs and kwargs["tags"] is not None:
                kwargs["tags"] = json.dumps(kwargs["tags"], ensure_ascii=False)

            kwargs["updated_at"] = _utcnow()

            for key, value in kwargs.items():
                if value is not None and hasattr(task, key):
                    setattr(task, key, value)

            session.commit()
            session.refresh(task)
            return self._enrich_task(task, session)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def move_task(self, task_id: int, column: str, position: int = None) -> Optional[dict]:
        session = self._get_session()
        try:
            task = session.query(KanbanTaskDB).filter_by(id=task_id).first()
            if not task:
                return None

            old_column = task.column
            task.column = column
            task.updated_at = _utcnow()

            if position is not None:
                task.position = position
            else:
                max_pos = session.query(KanbanTaskDB).filter_by(column=column).count()
                task.position = max_pos

            if old_column != column:
                tasks_in_old = session.query(KanbanTaskDB).filter(
                    KanbanTaskDB.column == old_column,
                    KanbanTaskDB.id != task_id
                ).order_by(KanbanTaskDB.position).all()
                for i, t in enumerate(tasks_in_old):
                    t.position = i

            session.commit()
            session.refresh(task)
            return self._enrich_task(task, session)
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def delete_task(self, task_id: int) -> bool:
        session = self._get_session()
        try:
            task = session.query(KanbanTaskDB).filter_by(id=task_id).first()
            if not task:
                return False
            session.delete(task)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_stats(self, user_id: int, role: str, department_id: int = None,
                  username: str = None) -> Dict:
        session = self._get_session()
        try:
            q = session.query(KanbanTaskDB)

            q = self._visible_tasks(q, role, department_id, username)

            tasks = q.all()

            by_column = {"todo": 0, "in_progress": 0, "review": 0, "done": 0}
            by_priority = {"low": 0, "medium": 0, "high": 0, "urgent": 0}
            overdue_count = 0
            my_count = 0
            dept_counts = {}

            for t in tasks:
                by_column[t.column] = by_column.get(t.column, 0) + 1
                by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
                if _is_overdue(t.due_date) and t.column != "done":
                    overdue_count += 1
                if t.assignee == username:
                    my_count += 1
                if t.department_id:
                    dept_counts[t.department_id] = dept_counts.get(t.department_id, 0) + 1

            by_department = []
            from app.services.auth_service import DepartmentDB
            for dept_id, count in dept_counts.items():
                dept = session.query(DepartmentDB).filter_by(id=dept_id).first()
                by_department.append({
                    "department_id": dept_id,
                    "department_name": dept.name if dept else "?",
                    "count": count,
                })

            return {
                "total": len(tasks),
                "by_column": by_column,
                "by_priority": by_priority,
                "by_department": by_department,
                "overdue_count": overdue_count,
                "my_tasks": my_count,
            }
        finally:
            session.close()

    def get_notifications(self, username: str, role: str, department_id: int = None, limit: int = 5) -> List[dict]:
        session = self._get_session()
        try:
            q = session.query(KanbanTaskDB)

            q = self._visible_tasks(q, role, department_id, username)

            tasks = q.order_by(KanbanTaskDB.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "assignee": t.assignee,
                    "column": t.column,
                    "created_at": t.created_at.isoformat() if t.created_at else "",
                }
                for t in tasks
            ]
        finally:
            session.close()

    def export_csv(self, user_id: int, role: str, department_id: int = None, username: str = None) -> str:
        tasks = self.get_tasks_for_user(user_id, role, department_id, username)
        lines = ["id,title,description,column,priority,assignee,due_date,department,created_by,source,is_overdue"]
        for t in tasks:
            desc = (t.get("description") or "").replace(",", ";").replace("\n", " ")
            lines.append(
                f'{t["id"]},"{t["title"]}",{desc},{t["column"]},{t["priority"]},'
                f'{t.get("assignee","")},{t.get("due_date","")},{t.get("department_name","")},'
                f'{t.get("created_by","")},{t["source"]},{t["is_overdue"]}'
            )
        return "\n".join(lines)

    def get_tasks_for_1c_sync(self) -> List[dict]:
        session = self._get_session()
        try:
            tasks = session.query(KanbanTaskDB).filter_by(synced_1c=False).all()
            return [self._task_to_dict(t) for t in tasks]
        finally:
            session.close()

    def mark_synced(self, task_ids: List[int]):
        session = self._get_session()
        try:
            session.query(KanbanTaskDB).filter(KanbanTaskDB.id.in_(task_ids)).update(
                {"synced_1c": True, "updated_at": _utcnow()}
            )
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


kanban_service = KanbanService()
