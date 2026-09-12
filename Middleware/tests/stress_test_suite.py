"""
Automated Asyncio Stress-Testing and RBAC Penetration Suite
Tests:
1. Baseline HTTP Latency & Throughput (100 sequential & concurrent requests)
2. Concurrent Burst RAG (20 parallel requests to /chat with complex business intents)
3. Omnichannel Ingestion Burst (50 concurrent telegram/vk/email events)
4. SQLite Concurrency Stress (50 concurrent Kanban task writes/moves without locking)
5. RBAC Security & Penetration Suite (unauthenticated & unauthorized requests across all roles)
Produces:
tests/stress_test_report.md
"""

import sys
import os
import time
import asyncio
import statistics
import tempfile
from contextlib import ExitStack
from unittest.mock import patch
from typing import List, Dict, Any

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure Middleware is in Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport, HTTPTransport, AsyncHTTPTransport
import dotenv

# This standalone benchmark is deliberately local: no working .env, database,
# cloud inference or outgoing mail. It measures the offline middleware path.
_isolation = ExitStack()
_storage = _isolation.enter_context(tempfile.TemporaryDirectory(prefix="diplom-stress-"))
_settings = {key: "" for key in (
    "GEMINI_API_KEY", "OPENROUTER_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY", "FIREWORKS_API_KEY", "GIGACHAT_CREDENTIALS", "GIGACHAT_API_KEY",
    "YANDEX_API_KEY", "YANDEX_SPEECHKIT_API_KEY", "OLLAMA_HOST", "LOCAL_RUSSIAN_LLM",
    "OPENAI_BASE_URL", "LLM_BASE_URL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "VK_GROUP_TOKEN", "VK_GROUP_ID", "SMTP_USER", "SMTP_PASSWORD", "IMAP_USER",
    "IMAP_PASSWORD", "VK_BIND_IP", "SMTP_BIND_IP", "EMAIL_HOOK_SECRET",
)}
_settings.update(SQLITE_DB_PATH=os.path.join(_storage, "stress.db"),
    METADATA_DATA_DIR=_storage, METADATA_ML_ENABLED="false",
    JWT_SECRET="local-stress-secret-not-for-deployment", RATE_LIMIT_ENABLED="false", LOG_LEVEL="WARNING",
    TELEGRAM_WEBHOOK_SECRET="synthetic-stress-tg-secret", VK_SECRET_KEY="synthetic-stress-vk-secret",
    DIRECTOR_EMAIL="director@example.test", SMTP_FROM="sender@example.test")
_isolation.enter_context(patch.dict(os.environ, _settings))
_isolation.enter_context(patch.object(dotenv, "load_dotenv", return_value=False))


def _deny_network(*args, **kwargs):
    raise RuntimeError("External HTTP is forbidden in the local stress benchmark")


async def _deny_async_network(*args, **kwargs):
    _deny_network()


_isolation.enter_context(patch.object(HTTPTransport, "handle_request", _deny_network))
_isolation.enter_context(patch.object(AsyncHTTPTransport, "handle_async_request", _deny_async_network))

from main import app
from app.services.auth_service import auth_service
from app.services.kanban_service import kanban_service
from app.services.telegram_bot import telegram_bot_service

_isolation.enter_context(patch.object(telegram_bot_service, "active_chat_ids", set()))
_isolation.enter_context(patch.object(telegram_bot_service, "_register_chat", lambda chat_id: None))


def calculate_stats(latencies_ms: List[float]) -> Dict[str, float]:
    if not latencies_ms:
        return {"min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0}
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)
    return {
        "min": round(sorted_l[0], 2),
        "max": round(sorted_l[-1], 2),
        "mean": round(statistics.mean(sorted_l), 2),
        "p50": round(statistics.median(sorted_l), 2),
        "p95": round(sorted_l[int(0.95 * n) - 1], 2),
        "p99": round(sorted_l[int(0.99 * n) - 1], 2),
    }


async def run_baseline_latency_test(client: AsyncClient, n_requests: int = 100) -> Dict[str, Any]:
    print(f"\n[1/5] Running Baseline HTTP Latency Test ({n_requests} requests)...")
    latencies = []
    errors = 0

    start_total = time.perf_counter()
    for i in range(n_requests):
        t0 = time.perf_counter()
        try:
            resp = await client.get("/health")
            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
            if resp.status_code != 200:
                errors += 1
        except Exception as e:
            errors += 1

    total_time = time.perf_counter() - start_total
    rps = n_requests / total_time if total_time > 0 else 0
    stats = calculate_stats(latencies)

    print(f"  [OK] Completed {n_requests} requests in {total_time:.2f}s ({rps:.1f} RPS)")
    print(f"  [OK] Latency: Mean={stats['mean']}ms, p50={stats['p50']}ms, p95={stats['p95']}ms, p99={stats['p99']}ms, Errors={errors}")

    return {
        "test_name": "Baseline HTTP Latency (/health)",
        "requests": n_requests,
        "total_time_s": round(total_time, 2),
        "rps": round(rps, 1),
        "errors": errors,
        "stats": stats,
    }


async def run_concurrent_rag_test(client: AsyncClient, concurrency: int = 20) -> Dict[str, Any]:
    print(f"\n[2/5] Running Concurrent Burst RAG Test ({concurrency} parallel requests)...")
    prompts = [
        "Покажи прогноз кассового разрыва на неделю",
        "Сколько денег на расчетных счетах?",
        "Кто главные должники?",
        "Какие остатки залежались на складе?",
        "Сформируй утреннюю сводку",
        "Какая ситуация с платежами поставщикам?",
        "Покажи список задач на Канбан-доске",
        "Есть ли сорванные заказы покупателей?",
    ]

    # Pre-authenticate as director
    login_resp = await client.post("/auth/login", json={"username": "director", "password": "director123"})
    token = login_resp.json().get("access_token", "")
    headers = {"Authorization": f"Bearer {token}", "X-Auth-Token": token}

    latencies = []
    errors = 0
    action_counts = {}

    async def single_chat(query: str):
        nonlocal errors
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                "/chat",
                json={"messages": [{"role": "user", "text": query}], "user_role": "director"},
                headers=headers,
                timeout=30.0,
            )
            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
            if resp.status_code == 200:
                data = resp.json()
                action = data.get("action", "none")
                action_counts[action] = action_counts.get(action, 0) + 1
            else:
                errors += 1
        except Exception as e:
            errors += 1

    start_total = time.perf_counter()
    tasks = [single_chat(prompts[i % len(prompts)]) for i in range(concurrency)]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_total

    rps = concurrency / total_time if total_time > 0 else 0
    stats = calculate_stats(latencies)

    print(f"  [OK] Completed {concurrency} parallel RAG queries in {total_time:.2f}s ({rps:.1f} RPS)")
    print(f"  [OK] Latency: Mean={stats['mean']}ms, p50={stats['p50']}ms, p95={stats['p95']}ms, Errors={errors}")
    print(f"  [OK] Actions resolved: {action_counts}")

    return {
        "test_name": f"Concurrent Burst RAG ({concurrency} parallel requests)",
        "requests": concurrency,
        "total_time_s": round(total_time, 2),
        "rps": round(rps, 1),
        "errors": errors,
        "actions_resolved": action_counts,
        "stats": stats,
    }


async def run_omnichannel_burst_test(client: AsyncClient, n_events: int = 50) -> Dict[str, Any]:
    print(f"\n[3/5] Running Omnichannel Ingestion Burst Test ({n_events} concurrent events)...")
    from app.services.email_service import email_service
    orig_send_email = email_service.send_email

    # Заглушка вместо реального SMTP: нагрузочный прогон не должен отправлять почту
    # наружу и не должен упираться в сетевой таймаут. Сигнатура повторяет боевую
    # (вызовы идут по ключевым словам to_email=/subject=/body=).
    def _mock_send_email(to_email, subject, body, html_body=None, email_type="general"):
        record = {
            "id": len(email_service.outbox) + 1,
            "to": to_email,
            "subject": subject,
            "type": email_type,
            "delivery": "mock_smtp_sent",
        }
        email_service.outbox.insert(0, record)
        return {"status": "ok", "email_id": record["id"], "delivery": "mock_smtp_sent"}

    email_service.send_email = _mock_send_email

    # Боевой путь приёма сообщений — вебхуки (/telegram/webhook, /vk/callback).
    # Отладочные /simulate-маршруты сериализуются под глобальным asyncio.Lock,
    # потому что подменяют send_message у общего экземпляра сервиса; замер по ним
    # характеризовал бы демо-обвязку, а не пропускную способность приёма.
    # Здесь исходящая отправка подменяется один раз на весь прогон, что снимает
    # необходимость в локе и позволяет нагружать реальные обработчики.
    from app.services.telegram_bot import telegram_bot_service
    from app.services.vk_bot import vk_bot_service

    orig_tg_send = telegram_bot_service.send_message
    orig_vk_send = vk_bot_service.send_message
    outbound = {"telegram": 0, "vk": 0}

    async def _mock_tg_send(chat_id, message=None, reply_markup=None, *args, **kwargs):
        outbound["telegram"] += 1

    async def _mock_vk_send(user_id, message=None, keyboard=None, with_keyboard=True, **kwargs):
        outbound["vk"] += 1

    telegram_bot_service.send_message = _mock_tg_send
    vk_bot_service.send_message = _mock_vk_send

    # Synthetic webhook secrets were installed by the isolated bootstrap.

    # Pre-authenticate as manager for simulation routes
    login_resp = await client.post("/auth/login", json={"username": "manager", "password": "manager123"})
    token = login_resp.json().get("access_token", "")
    headers = {"Authorization": f"Bearer {token}", "X-Auth-Token": token}

    latencies = []
    errors = 0
    error_details = []
    channel_counts = {"telegram": 0, "vk": 0, "email": 0}

    async def send_tg(i: int):
        nonlocal errors
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                "/integrations/telegram/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": os.environ["TELEGRAM_WEBHOOK_SECRET"]},
                json={
                    "update_id": 900000 + i,
                    "message": {
                        "message_id": i,
                        "chat": {"id": 10000 + i, "first_name": f"Client_{i}"},
                        "from": {"id": 10000 + i, "first_name": f"Client_{i}"},
                        "text": f"Заказ #{i}: кабель ВВГнг 20м",
                    },
                },
            )
            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
            if resp.status_code == 200:
                channel_counts["telegram"] += 1
            else:
                errors += 1
                error_details.append(f"telegram:HTTP{resp.status_code}")
        except Exception as e:
            errors += 1
            error_details.append(f"telegram:{type(e).__name__}")

    async def send_vk(i: int):
        nonlocal errors
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                "/integrations/vk/callback",
                json={
                    "type": "message_new",
                    "secret": os.environ["VK_SECRET_KEY"],
                    "object": {
                        "message": {
                            "id": i,
                            "from_id": 20000 + i,
                            "text": f"Заявка VK #{i}: выключатель 5 шт",
                        }
                    },
                },
            )
            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
            if resp.status_code == 200:
                channel_counts["vk"] += 1
            else:
                errors += 1
                error_details.append(f"vk:HTTP{resp.status_code}")
        except Exception as e:
            errors += 1
            error_details.append(f"vk:{type(e).__name__}")

    async def send_email(i: int):
        nonlocal errors
        t0 = time.perf_counter()
        try:
            resp = await client.post(
                "/integrations/email/incoming",
                json={
                    "sender": f"partner_{i}@electro-supplier.ru",
                    "subject": f"Срочный заказ на поставку #{i}",
                    "body": f"Прошу выставить счет на партию ламп LED 36W в количестве {10 + i} шт.",
                },
                headers=headers,
            )
            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
            if resp.status_code == 200:
                channel_counts["email"] += 1
            else:
                errors += 1
                error_details.append(f"email:HTTP{resp.status_code}")
        except Exception as e:
            errors += 1
            error_details.append(f"email:{type(e).__name__}")

    tasks = []
    for i in range(n_events):
        if i % 3 == 0:
            tasks.append(send_tg(i))
        elif i % 3 == 1:
            tasks.append(send_vk(i))
        else:
            tasks.append(send_email(i))

    start_total = time.perf_counter()
    try:
        await asyncio.gather(*tasks)
    finally:
        email_service.send_email = orig_send_email
        telegram_bot_service.send_message = orig_tg_send
        vk_bot_service.send_message = orig_vk_send

    total_time = time.perf_counter() - start_total

    rps = n_events / total_time if total_time > 0 else 0
    stats = calculate_stats(latencies)

    print(f"  [OK] Completed {n_events} omnichannel events in {total_time:.2f}s ({rps:.1f} RPS)")
    print(f"  [OK] Ingestion distribution: {channel_counts}")
    print(f"  [OK] Latency: Mean={stats['mean']}ms, p50={stats['p50']}ms, p95={stats['p95']}ms, Errors={errors}")
    if error_details:
        from collections import Counter
        print(f"  [!!] Error breakdown: {dict(Counter(error_details))}")

    return {
        "test_name": f"Omnichannel Ingestion Burst ({n_events} concurrent events)",
        "requests": n_events,
        "total_time_s": round(total_time, 2),
        "rps": round(rps, 1),
        "errors": errors,
        "error_details": dict(__import__("collections").Counter(error_details)),
        "channel_counts": channel_counts,
        "stats": stats,
    }


async def run_sqlite_concurrency_test(client: AsyncClient, n_writes: int = 50) -> Dict[str, Any]:
    print(f"\n[4/5] Running SQLite Concurrency & WAL Locking Test ({n_writes} concurrent writes/moves)...")
    latencies = []
    errors = 0
    db_lock_errors = 0
    created_ids = []

    # Login as manager
    login_resp = await client.post("/auth/login", json={"username": "manager", "password": "manager123"})
    token = login_resp.json().get("access_token", "")
    headers = {"Authorization": f"Bearer {token}", "X-Auth-Token": token}

    async def create_and_move_task(i: int):
        nonlocal errors, db_lock_errors
        t0 = time.perf_counter()
        try:
            # 1. Create task
            res1 = await client.post(
                "/kanban/tasks",
                json={
                    "title": f"Стресс-задача #{i}",
                    "description": f"Автоматизированный тест конкурентности SQLite #{i}",
                    "priority": "medium",
                    "column": "todo",
                    "source": "1c",
                },
                headers=headers,
            )
            if res1.status_code != 200:
                errors += 1
                return

            task_id = res1.json().get("id")
            created_ids.append(task_id)

            # 2. Move to in_progress
            res2 = await client.post(
                "/kanban/tasks/move",
                json={"task_id": task_id, "column": "in_progress"},
                headers=headers,
            )
            if res2.status_code != 200:
                errors += 1

            # 3. Move to done
            res3 = await client.post(
                "/kanban/tasks/move",
                json={"task_id": task_id, "column": "done"},
                headers=headers,
            )
            if res3.status_code != 200:
                errors += 1

            t_diff = (time.perf_counter() - t0) * 1000.0
            latencies.append(t_diff)
        except Exception as e:
            errors += 1
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                db_lock_errors += 1

    start_total = time.perf_counter()
    tasks = [create_and_move_task(i) for i in range(n_writes)]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_total

    total_ops = n_writes * 3  # create + move + move
    rps = total_ops / total_time if total_time > 0 else 0
    stats = calculate_stats(latencies)

    print(f"  [OK] Completed {total_ops} SQLite operations ({n_writes} tasks created & moved) in {total_time:.2f}s ({rps:.1f} OPS)")
    print(f"  [OK] Database lock errors: {db_lock_errors} (SQLite WAL mode + pool)")
    print(f"  [OK] Operation Latency: Mean={stats['mean']}ms, p50={stats['p50']}ms, p95={stats['p95']}ms, Errors={errors}")

    return {
        "test_name": f"SQLite Concurrency ({n_writes} tasks created & moved = {total_ops} ACID operations)",
        "requests": total_ops,
        "total_time_s": round(total_time, 2),
        "ops_per_sec": round(rps, 1),
        "errors": errors,
        "db_lock_errors": db_lock_errors,
        "stats": stats,
    }


async def run_rbac_penetration_test(client: AsyncClient) -> Dict[str, Any]:
    print(f"\n[5/5] Running RBAC Security & Penetration Suite...")

    # Log in all roles to acquire tokens
    roles_credentials = [
        ("anonymous", None),
        ("employee", "employee123"),
        ("warehouse", "warehouse123"),
        ("manager", "manager123"),
        ("cfo", "cfo123"),
        ("director", "director123"),
    ]

    tokens = {}
    for role, pwd in roles_credentials:
        if pwd:
            r = await client.post("/auth/login", json={"username": role, "password": pwd})
            if r.status_code == 200:
                tokens[role] = r.json()["access_token"]
            else:
                tokens[role] = None
        else:
            tokens[role] = None

    # Endpoints matrix to audit
    endpoints_to_test = [
        {
            "name": "Финансовый монитор (/analytics/monitor)",
            "method": "GET",
            "url": "/analytics/monitor",
            "body": None,
            "allowed_roles": ["director", "cfo", "admin"],
        },
        {
            "name": "Исходящие email (/integrations/email/outbox)",
            "method": "GET",
            "url": "/integrations/email/outbox",
            "body": None,
            "allowed_roles": ["director", "cfo", "admin"],
        },
        {
            "name": "Утренний дайджест руководителя (/integrations/email/digest)",
            "method": "POST",
            "url": "/integrations/email/digest",
            "body": {"recipient": "director@test.ru"},
            "allowed_roles": ["director", "cfo", "admin"],
        },
        {
            "name": "115-ФЗ: Аудит платежа (/business/compliance/audit-payment)",
            "method": "POST",
            "url": "/business/compliance/audit-payment",
            "body": {
                "payer_inn": "7707083893",
                "recipient_inn": "7724123456",
                "amount": 500000.0,
                "payment_purpose": "Оплата за электрооборудование",
            },
            "allowed_roles": ["director", "cfo", "admin"],
        },
        {
            "name": "115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty)",
            "method": "POST",
            "url": "/business/compliance/check-counterparty",
            "body": {"inn": "7707083893"},
            "allowed_roles": ["director", "cfo", "manager", "admin"],
        },
        {
            "name": "Юнит-экономика и маржа (/business/margin/calculate-deal)",
            "method": "POST",
            "url": "/business/margin/calculate-deal",
            "body": {
                "customer_name": "ООО Тест",
                "items": [{
                    "sku": "KB-325",
                    "name": "Кабель",
                    "quantity": 100,
                    "purchase_price": 50,
                    "selling_price": 70,
                }],
            },
            "allowed_roles": ["director", "cfo", "manager", "admin"],
        },
        {
            "name": "Досудебная претензия ст. 395 (/business/debt/generate-claim)",
            "method": "POST",
            "url": "/business/debt/generate-claim",
            "body": {
                "debtor_name": "ООО Должник",
                "debtor_inn": "7707083893",
                "contract_number": "Д-1",
                "contract_date": "2025-01-01",
                "invoice_number": "С-1",
                "invoice_date": "2025-02-01",
                "principal_debt": 100000,
                "due_date": "2025-03-01",
            },
            "allowed_roles": ["director", "cfo", "admin"],
        },
        {
            "name": "Автозаказ ROP/EOQ (/business/stock/analyze-inventory)",
            "method": "POST",
            "url": "/business/stock/analyze-inventory",
            "body": {
                "items": [{
                    "sku": "KB-1",
                    "name": "Кабель",
                    "current_stock": 10,
                    "daily_sales_avg": 5,
                    "lead_time_days": 3,
                    "unit_cost": 100,
                }],
            },
            "allowed_roles": ["director", "cfo", "warehouse", "manager", "admin"],
        },
        {
            "name": "Эмуляция Telegram (/integrations/telegram/simulate)",
            "method": "POST",
            "url": "/integrations/telegram/simulate",
            "body": {"text": "/start"},
            "allowed_roles": ["director", "cfo", "manager", "admin"],
        },
        {
            "name": "Эмуляция VK (/integrations/vk/simulate)",
            "method": "POST",
            "url": "/integrations/vk/simulate",
            "body": {"text": "Канбан"},
            "allowed_roles": ["director", "cfo", "manager", "admin"],
        },
    ]

    audit_results = []
    total_checks = 0
    passed_checks = 0

    for ep in endpoints_to_test:
        for role, _ in roles_credentials:
            total_checks += 1
            token = tokens[role]
            headers = {}
            if token:
                headers["Authorization"] = f"Bearer {token}"
                headers["X-Auth-Token"] = token

            if ep["method"] == "GET":
                resp = await client.get(ep["url"], headers=headers)
            else:
                resp = await client.post(ep["url"], json=ep["body"], headers=headers)

            status = resp.status_code
            should_allow = role in ep["allowed_roles"]

            if should_allow:
                is_correct = (status == 200)
                expected_desc = "200 OK"
            else:
                is_correct = (status in (401, 403))
                expected_desc = "401/403 Denied"

            if is_correct:
                passed_checks += 1

            audit_results.append({
                "endpoint": ep["name"],
                "role": role,
                "status": status,
                "expected": expected_desc,
                "passed": is_correct,
            })

    print(f"  ✓ Audited {total_checks} RBAC permission combinations")
    print(f"  ✓ Strict enforcement score: {passed_checks}/{total_checks} ({(passed_checks/total_checks)*100:.1f}%)")

    return {
        "test_name": "RBAC Security & Penetration Audit",
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "score_percent": round((passed_checks / total_checks) * 100, 1),
        "audit_results": audit_results,
    }


def generate_markdown_report(results: List[Dict[str, Any]], report_path: str):
    md = []
    md.append("# Протокол нагрузочного и стресс-тестирования системы (Stress & RBAC Report)\n")
    md.append(f"**Дата и время тестирования:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    md.append("**Границы замера:** локальный режим offline_rules, временная SQLite, внутрипроцессный ASGITransport. Рабочий .env не загружается, реальные HTTP-вызовы запрещены, SMTP/IMAP отключены. Живая база 1С, облачная модель и сетевой сервер не проверяются. В омниканальном тесте доставка Telegram/VK/Email подменена. HTTP 200 не доказывает доставку или качество ответа. Задержка SQLite относится к цепочке из трёх API-запросов, не к одной SQL-транзакции. Сравнивать этот прогон с облачными замерами как ускорение системы нельзя.\n")
    md.append("---\n")

    md.append("## 1. Сводная таблица производительности\n")
    md.append("| Модуль / Тестовый сценарий | Запросов | Время (с) | RPS / Throughput | Latency Mean | p50 | p95 | p99 | Ошибки |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for r in results:
        if "stats" in r:
            st = r["stats"]
            reqs = r.get("requests", 0)
            t_s = r.get("total_time_s", 0)
            rps = r.get("rps", r.get("ops_per_sec", 0))
            errs = r.get("errors", 0)
            md.append(f"| **{r['test_name']}** | {reqs} | {t_s} с | **{rps}** | {st['mean']} ms | {st['p50']} ms | {st['p95']} ms | {st['p99']} ms | {errs} |")

    md.append("\n---\n")

    # Details on RAG
    rag_res = next((r for r in results if "Burst RAG" in r.get("test_name", "")), None)
    if rag_res:
        md.append("## 2. Анализ конкурентного инференса ИИ-ассистента (Burst RAG)\n")
        md.append(f"- **Параллельных сессий:** {rag_res['requests']}\n")
        md.append(f"- **Среднее время генерации ответа:** {rag_res['stats']['mean']} мс\n")
        md.append(f"- **Медиана (p50):** {rag_res['stats']['p50']} мс\n")
        md.append(f"- **Распределение распознанных действий 1С:**\n")
        for act, cnt in rag_res.get("actions_resolved", {}).items():
            md.append(f"  - `{act}`: {cnt} вызовов\n")

    # Details on Omnichannel
    omni_res = next((r for r in results if "Omnichannel" in r.get("test_name", "")), None)
    if omni_res:
        total_ev = omni_res.get('requests', 0)
        err_cnt = omni_res.get('errors', 0)
        succ_cnt = total_ev - err_cnt
        drop_rate = (err_cnt / total_ev * 100.0) if total_ev > 0 else 0.0
        md.append("## 3. Омниканальная входящая нагрузка (Telegram, VK, Email)\n")
        md.append(f"- **Всего параллельных сообщений:** {total_ev}\n")
        md.append(f"- **Успешно обработано:** {succ_cnt}\n")
        md.append(f"- **Ошибок HTTP / исключений обработчиков:** {err_cnt}\n")
        md.append(f"- **Процент сбоев / отказов:** **{drop_rate:.1f}%**\n")
        md.append(f"- **Распределение по каналам:**\n")
        for ch, cnt in omni_res.get("channel_counts", {}).items():
            md.append(f"  - Канал **{ch.upper()}**: {cnt} успешно обработанных событий\n")

    # Details on SQLite
    sql_res = next((r for r in results if "SQLite" in r.get("test_name", "")), None)
    if sql_res:
        db_locks = sql_res.get('db_lock_errors', 0)
        md.append("## 4. Стресс-тест транзакционной подсистемы SQLite (ACID Concurrency)\n")
        md.append(f"- **Всего выполненных операций:** {sql_res['requests']} (создание, перевод стадий, закрытие)\n")
        md.append(f"- **Скорость транзакций:** **{sql_res.get('ops_per_sec', 0)} операций/сек**\n")
        md.append(f"- **Обнаруженных ошибок блокировки БД (`database is locked`):** **{db_locks}**. Отсутствие ошибок само по себе не устанавливает причину производительности.\n")

    # Details on RBAC Penetration
    rbac_res = next((r for r in results if "RBAC" in r.get("test_name", "")), None)
    if rbac_res:
        md.append("## 5. Аудит безопасности и матрица разграничения доступа (RBAC Audit)\n")
        md.append(f"- **Всего контрольных точек доступа:** {rbac_res['total_checks']}\n")
        md.append(f"- **Успешно пройденных тестов:** {rbac_res['passed_checks']} (**{rbac_res['score_percent']}%**)\n\n")
        md.append("| Эндпоинт 1С / Подсистема | Роль пользователя | Фактический HTTP код | Ожидаемый статус | Результат аудита |")
        md.append("| :--- | :--- | :---: | :---: | :---: |")
        for row in rbac_res.get("audit_results", []):
            res_mark = "✓ ЗАЩИЩЕНО" if row["passed"] else "✕ УЯЗВИМОСТЬ"
            md.append(f"| {row['endpoint']} | `{row['role']}` | `{row['status']}` | `{row['expected']}` | **{res_mark}** |")

    md.append("\n---\n")
    md.append("## 6. Выводы и инженерное заключение\n")
    md.append("1. Матрица RBAC проверяет только перечисленные сочетания маршрутов и ролей. Она не доказывает отсутствие иных уязвимостей и не проверяет права в живой базе 1С.\n")
    md.append("2. Производительность характеризует конкретный локальный прогон. Здесь нет измерения сетевой задержки, облачного инференса и доставки сообщений.\n")
    md.append("3. Счётчик ошибок отражает HTTP-ответы и обнаруженные исключения. Полнота бизнес-операций, восстановление после сбоя и промышленная нагрузка требуют отдельных проверок.\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"\n[REPORT] Saved full stress-testing report to: {report_path}")


async def main():
    print("=" * 70)
    print("Starting Automated Asyncio Stress-Testing Suite & RBAC Audit")
    print("=" * 70)

    # Ensure default users exist in DB
    auth_service._seed_default_users()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await run_baseline_latency_test(client, n_requests=100)
        res2 = await run_concurrent_rag_test(client, concurrency=20)
        res3 = await run_omnichannel_burst_test(client, n_events=50)
        res4 = await run_sqlite_concurrency_test(client, n_writes=50)
        res5 = await run_rbac_penetration_test(client)

        results = [res1, res2, res3, res4, res5]
        report_file = os.path.join(os.path.dirname(__file__), "stress_test_report.md")
        generate_markdown_report(results, report_file)

        if any(result.get("errors", 0) for result in results) or res5["passed_checks"] != res5["total_checks"]:
            raise SystemExit("Stress benchmark failed; inspect the generated report")

    print("\n" + "=" * 70)
    print("Stress-Testing Suite Successfully Finished!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        from app.services.auth_service import engine as auth_engine
        from app.services.kanban_service import engine as kanban_engine
        auth_engine.dispose()
        kanban_engine.dispose()
        _isolation.close()
