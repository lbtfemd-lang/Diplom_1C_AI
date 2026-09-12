# Протокол нагрузочного и стресс-тестирования системы (Stress & RBAC Report)

**Дата и время тестирования:** 2026-09-10 11:27:56

**Границы замера:** локальный режим offline_rules, временная SQLite, внутрипроцессный ASGITransport. Рабочий .env не загружается, реальные HTTP-вызовы запрещены, SMTP/IMAP отключены. Живая база 1С, облачная модель и сетевой сервер не проверяются. В омниканальном тесте доставка Telegram/VK/Email подменена. HTTP 200 не доказывает доставку или качество ответа. Задержка SQLite относится к цепочке из трёх API-запросов, не к одной SQL-транзакции. Сравнивать этот прогон с облачными замерами как ускорение системы нельзя.

---

## 1. Сводная таблица производительности

| Модуль / Тестовый сценарий | Запросов | Время (с) | RPS / Throughput | Latency Mean | p50 | p95 | p99 | Ошибки |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline HTTP Latency (/health)** | 100 | 0.06 с | **1591.1** | 0.63 ms | 0.56 ms | 0.68 ms | 0.92 ms | 0 |
| **Concurrent Burst RAG (20 parallel requests)** | 20 | 0.19 с | **103.0** | 191.55 ms | 191.54 ms | 192.15 ms | 192.15 ms | 0 |
| **Omnichannel Ingestion Burst (50 concurrent events)** | 50 | 0.14 с | **365.0** | 130.06 ms | 129.59 ms | 133.87 ms | 134.63 ms | 0 |
| **SQLite Concurrency (50 tasks created & moved = 150 ACID operations)** | 150 | 0.72 с | **208.6** | 712.67 ms | 712.69 ms | 714.69 ms | 714.85 ms | 0 |

---

## 2. Анализ конкурентного инференса ИИ-ассистента (Burst RAG)

- **Параллельных сессий:** 20

- **Среднее время генерации ответа:** 191.55 мс

- **Медиана (p50):** 191.54 мс

- **Распределение распознанных действий 1С:**

  - `cash_gap_forecast`: 3 вызовов

  - `get_cash_balance`: 3 вызовов

  - `get_debtors`: 3 вызовов

  - `get_dead_stock`: 3 вызовов

  - `expert_answer`: 2 вызовов

  - `get_creditors`: 2 вызовов

  - `show_kanban`: 2 вызовов

  - `audit_stalled_orders`: 2 вызовов

## 3. Омниканальная входящая нагрузка (Telegram, VK, Email)

- **Всего параллельных сообщений:** 50

- **Успешно обработано:** 50

- **Ошибок HTTP / исключений обработчиков:** 0

- **Процент сбоев / отказов:** **0.0%**

- **Распределение по каналам:**

  - Канал **TELEGRAM**: 17 успешно обработанных событий

  - Канал **VK**: 17 успешно обработанных событий

  - Канал **EMAIL**: 16 успешно обработанных событий

## 4. Стресс-тест транзакционной подсистемы SQLite (ACID Concurrency)

- **Всего выполненных операций:** 150 (создание, перевод стадий, закрытие)

- **Скорость транзакций:** **208.6 операций/сек**

- **Обнаруженных ошибок блокировки БД (`database is locked`):** **0**. Отсутствие ошибок само по себе не устанавливает причину производительности.

## 5. Аудит безопасности и матрица разграничения доступа (RBAC Audit)

- **Всего контрольных точек доступа:** 60

- **Успешно пройденных тестов:** 60 (**100.0%**)


| Эндпоинт 1С / Подсистема | Роль пользователя | Фактический HTTP код | Ожидаемый статус | Результат аудита |
| :--- | :--- | :---: | :---: | :---: |
| Финансовый монитор (/analytics/monitor) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Финансовый монитор (/analytics/monitor) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Финансовый монитор (/analytics/monitor) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Финансовый монитор (/analytics/monitor) | `manager` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Финансовый монитор (/analytics/monitor) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Финансовый монитор (/analytics/monitor) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `manager` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Исходящие email (/integrations/email/outbox) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `manager` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Утренний дайджест руководителя (/integrations/email/digest) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `manager` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Аудит платежа (/business/compliance/audit-payment) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `manager` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| 115-ФЗ: Проверка контрагента (/business/compliance/check-counterparty) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `manager` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Юнит-экономика и маржа (/business/margin/calculate-deal) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `manager` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Досудебная претензия ст. 395 (/business/debt/generate-claim) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `warehouse` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `manager` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Автозаказ ROP/EOQ (/business/stock/analyze-inventory) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `manager` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция Telegram (/integrations/telegram/simulate) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `anonymous` | `401` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `employee` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `warehouse` | `403` | `401/403 Denied` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `manager` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `cfo` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |
| Эмуляция VK (/integrations/vk/simulate) | `director` | `200` | `200 OK` | **✓ ЗАЩИЩЕНО** |

---

## 6. Выводы и инженерное заключение

1. Матрица RBAC проверяет только перечисленные сочетания маршрутов и ролей. Она не доказывает отсутствие иных уязвимостей и не проверяет права в живой базе 1С.

2. Производительность характеризует конкретный локальный прогон. Здесь нет измерения сетевой задержки, облачного инференса и доставки сообщений.

3. Счётчик ошибок отражает HTTP-ответы и обнаруженные исключения. Полнота бизнес-операций, восстановление после сбоя и промышленная нагрузка требуют отдельных проверок.
