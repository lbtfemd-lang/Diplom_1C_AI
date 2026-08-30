from pydantic import BaseModel
from typing import Optional, List, Dict
from enum import Enum


class KanbanColumn(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TaskSource(str, Enum):
    WEB = "web"
    CHAT = "chat"
    ONE_C = "1c"
    ONE_C_KANBAN = "1c_kanban"
    ONE_C_MOBILE = "1c_mobile"


class KanbanTaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    column: KanbanColumn = KanbanColumn.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[TaskSource] = TaskSource.WEB
    department_id: Optional[int] = None
    created_by: Optional[str] = None


class KanbanTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    column: Optional[KanbanColumn] = None
    priority: Optional[TaskPriority] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None
    department_id: Optional[int] = None


class KanbanTaskMove(BaseModel):
    task_id: int
    column: KanbanColumn
    position: Optional[int] = None


class KanbanTaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    column: str
    priority: str
    assignee: Optional[str] = None
    assignee_color: Optional[str] = None
    due_date: Optional[str] = None
    tags: Optional[List[str]] = None
    source: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    created_by: Optional[str] = None
    position: int
    is_overdue: bool = False
    created_at: str
    updated_at: str


class KanbanBoardResponse(BaseModel):
    tasks: List[KanbanTaskResponse]
    columns: List[dict]


class KanbanStatsResponse(BaseModel):
    total: int
    by_column: Dict[str, int]
    by_priority: Dict[str, int]
    by_department: List[Dict[str, object]]
    overdue_count: int
    my_tasks: int


COLUMN_CONFIG = [
    {"id": "todo", "title": "К выполнению", "color": "#6b7280"},
    {"id": "in_progress", "title": "В работе", "color": "#3b82f6"},
    {"id": "review", "title": "На проверке", "color": "#f59e0b"},
    {"id": "done", "title": "Готово", "color": "#10b981"},
]
