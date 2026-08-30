# Оптимизированные диаграммы Mermaid.js для диплома

В данном документе собраны доработанные и оптимизированные версии Mermaid.js для всех 6 диаграмм категории 1. В этих версиях устранены проблемы с читаемостью текста:
- Использована иерархия шрифтов (жирный заголовок `<b>` + обычный текст).
- Текст внутри блоков аккуратно разбит на строки с помощью `<br/>`.
- Подписи на стрелках сокращены и структурированы, чтобы избежать наложения.
- Для каждого элемента задан правильный цвет обводки и заливки согласно правилам оформления диплома (`00_common_rules.txt`).

---

### Рисунок 1.1 — Место интеллектуального ассистента в контуре работы пользователей 1С:УНФ

```mermaid
flowchart LR
    %%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#ffffff', 'edgeLabelBackground': '#ffffff', 'fontSize': '14px', 'fontFamily': 'Arial' }}}%%
    
    User(["Пользователь"])
    
    subgraph Client ["Клиентская часть (1С:УНФ)"]
        ChatForm["<b>Форма чата</b><br/>HTML/JS чат-интерфейс"]
        CmdDispatcher["<b>Диспетчер команд</b><br/>Безопасный whitelist"]
    end
    
    subgraph Middleware ["Серверная часть (Python)"]
        FastAPI["<b>FastAPI Сервер</b><br/>Обработка HTTP запросов"]
        VectorDB[("<b>Векторный индекс</b><br/>База метаданных (.npy)")]
    end
    
    LLMAPI["<b>LLM-провайдер</b><br/>GLM-5.1 / Fireworks API"]
    
    %% Связи
    User -->|"1. Запрос"| ChatForm
    ChatForm -->|"2. POST /chat"| FastAPI
    FastAPI <-->|"3. RAG поиск"| VectorDB
    FastAPI -->|"4. Промпт + Контекст"| LLMAPI
    LLMAPI -->|"5. JSON ответ"| FastAPI
    FastAPI -->|"6. Ответ 200 OK"| ChatForm
    ChatForm -->|"7. Вызов действия"| CmdDispatcher
    CmdDispatcher -->|"8. Результат"| User

    %% Стилизация
    classDef client fill:#FFF3E0,stroke:#E67E22,stroke-width:2px,color:#1A1A2E;
    classDef middleware fill:#E3F2FD,stroke:#2980B9,stroke-width:2px,color:#1A1A2E;
    classDef llm fill:#E8F5E9,stroke:#27AE60,stroke-width:2px,color:#1A1A2E;
    classDef storage fill:#ECEFF1,stroke:#7F8C8D,stroke-width:2px,color:#1A1A2E;
    classDef user fill:#E0F7FA,stroke:#00ACC1,stroke-width:2px,color:#1A1A2E;
    
    class User user;
    class ChatForm,CmdDispatcher client;
    class FastAPI middleware;
    class VectorDB storage;
    class LLMAPI llm;
```

---

### Рисунок 2.1 — Архитектура решения: компоненты и взаимосвязи

```mermaid
flowchart TD
    %%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#ffffff', 'edgeLabelBackground': '#ffffff', 'fontSize': '13px', 'fontFamily': 'Arial' }}}%%
    
    subgraph Client ["КЛИЕНТСКАЯ ЧАСТЬ (Расширение 1С:УНФ)"]
        direction LR
        UI["<b>Интерфейс чата</b><br/>(HTML + быстрые кнопки)"]
        Dispatcher["<b>Диспетчер команд</b><br/>(Выполнение whitelist)"]
        MetaCollector["<b>Сбор метаданных</b><br/>(Анализ конфигурации)"]
    end
    
    subgraph Middleware ["СЕРВЕРНАЯ ЧАСТЬ (FastAPI Middleware)"]
        direction TB
        API["<b>API Контроллер</b><br/>(/chat, /auth, /kanban, /update_metadata)"]
        
        subgraph Services ["Модули сервисов"]
            direction LR
            AuthServ["<b>auth_service</b><br/>JWT / bcrypt"]
            KanbanServ["<b>kanban_service</b><br/>CRUD задач"]
            LLMServ["<b>llm_service</b><br/>Промпты и парсинг"]
            MetaServ["<b>metadata_service</b><br/>Эмбеддинги и RAG"]
        end
        API <--> AuthServ
        API <--> KanbanServ
        API <--> LLMServ
        API <--> MetaServ
    end

    subgraph LLM ["ВНЕШНИЙ LLM-ПРОВАЙДЕР"]
        LLMAPI["<b> fireworks.ai / glm-5.1</b><br/>OpenAI-совместимый API"]
    end

    subgraph Storage ["БАЗЫ ДАННЫХ И ХРАНИЛИЩА"]
        SQLite[("<b>SQLite БД</b><br/>Таблицы пользователей и задач")]
        NpyFile[("<b>Индекс метаданных</b><br/>Файлы .npy / .json")]
    end

    %% Взаимодействия
    UI -->|"HTTP POST /chat"| API
    API -.->|"JSON-ответ"| UI
    Dispatcher -->|"Выгрузка"| MetaCollector
    MetaCollector -->|"HTTP POST /update_metadata"| API
    
    LLMServ <-->|"API-запрос"| LLMAPI
    AuthServ <-->|"SQL запросы"| SQLite
    KanbanServ <-->|"SQL запросы"| SQLite
    MetaServ <-->|"Загрузка индексов"| NpyFile

    %% Стилизация
    classDef client fill:#FFF3E0,stroke:#E67E22,stroke-width:2px,color:#1A1A2E;
    classDef middleware fill:#E3F2FD,stroke:#2980B9,stroke-width:2px,color:#1A1A2E;
    classDef services fill:#F3E5F5,stroke:#9B59B6,stroke-width:2px,color:#1A1A2E;
    classDef llm fill:#E8F5E9,stroke:#27AE60,stroke-width:2px,color:#1A1A2E;
    classDef storage fill:#ECEFF1,stroke:#7F8C8D,stroke-width:2px,color:#1A1A2E;

    class UI,Dispatcher,MetaCollector,Client client;
    class API,Middleware middleware;
    class AuthServ,KanbanServ,LLMServ,MetaServ services;
    class LLMAPI,LLM llm;
    class SQLite,NpyFile,Storage storage;
```

---

### Рисунок 2.2 — Диаграмма последовательностей «Отправка сообщения»

```mermaid
sequenceDiagram
    autonumber
    actor User as Пользователь
    participant Client as 1С:УНФ (Клиент)
    participant Server as Middleware (FastAPI)
    participant RAG as RAG-сервис
    participant LLM as LLM-модель

    User->>Client: Ввод текстового сообщения
    Client->>Server: HTTP POST /chat (сообщение, контекст)
    Server->>RAG: Поиск объектов (косинусное сходство)
    RAG-->>Server: Top-7 релевантных объектов
    Server->>LLM: Запрос (системный промпт + RAG-контекст)
    LLM-->>Server: Структурированный JSON (text, action, data)
    Server-->>Client: HTTP 200 OK (JSON)
    Client-->>User: Отображение ответа в форме чата
    
    rect rgb(255, 243, 224)
        note over Client: Выполнение безопасной команды
        Client->>Client: ВыполнитьКомандуАссистента(action)
    end
```

---

### Рисунок 2.3 — Структура элемента метаданных и место в процессе RAG

```mermaid
flowchart TD
    %%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#ffffff', 'edgeLabelBackground': '#ffffff', 'fontSize': '14px', 'fontFamily': 'Arial' }}}%%

    subgraph MetadataBlock ["ЭЛЕМЕНТ МЕТАДАННЫХ (1С)"]
        MetaObj["<b>Объект:</b> Документ.ЗаказПокупателя<br/><b>Синоним:</b> Заказ покупателя<br/>-----------------------------------<br/><b>Поля:</b><br/>• Контрагент (СправочникСсылка.Контрагенты)<br/>• СуммаДокумента (Число 15, 2)"]
    end

    subgraph Pipeline ["Поиск и RAG-пайплайн"]
        Encoder["<b>Энкодер</b><br/>SentenceTransformers<br/>(paraphrase-multilingual)"]
        VectorDB[("<b>Векторный индекс</b><br/>384-мерные эмбеддинги<br/>(Cosine Similarity)")]
        TopK["<b>Top-7 Кандидатов</b><br/>Выборка наиболее релевантных<br/>объектов для контекста"]
    end

    subgraph GenBlock ["Генерация и валидация"]
        LLM["<b>LLM (GLM-5.1)</b><br/>Формирование ответа<br/>на основе контекста"]
        Parser["<b>Разбор JSON</b><br/>Валидация по whitelist<br/>и проверка прав доступа"]
    end

    %% Связи
    MetadataBlock -->|"1. Экспорт и векторизация"| Encoder
    Encoder -->|"384-мерный вектор"| VectorDB
    VectorDB -->|"2. Поиск похожих"| TopK
    TopK -->|"3. Контекст в промпт"| LLM
    LLM -->|"4. JSON: text, action, data"| Parser

    %% Стилизация
    classDef client fill:#FFF3E0,stroke:#E67E22,stroke-width:2px,color:#1A1A2E;
    classDef middleware fill:#E3F2FD,stroke:#2980B9,stroke-width:2px,color:#1A1A2E;
    classDef llm fill:#E8F5E9,stroke:#27AE60,stroke-width:2px,color:#1A1A2E;
    classDef parser fill:#F3E5F5,stroke:#9B59B6,stroke-width:2px,color:#1A1A2E;

    class MetadataBlock,MetaObj client;
    class Encoder,VectorDB,TopK,Pipeline middleware;
    class GenBlock,LLM llm;
    class Parser parser;
```

---

### Рисунок 2.4 — ER-диаграмма базы данных SQLite

```mermaid
erDiagram
    %%{init: {'theme': 'base', 'themeVariables': { 'fontSize': '14px', 'fontFamily': 'Arial' }}}%%
    
    DEPARTMENTS {
        int id PK
        varchar name UK
        int head_user_id FK
        int parent_id FK
    }

    USERS {
        int id PK
        varchar username UK
        varchar password_hash
        varchar role
        int department_id FK
        datetime created_at
    }

    KANBAN_TASKS {
        int id PK
        varchar title
        varchar column
        varchar priority
        varchar assignee FK
        varchar due_date
        int department_id FK
        int position
    }

    DEPARTMENTS ||--o{ USERS : "содержит"
    DEPARTMENTS ||--o{ KANBAN_TASKS : "содержит_задачи"
    USERS ||--o{ KANBAN_TASKS : "исполняет"
```

---

### Рисунок 2.6 — Схема JWT-авторизации между 1С и middleware

```mermaid
sequenceDiagram
    autonumber
    actor User as Пользователь 1С
    participant Client as 1С:УНФ (Клиент)
    participant Server as Middleware (FastAPI)
    participant DB as SQLite БД

    User->>Client: Открытие формы чата
    Client->>Server: HTTP POST /auth/login (логин, пароль)
    Server->>DB: Проверка пароля (bcrypt) и получение роли
    DB-->>Server: Данные о пользователе (role, dept_id)
    Server-->>Client: HTTP 200 OK (access_token: JWT)
    
    note over Client, Server: JWT Payload содержит: sub, user_id, role, department_id, exp

    rect rgb(235, 240, 245)
        note over Client: Сохранение токена во внутренний реквизит
        Client->>Client: Сохранить в MiddlewareТокен
    end

    Client->>Server: HTTP GET /kanban/tasks (X-Auth-Token: JWT)
    Server-->>Client: HTTP 200 OK (Задачи, отфильтрованные по роли)
    Client-->>User: Отображение задач на канбан-доске

    note over Client: При получении 401 Unauthorized:<br/>1. Сбросить MiddlewareТокен<br/>2. Повторить POST /auth/login<br/>3. Повторить исходный HTTP-запрос
```

---

### Рисунок 3.2 — Схема RAG: от запроса пользователя к структурированному ответу

```mermaid
flowchart TD
    %%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#ffffff', 'edgeLabelBackground': '#ffffff', 'fontSize': '14px', 'fontFamily': 'Arial' }}}%%

    Query["<b>1. Запрос пользователя</b><br/>Естественный язык пользователя"]
    
    subgraph VectorSearch ["Векторный поиск (Основной путь)"]
        Vectorization["<b>2. Векторизация</b><br/>SentenceTransformer<br/>(384-мерный вектор)"]
        Cosine["<b>3. Косинусное сходство</b><br/>Сравнение с 1423 объектами<br/>(выборка .klargest(7))"]
    end
    
    subgraph FallbackSearch ["Лексический поиск (Резервный путь)"]
        WordOverlap["<b>Word Overlap (Fallback)</b><br/>Поиск по пересечению слов<br/>(synonym + name)"]
    end

    TopK["<b>4. Top-7 объектов</b><br/>Формирование RAG-контекста<br/>(имена + типы полей)"]
    
    subgraph Generation ["Генерация ответа"]
        Prompt["<b>5. Системный промпт</b><br/>Шаблон + RAG-контекст<br/>+ Few-shot примеры"]
        LLM["<b>6. LLM (GLM-5.1)</b><br/>Fireworks API"]
    end

    Response["<b>7. JSON ответ</b><br/>{text, action, data}"]

    %% Связи
    Query --> Vectorization
    Vectorization --> Cosine
    Cosine --> TopK
    
    Query -.->|"В случае ошибки сети/векторизатора"| WordOverlap
    WordOverlap -.-> TopK
    
    TopK --> Prompt
    Prompt --> LLM
    LLM --> Response

    %% Стилизация
    classDef client fill:#FFF3E0,stroke:#E67E22,stroke-width:2px,color:#1A1A2E;
    classDef middleware fill:#E3F2FD,stroke:#2980B9,stroke-width:2px,color:#1A1A2E;
    classDef fallback fill:#FFFDE7,stroke:#FBC02D,stroke-width:2px,color:#1A1A2E;
    classDef llm fill:#E8F5E9,stroke:#27AE60,stroke-width:2px,color:#1A1A2E;
    classDef metadata fill:#F3E5F5,stroke:#9B59B6,stroke-width:2px,color:#1A1A2E;

    class Query,Response client;
    class Vectorization,Cosine,Prompt middleware;
    class WordOverlap fallback;
    class TopK metadata;
    class LLM llm;
```
