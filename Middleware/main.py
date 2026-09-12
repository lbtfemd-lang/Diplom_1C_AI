import sys
import os
import asyncio
import secrets
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

# Fix Windows httpx NO_PROXY issue with IPv6
if "NO_PROXY" in os.environ and "::" in os.environ["NO_PROXY"]:
    os.environ["NO_PROXY"] = ",".join([p for p in os.environ["NO_PROXY"].split(",") if "::" not in p])

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Depends, Query, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.models.api_models import ChatRequest, ChatResponse, MetadataRequest, VoiceTranscribeRequest, VoiceTranscribeResponse
from app.models.kanban_models import (
    KanbanTaskCreate, KanbanTaskUpdate, KanbanTaskMove,
    KanbanTaskResponse, KanbanBoardResponse, KanbanStatsResponse, COLUMN_CONFIG,
    TaskSource,
)
from app.models.auth_models import (
    LoginRequest, LoginResponse, UserCreate, UserUpdate, UserResponse,
    DepartmentCreate, DepartmentUpdate, DepartmentResponse, NotificationResponse,
    ChangePasswordRequest,
)
from app.services.llm_service import llm_service
from app.services.metadata_service import metadata_service
from app.services.kanban_service import kanban_service
from app.services.auth_service import auth_service
from app.services.voice_service import voice_service
from app.services.telegram_bot import telegram_bot_service
from app.services.vk_bot import vk_bot_service
from app.services.email_service import email_service

from app.models.compliance_models import (
    CounterpartyCheckRequest, CounterpartyCheckResponse,
    PaymentAuditRequest, PaymentAuditResponse
)
from app.models.margin_models import (
    DealCalculationRequest, DealCalculationResponse
)
from app.models.debt_models import (
    PenaltyCalculationRequest, PenaltyCalculationResponse,
    PreTrialClaimRequest, PreTrialClaimResponse
)
from app.models.stock_models import (
    InventoryAnalysisRequest, InventoryAnalysisResponse
)
from app.models.ocr_models import (
    InvoiceParseRequest, InvoiceParseResponse
)

from app.services.compliance_service import compliance_service
from app.services.margin_service import margin_service
from app.services.debt_service import debt_service
from app.services.stock_rebalancing_service import stock_service
from app.services.ocr_service import ocr_service


from typing import Any, Dict, List, Optional
import io
import uvicorn

@asynccontextmanager
async def _lifespan(app_instance):
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret or jwt_secret in ("your_jwt_secret_key_here", "changeme"):
        logger.warning("JWT_SECRET is not properly configured. Set a strong secret in .env!")
    api_key = os.getenv("FIREWORKS_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    if not api_key or api_key.startswith("your_"):
        logger.info("Zero-Cloud Mode: No external LLM API key configured. Autonomous Offline Fallback Engine is active.")

    # Start Omnichannel Background Polling Tasks
    tg_task = None
    vk_task = None
    email_task = None
    if telegram_bot_service.bot_token:
        tg_task = asyncio.create_task(telegram_bot_service.start_polling(_internal_bot_chat_handler))
    if vk_bot_service.access_token and vk_bot_service.group_id:
        vk_task = asyncio.create_task(vk_bot_service.start_polling(_internal_bot_chat_handler))
    if email_service.is_imap_configured:
        email_task = asyncio.create_task(email_service.start_imap_listener(_internal_bot_chat_handler))

    yield

    if tg_task:
        telegram_bot_service.stop_polling()
        tg_task.cancel()
    if vk_task:
        vk_bot_service.stop_polling()
        vk_task.cancel()
    if email_task:
        email_service.stop_listening()
        email_task.cancel()


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
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def _request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "-")
    logger.info("%s %s req_id=%s", request.method, request.url.path, request_id)
    response = await call_next(request)
    return response


api_key_scheme = APIKeyHeader(name="X-Auth-Token", auto_error=False)


async def get_current_user(request: Request, token: str = Security(api_key_scheme)) -> dict:
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            else:
                token = auth_header.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = auth_service.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = auth_service.get_user_by_id(payload.get("user_id"))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def get_optional_user(request: Request, token: str = Security(api_key_scheme)) -> Optional[dict]:
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            else:
                token = auth_header.strip()
    if not token:
        return None
    try:
        return await get_current_user(request, token)
    except HTTPException:
        return None


def require_role(user: dict, *roles):
    if user["role"] not in roles and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions")


@app.get("/api", response_model=Dict[str, Any])
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


@app.post("/auth/change-password", response_model=Dict[str, Any])
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    success = auth_service.change_password(user["id"], req.old_password, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid old password or password change failed")
    return {"status": "ok", "message": "Password updated successfully"}


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
        logger.error("Metadata update failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("200/minute")
async def chat_endpoint(request: Request, req: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        # Resolve acting user identity and role
        if user.get("role") == "service_bridge":
            # A claimed username is not proof of identity, even if it exists in DB.
            # Privileged requests must use the end user's own JWT.
            acting_role = "employee"
            user_role = acting_role
            caller_name = user.get("username", "1c_service")
        else:
            user_role = user.get("role", "employee")
            caller_name = user.get("username", "user")

        response_data = await llm_service.generate_response(req.messages, context=req.context, user_role=user_role)
        action = response_data.get("action")

        if action == "create_kanban_task" and response_data.get("data"):
            data = response_data["data"]
            task = kanban_service.create_task(
                title=data.get("title", "Новая задача"),
                description=data.get("description"),
                column=data.get("column", "todo"),
                priority=data.get("priority", "medium"),
                assignee=caller_name if user_role == "employee" else data.get("assignee", caller_name),
                due_date=data.get("due_date"),
                tags=data.get("tags"),
                source="chat",
                department_id=user.get("department_id"),
                created_by=caller_name,
            )
            response_data["data"]["task_id"] = task["id"]
            response_data["text"] += f"\n\nЗадача #{task['id']} создана и добавлена в колонку «{task['column']}»."

        return ChatResponse(
            role="assistant",
            text=response_data["text"],
            action=response_data.get("action"),
            data=response_data.get("data"),
            provider_used=response_data.get("provider_used"),
            is_fallback=response_data.get("is_fallback", False),
            model_name=response_data.get("model_name"),
        )
    except Exception as e:
        logger.error("Chat processing failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from None


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

        if user["role"] in ("employee", "service_bridge") and task.assignee and task.assignee != user["username"]:
            raise HTTPException(status_code=403, detail="Employees can only create tasks for themselves")
        if user["role"] not in ("admin", "director", "cfo") and dept_id != user.get("department_id"):
            raise HTTPException(status_code=403, detail="Cannot create tasks for another department")

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
        logger.error("Task creation failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from None


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
    if not kanban_service.can_access_task(task_id, user):
        raise HTTPException(status_code=403, detail="Access denied")
    return result


@app.put("/kanban/tasks/{task_id}", response_model=KanbanTaskResponse)
async def update_task(task_id: int, task: KanbanTaskUpdate, user: dict = Depends(get_current_user)):
    try:
        existing = kanban_service.get_task(task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        if not kanban_service.can_access_task(task_id, user):
            raise HTTPException(status_code=403, detail="Access denied")

        updates = {k: v for k, v in task.model_dump().items() if v is not None}
        if user["role"] in ("employee", "service_bridge") and updates.get("assignee", user["username"]) != user["username"]:
            raise HTTPException(status_code=403, detail="Cannot reassign tasks to another user")
        if user["role"] not in ("admin", "director", "cfo") and "department_id" in updates and updates["department_id"] != user.get("department_id"):
            raise HTTPException(status_code=403, detail="Cannot transfer tasks to another department")
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
        logger.error("Task update failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@app.post("/kanban/tasks/move", response_model=KanbanTaskResponse)
async def move_task(move: KanbanTaskMove, user: dict = Depends(get_current_user)):
    try:
        existing = kanban_service.get_task(move.task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Task not found")
        if not kanban_service.can_access_task(move.task_id, user):
            raise HTTPException(status_code=403, detail="Access denied")

        result = kanban_service.move_task(move.task_id, move.column.value, move.position)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Task move failed (%s)", type(e).__name__)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@app.delete("/kanban/tasks/{task_id}", response_model=Dict[str, Any])
async def delete_task(task_id: int, user: dict = Depends(get_current_user)):
    existing = kanban_service.get_task(task_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Task not found")
    if user["role"] != "admin" and existing.get("created_by") != user["username"]:
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


# ─── FINANCIAL & OPERATIONAL MONITOR API ────────────────────────────────────

_live_financial_snapshot: Optional[Dict[str, Any]] = None


@app.post("/analytics/1c/sync-financial-snapshot")
async def sync_financial_snapshot(snapshot: Dict[str, Any], user: dict = Depends(get_current_user)):
    """
    Receives live aggregated registers and balances from 1C:Enterprise HTTP sync.
    Accepts snapshot data from 1C scheduled jobs or ad-hoc 1C export.
    """
    require_role(user, "admin", "service_bridge", "cfo", "director")
    global _live_financial_snapshot
    import datetime
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    snapshot["timestamp"] = now_str
    snapshot["synced_at"] = datetime.datetime.now().isoformat()
    snapshot["is_mock_data"] = False
    snapshot["mode"] = "live_1c_sync"
    _live_financial_snapshot = snapshot
    return {
        "status": "ok",
        "message": "Финансовые регистры успешно синхронизированы с 1С:Предприятие",
        "timestamp": now_str,
    }


@app.get("/analytics/monitor")
async def get_financial_monitor(user: dict = Depends(get_current_user)):
    require_role(user, "director", "cfo", "admin")
    """
    Returns live aggregated KPIs and registers from 1C:Enterprise (SmallBusinessDemo):
    - Real cash balance from AccumulationRegister.ДенежныеСредства
    - Creditors obligations from AccumulationRegister.РасчетыСПоставщиками
    - Stalled customer orders from AccumulationRegister.ЗаказыПокупателей
    - Stalled stock from AccumulationRegister.Запасы
    - Calculated 7-day liquidity cash gap
    """
    global _live_financial_snapshot
    if _live_financial_snapshot is not None:
        return _live_financial_snapshot

    import datetime
    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    return {
        "timestamp": now_str,
        "mode": "demo_snapshot",
        "source": "Контрольный срез демо-базы 1С:УНФ 3.0 (ООО «УНФ Трейд Сервис»)",
        "is_mock_data": True,
        "sync_available": True,
        "sync_endpoint": "POST /analytics/1c/sync-financial-snapshot",
        "kpi": {
            "cash_balance": 69825848.00,
            "cash_gap": 0.00,
            "liquidity_reserve": 67067978.00,
            "stalled_orders_amount": 174700.00,
            "stalled_orders_count": 2,
            "dead_stock_amount": 168250.00,
            "dead_stock_count": 2,
            "creditors_amount": 2757870.28,
            "debtors_amount": 0.00
        },
        "creditors": [
            {
                "status": "К оплате",
                "partner": 'ООО "КабельСнабСервис"',
                "contract": "Договор поставки № 12",
                "debt": 1420500.00,
                "due_date": "05.09.2026",
                "urgency": "high"
            },
            {
                "status": "К оплате",
                "partner": 'ЗАО "Световые Системы"',
                "contract": "Основной договор",
                "debt": 890370.28,
                "due_date": "04.09.2026",
                "urgency": "medium"
            },
            {
                "status": "Плановый",
                "partner": "ИП Григорьев С.В.",
                "contract": "Разовый счет №41",
                "debt": 447000.00,
                "due_date": "08.09.2026",
                "urgency": "low"
            }
        ],
        "dead_stock": [
            {
                "code": "00-0000124",
                "sku": "КБ-325",
                "name": "Кабель силовой ВВГнг-LS 3x2.5",
                "warehouse": "Основной склад",
                "quantity": "1 200 м",
                "cost": 96000.00,
                "days_idle": 142
            },
            {
                "code": "00-0000189",
                "sku": "СВ-LED36",
                "name": "Светильник светодиодный LED 36W",
                "warehouse": "Склад готовой продукции",
                "quantity": "85 шт",
                "cost": 72250.00,
                "days_idle": 118
            }
        ]
    }


# ─── RUSSIAN BUSINESS MODULES (115-ФЗ, MARGIN, DEBT, STOCK, OCR) ──────────

@app.post("/business/compliance/check-counterparty", response_model=CounterpartyCheckResponse)
async def check_counterparty_endpoint(req: CounterpartyCheckRequest, user: dict = Depends(get_current_user)):
    """Проверка благонадежности контрагента по ИНН (ст. 54.1 НК РФ)"""
    require_role(user, "director", "cfo", "manager", "admin")
    return compliance_service.check_counterparty(req)


@app.post("/business/compliance/audit-payment", response_model=PaymentAuditResponse)
async def audit_payment_endpoint(req: PaymentAuditRequest, user: dict = Depends(get_current_user)):
    """Аудит платежного поручения на соответствие 115-ФЗ и критериям Росфинмониторинга"""
    require_role(user, "director", "cfo", "admin")
    return compliance_service.audit_payment(req)


@app.post("/business/margin/calculate-deal", response_model=DealCalculationResponse)
async def calculate_deal_margin_endpoint(req: DealCalculationRequest, user: dict = Depends(get_current_user)):
    """Расчет юнит-экономики сделки, НДС 20%, маржинальности и автоматическое согласование скидки"""
    require_role(user, "director", "cfo", "manager", "admin")
    return margin_service.calculate_deal(req, created_by=user.get("username", "manager"))


@app.post("/business/debt/calculate-penalty", response_model=PenaltyCalculationResponse)
async def calculate_debt_penalty_endpoint(req: PenaltyCalculationRequest, user: dict = Depends(get_current_user)):
    """Расчет процентов по ст. 395 ГК РФ по периодам действия ключевой ставки ЦБ РФ"""
    require_role(user, "director", "cfo", "manager", "admin")
    return debt_service.calculate_penalty(req)


@app.post("/business/debt/generate-claim", response_model=PreTrialClaimResponse)
async def generate_debt_claim_endpoint(req: PreTrialClaimRequest, user: dict = Depends(get_current_user)):
    """Формирование официальной досудебной претензии с расчетом процентов и отправкой должнику"""
    require_role(user, "director", "cfo", "admin")
    return debt_service.generate_pre_trial_claim(req)


@app.post("/business/stock/analyze-inventory", response_model=InventoryAnalysisResponse)
async def analyze_inventory_endpoint(req: InventoryAnalysisRequest, user: dict = Depends(get_current_user)):
    """Анализ запасов: расчет точек перезаказа ROP, формулы Уилсона EOQ, неликвидов и заказа поставщику"""
    require_role(user, "director", "cfo", "warehouse", "manager", "admin")
    return stock_service.analyze_inventory(req)


@app.post("/business/ocr/parse-invoice", response_model=InvoiceParseResponse)
async def parse_invoice_endpoint(req: InvoiceParseRequest, user: dict = Depends(get_current_user)):
    """Интеллектуальный разбор счетов/УПД, сверка со справочником 1С и валидация НДС 20%"""
    require_role(user, "director", "cfo", "warehouse", "manager", "admin")
    return ocr_service.parse_invoice(req)


# ─── 1C KANBAN SYNC API ───────────────────────────────────────────────────────

@app.get("/kanban/sync/1c", response_model=Dict[str, Any])
async def get_tasks_for_1c(user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    tasks = kanban_service.get_tasks_for_1c_sync()
    return {"tasks": tasks, "count": len(tasks)}


@app.post("/kanban/sync/1c", response_model=Dict[str, Any])
async def mark_tasks_synced(task_ids: List[int], user: dict = Depends(get_current_user)):
    require_role(user, "admin")
    kanban_service.mark_synced(task_ids)
    return {"status": "ok", "synced": len(task_ids)}


# ─── VOICE RECORDING & TRANSCRIBING ──────────────────────────────────────────

@app.post("/voice/record/start")
def start_voice_recording(user: dict = Depends(get_current_user)):
    """Start Windows microphone recording (requires authorized user)"""
    return voice_service.start_recording()


@app.post("/voice/record/stop", response_model=VoiceTranscribeResponse)
async def stop_voice_recording(user: dict = Depends(get_current_user)):
    """Stop Windows microphone recording and transcribe (requires authorized user)"""
    res = await voice_service.stop_recording_and_transcribe(language="ru")
    return VoiceTranscribeResponse(**res)


@app.post("/voice/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(req: VoiceTranscribeRequest, user: dict = Depends(get_current_user)):
    """
    Transcribe audio base64 (webm/wav/ogg) to text using Whisper / Gemini.
    Requires an authorized user: распознавание расходует квоту внешнего провайдера.
    """
    res = await voice_service.transcribe_audio(
        audio_base64=req.audio_base64,
        audio_format=req.format or "webm",
        language=req.language or "ru"
    )
    return VoiceTranscribeResponse(**res)



# ─── MESSENGER BOT INTEGRATIONS ───────────────────────────────────────────────

async def _internal_bot_chat_handler(
    query_text: str,
    user_name: str,
    channel: str = "telegram",
    user_role: Optional[str] = None
) -> str:
    """Helper to process bot requests through LLM orchestrator with real 1C data enrichment and omnichannel visual styling"""
    try:
        from app.models.api_models import Message
        from app.services.omnichannel_formatter import omnichannel_formatter

        # Display names and email addresses do not authenticate an account.
        # Only the authenticated simulation routes may supply an explicit role.
        if user_role is None:
            user_role = "employee"

        q_lower = query_text.lower().strip()

        # RBAC verification for financial commands
        financial_keywords = (
            "разрыв", "кассовый разрыв", "/gap",
            "деньги", "баланс", "остатки", "/balance",
            "должники", "дебиторы", "/debts", "дебиторка",
            "кредиторы", "долги наши", "/creditors"
        )
        if any(w in q_lower for w in financial_keywords):
            if user_role not in ("director", "cfo", "admin"):
                if channel == "telegram":
                    return (
                        f"⛔ <b>Доступ ограничен (RBAC 1С).</b>\n\n"
                        f"Запрос финансовых показателей (кассовый разрыв, баланс, кредиторы/дебиторы) "
                        f"требует полномочий <code>director</code>, <code>cfo</code> или <code>admin</code>.\n"
                        f"Текущая роль: <code>{user_role}</code>."
                    )
                else:
                    return (
                        f"⛔ Доступ ограничен (RBAC 1С). "
                        f"Запрос финансовых показателей требует полномочий director, cfo или admin. "
                        f"Текущая роль: {user_role}."
                    )

        # 1. Быстрый роутинг базовых команд 1С:УНФ
        if any(w in q_lower for w in ("разрыв", "кассовый разрыв", "/gap")):
            return omnichannel_formatter.format_cash_gap(channel=channel)
        if any(w in q_lower for w in ("деньги", "баланс", "остатки", "/balance")):
            return omnichannel_formatter.format_balance(channel=channel)
        if any(w in q_lower for w in ("должники", "дебиторы", "/debts", "дебиторка")):
            return omnichannel_formatter.format_debtors(channel=channel)
        if any(w in q_lower for w in ("заказы", "сорванные заказы", "/orders")):
            return omnichannel_formatter.format_stalled_orders(channel=channel)
        if any(w in q_lower for w in ("неликвиды", "склад", "/stock", "неликвид")):
            return omnichannel_formatter.format_dead_stock(channel=channel)
        if any(w in q_lower for w in ("кредиторы", "долги наши", "/creditors")):
            return omnichannel_formatter.format_creditors(channel=channel)
        if any(w in q_lower for w in ("канбан", "задачи", "/tasks", "поручения")):
            from app.services.kanban_service import kanban_service
            if user_role in ("director", "cfo", "manager", "admin"):
                tasks = kanban_service.get_all_tasks()
            else:
                tasks = kanban_service.get_tasks_for_user(
                    user_id=0, role=user_role, username=user_name
                )
            return omnichannel_formatter.format_kanban_tasks(tasks, channel=channel)

        # 2. Обработка через LLM
        msgs = [Message(role="user", text=query_text)]
        resp = await llm_service.process_chat(msgs, user_role=user_role)
        text = resp.get("text") or resp.get("response", "")
        action = resp.get("action")

        # Обогащение реальными данными 1С:УНФ для мессенджеров с RBAC-проверкой
        if action == "cash_gap_forecast":
            if user_role not in ("director", "cfo", "admin"):
                return "⛔ Доступ ограничен к финансовым данным."
            return omnichannel_formatter.format_cash_gap(channel=channel)
        elif action == "get_cash_balance":
            if user_role not in ("director", "cfo", "admin"):
                return "⛔ Доступ ограничен к финансовым данным."
            return omnichannel_formatter.format_balance(channel=channel)
        elif action == "audit_stalled_orders":
            return omnichannel_formatter.format_stalled_orders(channel=channel)
        elif action == "get_dead_stock":
            return omnichannel_formatter.format_dead_stock(channel=channel)
        elif action == "get_creditors":
            if user_role not in ("director", "cfo", "admin"):
                return "⛔ Доступ ограничен к финансовым данным."
            return omnichannel_formatter.format_creditors(channel=channel)
        elif action == "get_debtors":
            if user_role not in ("director", "cfo", "admin"):
                return "⛔ Доступ ограничен к финансовым данным."
            return omnichannel_formatter.format_debtors(channel=channel)
        elif action in ("get_kanban_tasks", "show_kanban"):
            from app.services.kanban_service import kanban_service
            if user_role in ("director", "cfo", "manager", "admin"):
                tasks = kanban_service.get_all_tasks()
            else:
                tasks = kanban_service.get_tasks_for_user(
                    user_id=0, role=user_role, username=user_name
                )
            return omnichannel_formatter.format_kanban_tasks(tasks, channel=channel)

        if action and action not in ("expert_answer", "create_kanban_task", "get_kanban_tasks", "show_kanban"):
            if channel == "telegram":
                text += f"\n\n⚡ <b>Действие в 1С:</b> <code>{action}</code>"
            else:
                text += f"\n\n⚡ Действие в 1С: {action}"

        return omnichannel_formatter.format_llm_response(text, channel=channel)
    except Exception as e:
        logger.error("Bot chat handler error: %s", e)
        return "Произошла ошибка при обработке запроса в 1С:УНФ."


# ─── OMNICHANNEL INTEGRATIONS (TELEGRAM, VK, EMAIL) ──────────────────────────

@app.get("/integrations/status")
async def get_integrations_status():
    """Returns the operational status of all external communication channels"""
    return {
        "channels": {
            "telegram": {
                "name": "Telegram Bot",
                "configured": bool(telegram_bot_service.bot_token),
                "mode": "live_webhook" if telegram_bot_service.bot_token else "sandbox_mock",
                "features": ["commands_25", "inline_keyboards", "voice_notes", "critical_alerts"]
            },
            "vk": {
                "name": "ВКонтакте (Callback API)",
                "configured": bool(vk_bot_service.access_token),
                "mode": "live_callback" if vk_bot_service.access_token else "sandbox_mock",
                "features": ["commands_menu", "interactive_keyboards", "analytics_reports"]
            },
            "email": {
                "name": "Корпоративная почта (SMTP)",
                "configured": email_service.is_smtp_configured,
                "mode": "live_smtp" if email_service.is_smtp_configured else "sandbox_outbox",
                "outbox_count": len(email_service.outbox),
                "features": ["order_ingestion", "executive_digest", "debt_claims", "trigger_alerts"]
            }
        }
    }


@app.post("/integrations/telegram/webhook")
async def telegram_webhook(update: Dict[str, Any], request: Request):
    """Telegram Bot Webhook endpoint with secret token validation"""
    secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if not secret_token:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured")
    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(header_secret.encode(), secret_token.encode()):
        raise HTTPException(status_code=403, detail="Invalid webhook secret token")
    res = await telegram_bot_service.process_webhook_update(update, _internal_bot_chat_handler)
    return res or {"status": "ignored"}


_tg_simulate_lock = asyncio.Lock()
_vk_simulate_lock = asyncio.Lock()


@app.post("/integrations/telegram/simulate")
async def telegram_simulate(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Simulate a Telegram message or command without external public IP (requires manager/director/cfo/admin)"""
    require_role(user, "director", "cfo", "manager", "admin")
    cb_data = payload.get("callback_data") or (payload.get("callback_query", {}).get("data") if isinstance(payload.get("callback_query"), dict) else None)
    text = payload.get("text", "/start")
    user_name = payload.get("user_name") or user.get("username") or "Руководитель"
    caller_role = user.get("role", "director")

    if cb_data:
        mock_update = {
            "update_id": 999999,
            "callback_query": {
                "id": "cb_1",
                "from": {"id": 10001, "first_name": user_name},
                "message": {"chat": {"id": 10001}},
                "data": cb_data
            }
        }
    else:
        mock_update = {
            "update_id": 999999,
            "message": {
                "message_id": 1,
                "chat": {"id": 10001, "first_name": user_name},
                "from": {"id": 10001, "first_name": user_name},
                "text": text
            }
        }
    sent_messages = []

    async def _sim_handler(q, u, channel="telegram"):
        return await _internal_bot_chat_handler(q, u, channel, user_role=caller_role)
    
    async with _tg_simulate_lock:
        original_send = telegram_bot_service.send_message
        async def mock_send(chat_id, msg_text, reply_markup=None, *args, **kwargs):
            sent_messages.append({
                "chat_id": chat_id,
                "text": msg_text,
                "reply_markup": reply_markup,
                "persistent_keyboard": kwargs.get("persistent_keyboard")
            })
        
        telegram_bot_service.send_message = mock_send
        try:
            res = await telegram_bot_service.process_webhook_update(mock_update, _sim_handler)
        finally:
            telegram_bot_service.send_message = original_send
        
    return {
        "status": "ok",
        "channel": "telegram",
        "input": cb_data or text,
        "result": res,
        "messages": sent_messages
    }


@app.post("/integrations/telegram/send")
async def telegram_send(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Direct message or broadcast to registered Telegram chats (requires authorized manager/director/admin)"""
    require_role(user, "director", "cfo", "manager", "admin")
    text = payload.get("text", "🔔 Сообщение от ассистента 1С:УНФ")
    chat_id = payload.get("chat_id")
    if chat_id:
        await telegram_bot_service.send_message(int(chat_id), text)
        return {"status": "ok", "delivered_to": [int(chat_id)]}
    elif telegram_bot_service.active_chat_ids:
        sent_to = []
        for cid in list(telegram_bot_service.active_chat_ids):
            await telegram_bot_service.send_message(cid, text)
            sent_to.append(cid)
        return {"status": "ok", "delivered_to": sent_to}
    else:
        return {"status": "warning", "message": "No active Telegram chats yet. Users must start @qelildiplom_bot first."}


@app.post("/integrations/vk/callback")
async def vk_callback(data: Dict[str, Any]):
    """VKontakte Community Callback API endpoint with secret check"""
    secret_key = os.getenv("VK_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=503, detail="VK callback is not configured")
    supplied_secret = data.get("secret", "")
    if not isinstance(supplied_secret, str) or not secrets.compare_digest(supplied_secret.encode(), secret_key.encode()):
        raise HTTPException(status_code=403, detail="Invalid secret key")
    return await vk_bot_service.process_callback_update(data, _internal_bot_chat_handler)


@app.post("/integrations/vk/simulate")
async def vk_simulate(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Simulate a VKontakte message without external public IP (requires manager/director/cfo/admin)"""
    require_role(user, "director", "cfo", "manager", "admin")
    text = payload.get("text", "Канбан")
    user_id = payload.get("user_id", 20002)
    caller_role = user.get("role", "manager")

    mock_data = {
        "type": "message_new",
        "object": {
            "message": {
                "id": 1,
                "from_id": user_id,
                "text": text
            }
        }
    }
    sent_messages = []

    async def _sim_handler(q, u, channel="vk"):
        return await _internal_bot_chat_handler(q, u, channel, user_role=caller_role)
    
    async with _vk_simulate_lock:
        original_send = vk_bot_service.send_message
        # Сигнатура должна принимать все аргументы боевого VKBotService.send_message
        # (в т.ч. with_keyboard=False для промежуточных статусных сообщений),
        # иначе симуляция падает с TypeError на части сценариев.
        async def mock_send(user_id, message=None, keyboard=None, with_keyboard=True, **kwargs):
            sent_messages.append({"user_id": user_id, "text": message, "keyboard": keyboard})


        vk_bot_service.send_message = mock_send
        try:
            res = await vk_bot_service.process_callback_update(mock_data, _sim_handler)
        finally:
            vk_bot_service.send_message = original_send

    return {
        "status": "ok",
        "channel": "vk",
        "input": text,
        "result": res,
        "messages": sent_messages
    }


@app.post("/integrations/vk/send")
async def vk_send(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Direct message to VKontakte user (requires authorized manager/director/admin)"""
    require_role(user, "director", "cfo", "manager", "admin")
    user_id = int(payload.get("user_id", 401122543))
    text = payload.get("text", "🔔 Сообщение от ассистента 1С:УНФ")
    await vk_bot_service.send_message(user_id=user_id, message=text)
    return {"status": "ok", "channel": "vk", "user_id": user_id}


@app.post("/integrations/email/incoming")
async def email_incoming(
    payload: Dict[str, Any],
    request: Request,
    user: Optional[dict] = Depends(get_optional_user),
):
    """
    Email-to-Order ingestion robot:
    Receives incoming customer email, parses order with AI, registers task in 1C Kanban.

    Защита по образцу telegram-вебхука: либо общий секрет в заголовке
    X-Email-Hook-Secret (для внешнего почтового робота), либо авторизованный
    пользователь. Иначе эндпоинт позволял бы любому анониму создавать задачи
    в Канбане и расходовать квоту LLM.
    """
    hook_secret = os.getenv("EMAIL_HOOK_SECRET")
    if hook_secret:
        if request.headers.get("X-Email-Hook-Secret") == hook_secret:
            pass
        elif user is None:
            logger.warning("Email ingestion rejected: invalid X-Email-Hook-Secret and no authenticated user")
            raise HTTPException(status_code=403, detail="Invalid hook secret")
    elif user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sender = payload.get("sender", "client@alfatrade.ru")
    subject = payload.get("subject", "Заказ на поставку кабеля и выключателей")
    body = payload.get("body", "Здравствуйте! Прошу выставить счет: Кабель ВВГнг-LS 50м, Выключатель автоматический 10 шт. Доставка на наш склад в Москве.")
    
    result = await email_service.process_incoming_email(
        sender=sender,
        subject=subject,
        body=body,
        chat_handler=_internal_bot_chat_handler
    )
    return result


@app.post("/integrations/email/send")
async def email_send(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Send an email or financial report to counterparty/manager (requires authorized manager/director/admin)"""
    require_role(user, "director", "cfo", "manager", "admin")
    to_email = payload.get("to", "director@company.1c.ru")
    subject = payload.get("subject", "Уведомление 1С:УНФ")
    body = payload.get("body", "Текст сообщения")
    return await email_service.send_email_async(to_email, subject, body)


@app.post("/integrations/email/digest")
async def email_send_digest(payload: Dict[str, Any] = None, user: dict = Depends(get_current_user)):
    """Generate and dispatch Morning Executive Digest"""
    require_role(user, "director", "cfo", "admin")
    recipient = payload.get("recipient", "director@company.1c.ru") if payload else "director@company.1c.ru"
    return await asyncio.to_thread(email_service.generate_executive_digest, recipient)


@app.post("/integrations/email/claim")
async def email_send_claim(payload: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Send an official debt claim with invoice breakdown to counterparty"""
    require_role(user, "director", "cfo", "admin")
    client_email = payload.get("to", "buh@alphatrade.ru")
    client_name = payload.get("counterparty", "ООО «АльфаТрейд»")
    debt = float(payload.get("amount", 540000.0))
    days = int(payload.get("overdue_days", 12))
    doc = payload.get("contract", "Договор № 01-П от 15.01.2026")
    return await asyncio.to_thread(
        email_service.send_debt_claim_email, client_email, client_name, debt, days, doc
    )


@app.get("/integrations/email/outbox")
async def email_get_outbox(user: dict = Depends(get_current_user)):
    """Get stored emails in sandbox outbox"""
    require_role(user, "director", "cfo", "admin")
    return {"outbox": email_service.get_outbox()}


@app.get("/qr/generate")
@app.post("/qr/generate")
async def generate_qr_code(
    text: str = Query(..., description="Text or payment URL to encode in QR"),
    box_size: int = Query(4, ge=1, le=20, description="Size of each box in pixels"),
    border: int = Query(2, ge=0, le=10, description="Border size"),
    user: dict = Depends(get_current_user),
):
    """
    Generate authentic, scan-ready QR code in Base64 PNG and Data URI format.
    """
    try:
        import qrcode
        import base64
        import io

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            "text": text,
            "png_base64": b64,
            "data_uri": f"data:image/png;base64,{b64}",
            "status": "success",
        }
    except Exception as e:
        logger.error("QR code generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"QR generation failed: {e}")


# ---------------------------------------------------------------------------
# Executive Web Portal (Web SPA)
# ---------------------------------------------------------------------------
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.get("/")
@app.get("/app")
async def serve_executive_portal():
    index_file = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"status": "ok", "service": "1C AI Assistant Middleware"}

@app.get("/styles.css")
async def serve_styles_fallback():
    return FileResponse(os.path.join(_static_dir, "styles.css"))

@app.get("/app.js")
async def serve_js_fallback():
    return FileResponse(os.path.join(_static_dir, "app.js"))



if __name__ == "__main__":
    host = os.getenv("MIDDLEWARE_HOST", "0.0.0.0")
    port = int(os.getenv("MIDDLEWARE_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
