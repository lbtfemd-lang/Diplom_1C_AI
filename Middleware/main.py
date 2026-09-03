import sys
import os
import logging
from contextlib import asynccontextmanager

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Depends, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.models.api_models import ChatRequest, ChatResponse, MetadataRequest
from app.models.kanban_models import (
    KanbanTaskCreate, KanbanTaskUpdate, KanbanTaskMove,
    KanbanTaskResponse, KanbanBoardResponse, KanbanStatsResponse, COLUMN_CONFIG,
    TaskSource,
)
from app.models.auth_models import (
    LoginRequest, LoginResponse, UserCreate, UserUpdate, UserResponse,
    DepartmentCreate, DepartmentUpdate, DepartmentResponse, NotificationResponse,
)
from app.services.llm_service import llm_service
from app.services.metadata_service import metadata_service
from app.services.kanban_service import kanban_service
from app.services.auth_service import auth_service

from typing import Any, Dict, List, Optional
import io
import uvicorn

@asynccontextmanager
async def _lifespan(app_instance):
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret or jwt_secret in ("your_jwt_secret_key_here", "changeme"):
        logger.warning("JWT_SECRET is not properly configured. Set a strong secret in .env!")
    api_key = os.getenv("FIREWORKS_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
    if not api_key or api_key.startswith("your_"):
        logger.warning("No LLM API key configured. Chat functionality will not work.")
    yield


app = FastAPI(title="1C AI Assistant Middleware", lifespan=_lifespan)

_rate_limit_enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")

if _rate_limit_enabled:
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
else:
    limiter = Limiter(key_func=get_remote_address, enabled=False, default_limits=["100000/minute"])
    app.state.limiter = limiter

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "-")
    logger.info("%s %s req_id=%s", request.method, request.url.path, request_id)
    response = await call_next(request)
    return response


api_key_scheme = APIKeyHeader(name="X-Auth-Token", auto_error=False)


async def get_current_user(token: str = Security(api_key_scheme)) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = auth_service.get_user_by_id(payload.get("user_id"))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def get_optional_user(token: str = Security(api_key_scheme)) -> Optional[dict]:
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


def require_role(user: dict, *roles):
    if user["role"] not in roles and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions")


@app.get("/", response_model=Dict[str, Any])
def read_root():
    return {"status": "ok", "service": "1C AI Assistant Middleware"}


@app.get("/health", response_model=Dict[str, Any])
async def health_check():
    from sqlalchemy import text
    checks = {"status": "ok", "service": "1C AI Assistant Middleware"}
    try:
        session = auth_service._get_session()
        session.execute(text("SELECT 1"))
        session.close()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"
        checks["status"] = "degraded"
    checks["llm"] = "configured" if llm_service.client else "not_configured"
    return checks


# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
@limiter.limit("60/minute")
async def login(request: Request, req: LoginRequest):
    user = auth_service.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth_service.create_access_token({"sub": user["username"], "user_id": user["id"]})
    return LoginResponse(access_token=token, user=UserResponse(**user))


@app.post("/auth/register", response_model=UserResponse)
async def register(req: UserCreate, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    try:
        new_user = auth_service.create_user(
            username=req.username,
            password=req.password,
            full_name=req.full_name,
            role=req.role.value,
            department_id=req.department_id,
        )
        return UserResponse(**new_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(**user)


@app.put("/auth/me", response_model=UserResponse)
async def update_me(req: UserUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if user["role"] != "admin" and "role" in updates:
        del updates["role"]
    result = auth_service.update_user(user["id"], **updates)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**result)


@app.get("/auth/users", response_model=List[UserResponse])
async def list_users(
    department_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    if user["role"] == "employee":
        dept = user.get("department_id")
    elif user["role"] == "manager" and user.get("department_id"):
        dept = user.get("department_id")
    else:
        dept = department_id
    users = auth_service.list_users(department_id=dept)
    return [UserResponse(**u) for u in users[skip:skip + limit]]


@app.put("/auth/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, req: UserUpdate, caller: dict = Depends(get_current_user)):
    require_role(caller, "admin")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = auth_service.update_user(user_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**result)


@app.delete("/auth/users/{user_id}", response_model=Dict[str, Any])
async def delete_user(user_id: int, caller: dict = Depends(get_current_user)):
    require_role(caller, "admin")
    if not auth_service.delete_user(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok"}


# ─── DEPARTMENTS ─────────────────────────────────────────────────────────────

@app.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(user: dict = Depends(get_current_user)):
    return [DepartmentResponse(**d) for d in auth_service.get_departments()]


@app.post("/departments", response_model=DepartmentResponse)
async def create_department(req: DepartmentCreate, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    dept = auth_service.create_department(
        name=req.name,
        head_user_id=req.head_user_id,
        parent_id=req.parent_id,
    )
    return DepartmentResponse(**dept)


@app.put("/departments/{dept_id}", response_model=DepartmentResponse)
async def update_department(dept_id: int, req: DepartmentUpdate, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = auth_service.update_department(dept_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="Department not found")
    return DepartmentResponse(**result)


@app.delete("/departments/{dept_id}", response_model=Dict[str, Any])
async def delete_department(dept_id: int, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    if not auth_service.delete_department(dept_id):
        raise HTTPException(status_code=404, detail="Department not found")
    return {"status": "ok"}


# ─── CHAT ────────────────────────────────────────────────────────────────────

@app.post("/update_metadata", response_model=Dict[str, Any])
async def update_metadata_endpoint(request: MetadataRequest, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    try:
        items_dict = [item.model_dump() for item in request.items]
        metadata_service.update_metadata(items_dict)
        result = {"status": "ok", "count": len(items_dict)}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat_endpoint(request: Request, req: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        response_data = await llm_service.generate_response(req.messages, context=req.context)
        action = response_data.get("action")

        if action == "create_kanban_task" and response_data.get("data"):
            data = response_data["data"]
            task = kanban_service.create_task(
                title=data.get("title", "Новая задача"),
                description=data.get("description"),
                column=data.get("column", "todo"),
                priority=data.get("priority", "medium"),
                assignee=data.get("assignee"),
                due_date=data.get("due_date"),
                tags=data.get("tags"),
                source="chat",
                department_id=user.get("department_id"),
                created_by=user["username"],
            )
            response_data["data"]["task_id"] = task["id"]
            response_data["text"] += f"\n\nЗадача #{task['id']} создана и добавлена в колонку «{task['column']}»."

        return ChatResponse(
            role="assistant",
            text=response_data["text"],
            action=response_data.get("action"),
            data=response_data.get("data"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── KANBAN API ──────────────────────────────────────────────────────────────

@app.get("/kanban/board", response_model=KanbanBoardResponse)
async def get_board(user: dict = Depends(get_current_user)):
    tasks = kanban_service.get_tasks_for_user(
        user_id=user["id"],
        role=user["role"],
        department_id=user.get("department_id"),
        username=user["username"],
    )
    return KanbanBoardResponse(tasks=tasks, columns=COLUMN_CONFIG)


@app.get("/kanban/tasks", response_model=List[KanbanTaskResponse])
async def get_tasks(
    filter_dept: Optional[int] = None,
    filter_assignee: Optional[str] = None,
    filter_priority: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    tasks = kanban_service.get_tasks_for_user(
        user_id=user["id"],
        role=user["role"],
        department_id=user.get("department_id"),
        username=user["username"],
        filter_dept=filter_dept if user["role"] == "admin" else None,
        filter_assignee=filter_assignee,
        filter_priority=filter_priority,
    )
    return tasks[skip:skip + limit]


@app.post("/kanban/tasks", response_model=KanbanTaskResponse)
async def create_task(task: KanbanTaskCreate, user: dict = Depends(get_current_user)):
    try:
        dept_id = task.department_id
        if not dept_id and user.get("department_id"):
            dept_id = user["department_id"]

        if user["role"] == "employee" and task.assignee and task.assignee != user["username"]:
            raise HTTPException(status_code=403, detail="Employees can only create tasks for themselves")

        result = kanban_service.create_task(
            title=task.title,
            description=task.description,
            column=task.column.value,
            priority=task.priority.value,
            assignee=task.assignee or user["username"],
            due_date=task.due_date,
            tags=task.tags,
            source=task.source.value if task.source else "web",
            department_id=dept_id,
            created_by=user["username"],
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/kanban/tasks/export")
async def export_tasks(user: dict = Depends(get_current_user)):
    csv_data = kanban_service.export_csv(
        user_id=user["id"],
        role=user["role"],
        department_id=user.get("department_id"),
        username=user["username"],
    )
    return StreamingResponse(
        io.StringIO(csv_data),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kanban_tasks.csv"},
    )


@app.get("/kanban/tasks/{task_id}", response_model=KanbanTaskResponse)
async def get_task(task_id: int, user: dict = Depends(get_current_user)):
    result = kanban_service.get_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    if user["role"] == "employee" and result.get("assignee") != user["username"] and result.get("created_by") != user["username"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return result


@app.put("/kanban/tasks/{task_id}", response_model=KanbanTaskResponse)
async def update_task(task_id: int, task: KanbanTaskUpdate, user: dict = Depends(get_current_user)):
    try:
        existing = kanban_service.get_task(task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        if user["role"] == "employee" and existing.get("assignee") != user["username"]:
            raise HTTPException(status_code=403, detail="Access denied")

        updates = {k: v for k, v in task.model_dump().items() if v is not None}
        if "column" in updates and updates["column"] is not None:
            updates["column"] = updates["column"].value
        if "priority" in updates and updates["priority"] is not None:
            updates["priority"] = updates["priority"].value
        result = kanban_service.update_task(task_id, **updates)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/kanban/tasks/move", response_model=KanbanTaskResponse)
async def move_task(move: KanbanTaskMove, user: dict = Depends(get_current_user)):
    try:
        existing = kanban_service.get_task(move.task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        if user["role"] == "employee" and existing.get("assignee") != user["username"]:
            raise HTTPException(status_code=403, detail="Access denied")

        result = kanban_service.move_task(move.task_id, move.column.value, move.position)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/kanban/tasks/{task_id}", response_model=Dict[str, Any])
async def delete_task(task_id: int, user: dict = Depends(get_current_user)):
    existing = kanban_service.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    if user["role"] not in ("admin",) and existing.get("created_by") != user["username"]:
        if user["role"] == "employee":
            raise HTTPException(status_code=403, detail="Only admin or creator can delete tasks")
    if not kanban_service.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "deleted": task_id}


@app.get("/kanban/stats", response_model=KanbanStatsResponse)
async def get_stats(user: dict = Depends(get_current_user)):
    return kanban_service.get_stats(
        user_id=user["id"],
        role=user["role"],
        department_id=user.get("department_id"),
        username=user["username"],
    )


@app.get("/kanban/notifications", response_model=List[NotificationResponse])
async def get_notifications(user: dict = Depends(get_current_user)):
    notifs = kanban_service.get_notifications(
        username=user["username"],
        role=user["role"],
        department_id=user.get("department_id"),
    )
    return [NotificationResponse(**n) for n in notifs]


# ─── 1C SYNC ──────────────────────────────────────────────────────────────────

@app.get("/kanban/sync/1c", response_model=Dict[str, Any])
async def get_tasks_for_1c(user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    return kanban_service.get_tasks_for_1c_sync()


@app.post("/kanban/sync/1c", response_model=Dict[str, Any])
async def mark_tasks_synced(task_ids: List[int], user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    kanban_service.mark_synced(task_ids)
    return {"status": "ok", "synced": len(task_ids)}


if __name__ == "__main__":
    host = os.getenv("MIDDLEWARE_HOST", "0.0.0.0")
    port = int(os.getenv("MIDDLEWARE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
