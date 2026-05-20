import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

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
from app.models.tender_models import (
    MatchRequest,
    MatchResponse,
    TenderParseRequest,
    TenderParseResponse,
)
from app.core import is_drone_feature_enabled
from app.services.llm_service import llm_service
from app.services.metadata_service import metadata_service
from app.services.kanban_service import kanban_service
from app.services.auth_service import auth_service
from app.services.drone_index_service import drone_index_service
from app.services.component_index_service import component_index_service
from app.services.tender_service import TenderParseError, get_tender_service
from typing import List, Optional
import io
import uvicorn

app = FastAPI(title="1C AI Assistant Middleware")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/")
def read_root():
    return {"status": "ok", "service": "1C AI Assistant Middleware"}


# ─── AUTH ────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest):
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
    user: dict = Depends(get_current_user),
):
    if user["role"] == "employee":
        dept = user.get("department_id")
    elif user["role"] == "manager" and user.get("department_id"):
        dept = user.get("department_id")
    else:
        dept = department_id
    users = auth_service.list_users(department_id=dept)
    return [UserResponse(**u) for u in users]


@app.put("/auth/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, req: UserUpdate, caller: dict = Depends(get_current_user)):
    require_role(caller, "admin")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = auth_service.update_user(user_id, **updates)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**result)


@app.delete("/auth/users/{user_id}")
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


@app.delete("/departments/{dept_id}")
async def delete_department(dept_id: int, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    if not auth_service.delete_department(dept_id):
        raise HTTPException(status_code=404, detail="Department not found")
    return {"status": "ok"}


# ─── CHAT ────────────────────────────────────────────────────────────────────

@app.post("/update_metadata")
async def update_metadata_endpoint(request: MetadataRequest, user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    try:
        items_dict = [item.model_dump() for item in request.items]
        metadata_service.update_metadata(items_dict)
        result = {"status": "ok", "count": len(items_dict)}

        # Прикладное расширение: каталоги БПЛА и комплектующих.
        if is_drone_feature_enabled():
            if request.drones is not None:
                drone_index_service.rebuild_from_drones(list(request.drones))
                result["drones_count"] = len(request.drones)
            if request.components is not None:
                component_index_service.rebuild_from_components(list(request.components))
                result["components_count"] = len(request.components)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        response_data = await llm_service.generate_response(request.messages, context=request.context)
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


# ─── TENDER MATCHER (прикладное расширение БПЛА) ─────────────────────────────

def _require_drone_feature():
    if not is_drone_feature_enabled():
        # Фича выключена — поведение, как будто эндпоинта нет.
        raise HTTPException(status_code=404, detail="Not Found")


@app.post("/tender/parse", response_model=TenderParseResponse)
async def tender_parse_endpoint(req: TenderParseRequest, user: dict = Depends(get_current_user)):
    _require_drone_feature()
    require_role(user, "manager", "admin")
    try:
        requirements = await get_tender_service().parse(req.tender_text)
    except TenderParseError as exc:
        raise HTTPException(
            status_code=422,
            detail="Не удалось распознать требования тендера. "
                   "Попробуйте уточнить формулировку или ввести характеристики списком.",
        ) from exc
    summary = _summarize_requirements(requirements)
    return TenderParseResponse(requirements=requirements, summary=summary)


@app.post("/tender/match", response_model=MatchResponse)
async def tender_match_endpoint(req: MatchRequest, user: dict = Depends(get_current_user)):
    _require_drone_feature()
    require_role(user, "manager", "admin")
    if req.requirements.intent in ("ready_model", "auto") and not drone_index_service.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Каталог БПЛА не загружен. Нажмите «Обновить метаданные» в 1С.",
        )
    return await get_tender_service().match(req.requirements)


def _summarize_requirements(req) -> str:
    """Короткое читаемое резюме извлечённых требований по-русски."""
    parts = []
    type_map = {
        "quadcopter": "квадрокоптер", "hexacopter": "гексакоптер",
        "octocopter": "октокоптер", "fixed_wing": "самолётный тип",
        "helicopter": "вертолёт", "vtol_hybrid": "VTOL-гибрид",
    }
    purpose_map = {
        "educational": "учебный", "fpv_racing": "FPV-гонки",
        "logistics": "логистика", "aerial_photo": "аэрофотосъёмка",
        "surveillance": "наблюдение", "general": "общего назначения",
    }
    if req.drone_type:
        parts.append(type_map.get(req.drone_type, req.drone_type))
    if req.purpose:
        parts.append(purpose_map.get(req.purpose, req.purpose))
    if req.motor_count_min:
        parts.append(f"{req.motor_count_min} мотор(а/ов)")
    if req.payload_min_kg:
        parts.append(f"грузоподъёмность ≥ {req.payload_min_kg} кг")
    if req.flight_time_min_minutes:
        parts.append(f"время полёта ≥ {req.flight_time_min_minutes} мин")
    if req.range_min_km:
        parts.append(f"дальность ≥ {req.range_min_km} км")
    if req.frame_diagonal_mm:
        parts.append(f"диагональ {req.frame_diagonal_mm} мм")
    if req.programmable_languages:
        parts.append("языки: " + ", ".join(req.programmable_languages))
    if req.quantity:
        parts.append(f"количество {req.quantity} шт.")
    if req.budget_per_unit_rub:
        parts.append(f"бюджет {int(req.budget_per_unit_rub)} ₽/шт.")
    if not parts:
        return "Распознавание выполнено, но конкретных требований не выделено."
    return "Распознано: " + ", ".join(parts) + "."


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
    user: dict = Depends(get_current_user),
):
    return kanban_service.get_tasks_for_user(
        user_id=user["id"],
        role=user["role"],
        department_id=user.get("department_id"),
        username=user["username"],
        filter_dept=filter_dept if user["role"] == "admin" else None,
        filter_assignee=filter_assignee,
        filter_priority=filter_priority,
    )


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


@app.delete("/kanban/tasks/{task_id}")
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

@app.get("/kanban/sync/1c")
async def get_tasks_for_1c(user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    return kanban_service.get_tasks_for_1c_sync()


@app.post("/kanban/sync/1c")
async def mark_tasks_synced(task_ids: List[int], user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    kanban_service.mark_synced(task_ids)
    return {"status": "ok", "synced": len(task_ids)}


if __name__ == "__main__":
    host = os.getenv("MIDDLEWARE_HOST", "0.0.0.0")
    port = int(os.getenv("MIDDLEWARE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
