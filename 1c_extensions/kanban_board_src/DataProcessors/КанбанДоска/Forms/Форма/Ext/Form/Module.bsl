// =============================================================================
// Канбан-доска — Премиальное интерактивное решение 1С:Предприятие
// =============================================================================

&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
    АвтоЗаголовок = Ложь;
    Заголовок = "Канбан-доска";
    КанбанHTML = ПолучитьДоску1СНаСервере();
КонецПроцедуры

&НаКлиенте
Процедура ПриОткрытии(Отказ)
    АвтоЗаголовок = Ложь;
    Заголовок = "Канбан-доска";
    Если ПустаяСтрока(КанбанHTML) Тогда
        ОбновитьДоску();
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура ОбработкаОповещения(ИмяСобытия, Параметр, Источник)
    ОбновитьДоску();
КонецПроцедуры

&НаКлиенте
Процедура ОбновитьДоску()
    КанбанHTML = ПолучитьДоску1СНаСервере();
КонецПроцедуры

// =============================================================================
// ГЕНЕРАЦИЯ HTML КАНБАН-ДОСКИ
// =============================================================================

&НаСервере
Функция ПолучитьДоску1СНаСервере()
    Попытка
        Запрос = Новый Запрос;
        Запрос.Текст = 
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ
            |   Задача.Ссылка КАК Ссылка,
            |   Задача.Номер КАК Номер,
            |   Задача.Наименование КАК Заголовок,
            |   Задача.Описание КАК Описание,
            |   ПРЕДСТАВЛЕНИЕ(Задача.Исполнитель) КАК Исполнитель,
            |   Задача.Предмет КАК Предмет,
            |   ПРЕДСТАВЛЕНИЕ(Задача.Предмет) КАК ПредметПредставление,
            |   Задача.Важность КАК Важность,
            |   Задача.СрокИсполнения КАК КрайнийСрок,
            |   Задача.Выполнена КАК Выполнена,
            |   Задача.ПринятаКИсполнению КАК ПринятаКИсполнению,
            |   Задача.Дата КАК ДатаСоздания
            |ИЗ
            |   Задача.ЗадачаИсполнителя КАК Задача
            |ГДЕ
            |   НЕ Задача.ПометкаУдаления
            |УПОРЯДОЧИТЬ ПО
            |   Задача.Дата УБЫВ";
        
        Результат = Запрос.Выполнить();
        Выборка = Результат.Выбрать();
        
        МассивЗадач = Новый Массив;
        
        Пока Выборка.Следующий() Цикл
            СтруктураЗ = Новый Структура;
            СтруктураЗ.Вставить("ref", Строка(Выборка.Ссылка.УникальныйИдентификатор()));
            СтруктураЗ.Вставить("id", СокрЛП(Выборка.Номер));
            СтруктураЗ.Вставить("title", СокрЛП(Выборка.Заголовок));
            СтруктураЗ.Вставить("description", СокрЛП(Выборка.Описание));
            
            ТекстОписания = СокрЛП(Выборка.Описание);
            Если Выборка.Выполнена Тогда
                Колонка = "done";
            ИначеЕсли СтрНайти(ТекстОписания, "[Статус: На проверке]") > 0 И Выборка.ПринятаКИсполнению Тогда
                Колонка = "review";
            ИначеЕсли Выборка.ПринятаКИсполнению Тогда
                Колонка = "in_progress";
            Иначе
                Колонка = "todo";
            КонецЕсли;
            СтруктураЗ.Вставить("column", Колонка);
            
            Если Выборка.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая Тогда
                Приор = "high";
            ИначеЕсли Выборка.Важность = Перечисления.ВариантыВажностиЗадачи.Низкая Тогда
                Приор = "low";
            Иначе
                Приор = "medium";
            КонецЕсли;
            СтруктураЗ.Вставить("priority", Приор);
            
            ИсполнительТекст = СокрЛП(Выборка.Исполнитель);
            СтруктураЗ.Вставить("assignee", ?(ЗначениеЗаполнено(ИсполнительТекст), ИсполнительТекст, "Администратор"));
            
            ПредметТекст = СокрЛП(Выборка.ПредметПредставление);
            СтруктураЗ.Вставить("subject", ПредметТекст);
            
            Если ЗначениеЗаполнено(Выборка.КрайнийСрок) Тогда
                СтруктураЗ.Вставить("due_date", Формат(Выборка.КрайнийСрок, "ДФ=dd.MM.yyyy"));
                СтруктураЗ.Вставить("overdue", Выборка.КрайнийСрок < ТекущаяДатаСеанса() И НЕ Выборка.Выполнена);
            Иначе
                СтруктураЗ.Вставить("due_date", "");
                СтруктураЗ.Вставить("overdue", Ложь);
            КонецЕсли;
            
            МассивЗадач.Добавить(СтруктураЗ);
        КонецЦикла;
        
    Исключение
        МассивЗадач = Новый Массив;
    КонецПопытки;
    
    // Справочники для создания задач
    СписокКонтрагентов = Новый Массив;
    Попытка
        ЗапросК = Новый Запрос("ВЫБРАТЬ ПЕРВЫЕ 20 К.Ссылка, К.Наименование, К.ИНН ИЗ Справочник.Контрагенты КАК К ГДЕ НЕ К.ЭтоГруппа И НЕ К.ПометкаУдаления УПОРЯДОЧИТЬ ПО К.Наименование");
        ВыбК = ЗапросК.Выполнить().Выбрать();
        Пока ВыбК.Следующий() Цикл
            СписокКонтрагентов.Добавить(Новый Структура("Ref, Name, INN", Строка(ВыбК.Ссылка.УникальныйИдентификатор()), ВыбК.Наименование, ВыбК.ИНН));
        КонецЦикла;
    Исключение
    КонецПопытки;
    
    ОпцииКонтрагентов = "<option value=''>-- Без контрагента --</option>";
    Для Каждого К Из СписокКонтрагентов Цикл
        ОпцииКонтрагентов = ОпцииКонтрагентов + "<option value='" + К.Ref + "'>" + ЭкранироватьHTML(К.Name) + "</option>";
    КонецЦикла;
    
    // Определение колонок
    Колонки = Новый Массив;
    Колонки.Добавить(Новый Структура("id, name, color, badge", "todo", "К выполнению", "#3b82f6", "bg-blue"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "in_progress", "В работе", "#f59e0b", "bg-amber"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "review", "На проверке", "#a855f7", "bg-purple"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "done", "Готово", "#10b981", "bg-emerald"));
    
    IconPlus = "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5' style='vertical-align:middle;margin-right:4px;'><line x1='12' y1='5' x2='12' y2='19'></line><line x1='5' y1='12' x2='19' y2='12'></line></svg>";
    IconRefresh = "<svg width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' style='vertical-align:middle;margin-right:4px;'><polyline points='23 4 23 10 17 10'></polyline><polyline points='1 20 1 14 7 14'></polyline><path d='M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15'></path></svg>";
    IconTheme = "<svg width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' style='vertical-align:middle;margin-right:4px;'><circle cx='12' cy='12' r='5'></circle><line x1='12' y1='1' x2='12' y2='3'></line><line x1='12' y1='21' x2='12' y2='23'></line><line x1='4.22' y1='4.22' x2='5.64' y2='5.64'></line><line x1='18.36' y1='18.36' x2='19.78' y2='19.78'></line><line x1='1' y1='12' x2='3' y2='12'></line><line x1='21' y1='12' x2='23' y2='12'></line><line x1='4.22' y1='19.78' x2='5.64' y2='18.36'></line><line x1='18.36' y1='5.64' x2='19.78' y2='4.22'></line></svg>";
    IconUser = "<svg width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' style='vertical-align:middle;margin-right:4px;'><path d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'></path><circle cx='12' cy='7' r='4'></circle></svg>";
    IconCalendar = "<svg width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' style='vertical-align:middle;margin-right:4px;'><rect x='3' y='4' width='18' height='18' rx='2' ry='2'></rect><line x1='16' y1='2' x2='16' y2='6'></line><line x1='8' y1='2' x2='8' y2='6'></line><line x1='3' y1='10' x2='21' y2='10'></line></svg>";
    IconBoard = "<svg width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='#f59e0b' stroke-width='2' style='vertical-align:middle;margin-right:6px;'><rect x='3' y='3' width='18' height='18' rx='2' ry='2'></rect><line x1='9' y1='3' x2='9' y2='21'></line><line x1='15' y1='3' x2='15' y2='21'></line></svg>";

    ВсегоЗадач = МассивЗадач.Количество();
    
    СтолбцыHTML = "";
    Для Каждого Колонка Из Колонки Цикл
        ЗадачиКолонки = "";
        Счётчик = 0;
        
        Для Каждого З Из МассивЗадач Цикл
            Если З.column <> Колонка.id Тогда Продолжить; КонецЕсли;
            
            Счётчик = Счётчик + 1;
            Ref = З.ref;
            Id = З.id;
            Title = ЭкранироватьHTML(З.title);
            Description = ЭкранироватьHTML(З.description);
            Assignee = ЭкранироватьHTML(З.assignee);
            Subject = ЭкранироватьHTML(З.subject);
            DueDate = З.due_date;
            
            ПриорHTML = "";
            Если З.priority = "high" Тогда
                ПриорHTML = "<span class='priority-badge priority-high'>Высокий</span>";
            ИначеЕсли З.priority = "medium" Тогда
                ПриорHTML = "<span class='priority-badge priority-med'>Средний</span>";
            Иначе
                ПриорHTML = "<span class='priority-badge priority-low'>Низкий</span>";
            КонецЕсли;
            
            ПредметHTML = ?(ПустаяСтрока(Subject), "", "<div class='task-subject' title='Предмет задачи'>" + Subject + "</div>");
            ДедлайнHTML = ?(ПустаяСтрока(DueDate), "", "<div class='task-date" + ?(З.overdue, " overdue", "") + "' title='Срок исполнения'>" + IconCalendar + DueDate + "</div>");
            
            КнопкиДействий = "<div class='card-actions'>";
            Если Колонка.id = "todo" Тогда
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=in_progress' class='act-btn act-primary' title='Взять в работу'>▶ В работу</a>";
            ИначеЕсли Колонка.id = "in_progress" Тогда
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=review' class='act-btn act-purple' title='Передать на проверку'>⏳ Проверить</a>";
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=done' class='act-btn act-success' title='Завершить'>✓ Готово</a>";
            ИначеЕсли Колонка.id = "review" Тогда
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=done' class='act-btn act-success' title='Утвердить'>✓ Готово</a>";
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=in_progress' class='act-btn' title='Вернуть'>↺ В работу</a>";
            ИначеЕсли Колонка.id = "done" Тогда
                КнопкиДействий = КнопкиДействий + "<a href='#moveTask?ref=" + Ref + "&to=todo' class='act-btn' title='Вернуть'>↺ Вернуть</a>";
            КонецЕсли;
            
            КнопкиДействий = КнопкиДействий + "<button type='button' class='act-btn btn-open-edit' data-ref='" + Ref + "' data-title='" + Title + "' data-desc='" + Description + "' data-prio='" + З.priority + "' data-subject='" + Subject + "' data-assignee='" + Assignee + "' title='Редактировать'>✏️ Инфо</button>";
            КнопкиДействий = КнопкиДействий + "<a href='#deleteTask?ref=" + Ref + "' class='act-btn act-danger' title='Удалить'>🗑</a></div>";
            
            ЗадачиКолонки = ЗадачиКолонки
                + "<div class='task-card'>"
                + "  <div class='card-top'>"
                + "    <span class='task-id'>#" + Id + "</span>"
                + "    " + ПриорHTML
                + "  </div>"
                + "  <div class='task-title btn-open-edit' data-ref='" + Ref + "' data-title='" + Title + "' data-desc='" + Description + "' data-prio='" + З.priority + "' data-subject='" + Subject + "' data-assignee='" + Assignee + "'>" + Title + "</div>"
                +    ПредметHTML
                + "  <div class='card-footer'>"
                + "    <div class='task-assignee' title='Исполнитель'>" + IconUser + Assignee + "</div>"
                +      ДедлайнHTML
                + "  </div>"
                +    КнопкиДействий
                + "</div>";
        КонецЦикла;
        
        СтолбцыHTML = СтолбцыHTML
            + "<div class='column'>"
            + "  <div class='column-header' style='border-top: 3px solid " + Колонка.color + "'>"
            + "    <span class='column-title'>" + Колонка.name + "</span>"
            + "    <span class='column-badge " + Колонка.badge + "'>" + Счётчик + "</span>"
            + "  </div>"
            + "  <div class='column-body'>"
            +      ЗадачиКолонки
            + "  </div>"
            + "</div>";
    КонецЦикла;
    
    HTML = "<!DOCTYPE html>"
        + "<html><head><meta charset='utf-8'>"
        + "<style>"
        + "  :root {"
        + "    --bg-main: #18181b;"
        + "    --bg-header: #27272a;"
        + "    --bg-col: #202024;"
        + "    --bg-col-header: #27272a;"
        + "    --bg-card: #27272a;"
        + "    --bg-card-hover: #303036;"
        + "    --border-main: #3f3f46;"
        + "    --border-subtle: #2d2d33;"
        + "    --text-main: #f4f4f5;"
        + "    --text-muted: #a1a1aa;"
        + "    --text-id: #71717a;"
        + "    --input-bg: #18181b;"
        + "    --input-border: #3f3f46;"
        + "    --input-text: #f4f4f5;"
        + "    --modal-bg: #27272a;"
        + "    --modal-header: #202024;"
        + "    --modal-border: #3f3f46;"
        + "    --subject-bg: #1e293b;"
        + "    --subject-border: #3b82f6;"
        + "    --subject-text: #93c5fd;"
        + "    --act-btn-bg: #1f1f23;"
        + "    --act-btn-border: #3f3f46;"
        + "    --act-btn-text: #d4d4d8;"
        + "    --act-btn-hover: #3f3f46;"
        + "    --sec-btn-bg: #27272a;"
        + "    --sec-btn-border: #3f3f46;"
        + "    --sec-btn-text: #e4e4e7;"
        + "    --sec-btn-hover: #3f3f46;"
        + "  }"
        + "  body.theme-light {"
        + "    --bg-main: #f8fafc;"
        + "    --bg-header: #ffffff;"
        + "    --bg-col: #ffffff;"
        + "    --bg-col-header: #fafafa;"
        + "    --bg-card: #ffffff;"
        + "    --bg-card-hover: #ffffff;"
        + "    --border-main: #e2e8f0;"
        + "    --border-subtle: #f1f5f9;"
        + "    --text-main: #1e293b;"
        + "    --text-muted: #64748b;"
        + "    --text-id: #64748b;"
        + "    --input-bg: #ffffff;"
        + "    --input-border: #cbd5e1;"
        + "    --input-text: #1e293b;"
        + "    --modal-bg: #ffffff;"
        + "    --modal-header: #f8fafc;"
        + "    --modal-border: #e2e8f0;"
        + "    --subject-bg: #eff6ff;"
        + "    --subject-border: #bfdbfe;"
        + "    --subject-text: #2563eb;"
        + "    --act-btn-bg: #f1f5f9;"
        + "    --act-btn-border: #e2e8f0;"
        + "    --act-btn-text: #475569;"
        + "    --act-btn-hover: #e2e8f0;"
        + "    --sec-btn-bg: #f1f5f9;"
        + "    --sec-btn-border: #cbd5e1;"
        + "    --sec-btn-text: #475569;"
        + "    --sec-btn-hover: #e2e8f0;"
        + "  }"
        + "  * { box-sizing: border-box; margin: 0; padding: 0; }"
        + "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: var(--bg-main); color: var(--text-main); padding: 12px; user-select: none; transition: background 0.2s, color 0.2s; }"
        + "  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; background: var(--bg-header); padding: 10px 16px; border-radius: 8px; border: 1px solid var(--border-main); box-shadow: 0 1px 3px rgba(0,0,0,0.15); }"
        + "  .header-title { font-size: 15px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; }"
        + "  .controls { display: flex; gap: 8px; align-items: center; }"
        + "  .search-input { padding: 6px 12px; background: var(--input-bg); border: 1px solid var(--input-border); color: var(--input-text); border-radius: 6px; font-size: 13px; width: 200px; outline: none; transition: border 0.2s; }"
        + "  .search-input:focus { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.2); }"
        + "  .btn { padding: 6px 12px; font-size: 13px; font-weight: 600; border-radius: 6px; cursor: pointer; border: none; transition: all 0.2s; display: inline-flex; align-items: center; text-decoration: none; }"
        + "  .btn-primary { background: #f59e0b; color: #ffffff; }"
        + "  .btn-primary:hover { background: #d97706; }"
        + "  .btn-secondary { background: var(--sec-btn-bg); color: var(--sec-btn-text); border: 1px solid var(--sec-btn-border); }"
        + "  .btn-secondary:hover { background: var(--sec-btn-hover); color: var(--text-main); }"
        + "  .btn-danger { background: #ef4444; color: #ffffff; }"
        + "  .btn-danger:hover { background: #dc2626; }"
        + "  .board { display: flex; gap: 12px; align-items: flex-start; overflow-x: auto; min-height: 84vh; }"
        + "  .column { flex: 1; min-width: 240px; background: var(--bg-col); border: 1px solid var(--border-main); border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }"
        + "  .column-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: var(--bg-col-header); border-bottom: 1px solid var(--border-subtle); border-radius: 8px 8px 0 0; }"
        + "  .column-title { font-size: 13px; font-weight: 700; color: var(--text-main); }"
        + "  .column-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px; }"
        + "  .bg-blue { background: rgba(59,130,246,0.2); color: #60a5fa; }"
        + "  .bg-amber { background: rgba(245,158,11,0.2); color: #fbbf24; }"
        + "  .bg-purple { background: rgba(168,85,247,0.2); color: #c084fc; }"
        + "  .bg-emerald { background: rgba(16,185,129,0.2); color: #34d399; }"
        + "  .column-body { padding: 10px; min-height: 350px; display: flex; flex-direction: column; gap: 8px; }"
        + "  .task-card { background: var(--bg-card); border: 1px solid var(--border-main); border-radius: 6px; padding: 10px 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s; }"
        + "  .task-card:hover { transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); border-color: #52525b; background: var(--bg-card-hover); }"
        + "  .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }"
        + "  .task-id { font-size: 11px; font-weight: 700; color: var(--text-id); font-family: monospace; }"
        + "  .priority-badge { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }"
        + "  .priority-high { background: rgba(239,68,68,0.2); color: #f87171; }"
        + "  .priority-med { background: rgba(245,158,11,0.2); color: #fbbf24; }"
        + "  .priority-low { background: rgba(100,116,139,0.2); color: #94a3b8; }"
        + "  .task-title { font-size: 13px; font-weight: 600; color: var(--text-main); line-height: 1.35; margin-bottom: 6px; cursor: pointer; }"
        + "  .task-title:hover { color: #60a5fa; text-decoration: underline; }"
        + "  .task-subject { font-size: 11px; font-weight: 600; color: var(--subject-text); background: var(--subject-bg); border: 1px solid var(--subject-border); padding: 3px 8px; border-radius: 4px; display: inline-flex; align-items: center; margin-bottom: 6px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }"
        + "  .card-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed var(--border-subtle); padding-top: 6px; margin-top: 4px; font-size: 11px; color: var(--text-muted); }"
        + "  .task-assignee { font-weight: 500; color: var(--text-muted); display: inline-flex; align-items: center; }"
        + "  .task-date { font-size: 11px; color: var(--text-muted); display: inline-flex; align-items: center; }"
        + "  .task-date.overdue { color: #f87171; font-weight: 700; }"
        + "  .card-actions { display: flex; gap: 4px; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border-subtle); flex-wrap: wrap; }"
        + "  .act-btn { font-size: 11px; font-weight: 600; padding: 3px 7px; border-radius: 4px; text-decoration: none; background: var(--act-btn-bg); color: var(--act-btn-text); border: 1px solid var(--act-btn-border); transition: all 0.15s; display: inline-flex; align-items: center; cursor: pointer; }"
        + "  .act-btn:hover { background: var(--act-btn-hover); color: var(--text-main); }"
        + "  .act-primary { background: rgba(37,99,235,0.2); color: #60a5fa; border-color: rgba(96,165,250,0.4); }"
        + "  .act-primary:hover { background: #2563eb; color: #ffffff; }"
        + "  .act-purple { background: rgba(124,58,237,0.2); color: #c084fc; border-color: rgba(192,132,252,0.4); }"
        + "  .act-purple:hover { background: #7c3aed; color: #ffffff; }"
        + "  .act-success { background: rgba(5,150,105,0.2); color: #34d399; border-color: rgba(52,211,153,0.4); }"
        + "  .act-success:hover { background: #059669; color: #ffffff; }"
        + "  .act-danger { background: rgba(220,38,38,0.2); color: #f87171; border-color: rgba(248,113,113,0.4); margin-left: auto; }"
        + "  .act-danger:hover { background: #dc2626; color: #ffffff; }"
        + "  /* Модальные окна */"
        + "  .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.7); z-index: 1000; align-items: center; justify-content: center; backdrop-filter: blur(4px); }"
        + "  .modal-overlay.active { display: flex; }"
        + "  .modal-box { background: var(--modal-bg); width: 500px; max-width: 95vw; border-radius: 10px; box-shadow: 0 20px 40px rgba(0,0,0,0.4); border: 1px solid var(--modal-border); overflow: hidden; animation: pop 0.18s ease-out; color: var(--text-main); }"
        + "  @keyframes pop { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }"
        + "  .modal-header { padding: 14px 18px; background: var(--modal-header); border-bottom: 1px solid var(--modal-border); display: flex; justify-content: space-between; align-items: center; }"
        + "  .modal-header h3 { font-size: 15px; font-weight: 700; color: var(--text-main); }"
        + "  .modal-close { cursor: pointer; font-size: 20px; color: var(--text-muted); line-height: 1; }"
        + "  .modal-close:hover { color: var(--text-main); }"
        + "  .modal-body { padding: 18px; display: flex; flex-direction: column; gap: 12px; max-height: 70vh; overflow-y: auto; }"
        + "  .form-group { display: flex; flex-direction: column; gap: 4px; }"
        + "  .form-label { font-size: 12px; font-weight: 600; color: var(--text-muted); }"
        + "  .form-input, .form-select, .form-textarea { padding: 8px 12px; border: 1px solid var(--input-border); border-radius: 6px; font-size: 13px; outline: none; width: 100%; box-sizing: border-box; background: var(--input-bg); color: var(--input-text); }"
        + "  .form-input:focus, .form-select:focus, .form-textarea:focus { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.2); }"
        + "  .modal-footer { padding: 12px 18px; background: var(--modal-header); border-top: 1px solid var(--modal-border); display: flex; justify-content: space-between; gap: 8px; }"
        + "</style></head><body>"
        + "<div class='header-bar'>"
        + "  <div class='header-title'>" + IconBoard + " Канбан-доска <span style='font-size:12px; font-weight:500; color:var(--text-muted); margin-left:8px;'>• Всего задач: " + ВсегоЗадач + "</span></div>"
        + "  <div class='controls'>"
        + "    <input type='text' class='search-input' placeholder='Поиск задач...' oninput='filterTasks(this.value)'>"
        + "    <button onclick='openNewTaskModal()' class='btn btn-primary'>" + IconPlus + " Новая задача</button>"
        + "    <a href='#refresh' class='btn btn-secondary'>" + IconRefresh + " Обновить</a>"
        + "    <button onclick='toggleTheme()' class='btn btn-secondary' id='themeToggleBtn'>" + IconTheme + " <span id='themeText'>Тема</span></button>"
        + "  </div>"
        + "</div>"
        + "<div class='board'>"
        +    СтолбцыHTML
        + "</div>"
        + "<!-- Модальное окно редактирования задачи -->"
        + "<div id='editModal' class='modal-overlay' onclick='closeModalBg(event, &apos;editModal&apos;)'>"
        + "  <div class='modal-box'>"
        + "    <div class='modal-header'>"
        + "      <h3>Редактирование задачи 1С</h3>"
        + "      <span class='modal-close' onclick='closeModal(&apos;editModal&apos;)'>&times;</span>"
        + "    </div>"
        + "    <div class='modal-body'>"
        + "      <input type='hidden' id='editRef'>"
        + "      <div class='form-group'><div class='form-label'>Заголовок задачи:</div><input type='text' id='editTitle' class='form-input'></div>"
        + "      <div class='form-group'><div class='form-label'>Описание:</div><textarea id='editDesc' class='form-textarea' rows='4'></textarea></div>"
        + "      <div class='form-group'><div class='form-label'>Приоритет:</div><select id='editPriority' class='form-select'><option value='high'>Высокий</option><option value='medium'>Средний</option><option value='low'>Низкий</option></select></div>"
        + "      <div class='form-group'><div class='form-label'>Предмет / Заказ / Контрагент:</div><div id='editSubject' style='font-size:13px; font-weight:600; color:#60a5fa;'>-</div></div>"
        + "      <div class='form-group'><div class='form-label'>Исполнитель:</div><div id='editAssignee' style='font-size:13px; color:var(--text-muted);'>-</div></div>"
        + "    </div>"
        + "    <div class='modal-footer'>"
        + "      <button onclick='submitEditTask()' class='btn btn-primary'>💾 Сохранить изменения</button>"
        + "      <button onclick='closeModal(&apos;editModal&apos;)' class='btn btn-secondary'>Закрыть</button>"
        + "    </div>"
        + "  </div>"
        + "</div>"
        + "<!-- Модальное окно создания задачи -->"
        + "<div id='newModal' class='modal-overlay' onclick='closeModalBg(event, &apos;newModal&apos;)'>"
        + "  <div class='modal-box'>"
        + "    <div class='modal-header'>"
        + "      <h3>Создание новой задачи в 1С</h3>"
        + "      <span class='modal-close' onclick='closeModal(&apos;newModal&apos;)'>&times;</span>"
        + "    </div>"
        + "    <div class='modal-body'>"
        + "      <div class='form-group'><div class='form-label'>Название задачи:</div><input type='text' id='newTitle' class='form-input' placeholder='Например: Согласовать договор с клиентом'></div>"
        + "      <div class='form-group'><div class='form-label'>Описание:</div><textarea id='newDesc' class='form-textarea' rows='3' placeholder='Детали поручения...'></textarea></div>"
        + "      <div class='form-group'><div class='form-label'>Приоритет:</div><select id='newPriority' class='form-select'><option value='high'>Высокий</option><option value='medium' selected>Средний</option><option value='low'>Низкий</option></select></div>"
        + "      <div class='form-group'><div class='form-label'>Контрагент:</div><select id='newPartner' class='form-select'>" + ОпцииКонтрагентов + "</select></div>"
        + "      <div class='form-group'><div class='form-label'>Срок исполнения:</div><select id='newDays' class='form-select'><option value='1'>1 день (Срочно)</option><option value='3' selected>3 дня (Стандартно)</option><option value='7'>7 дней (Неделя)</option></select></div>"
        + "    </div>"
        + "    <div class='modal-footer'>"
        + "      <button onclick='submitNewTask()' class='btn btn-primary'>💾 Создать задачу в 1С</button>"
        + "      <button onclick='closeModal(&apos;newModal&apos;)' class='btn btn-secondary'>Отмена</button>"
        + "    </div>"
        + "  </div>"
        + "</div>"
        + "<script>"
        + "  function applySavedTheme() {"
        + "    try {"
        + "      var t = localStorage.getItem('v8_app_theme') || 'dark';"
        + "      if (t === 'light') {"
        + "        document.body.classList.add('theme-light');"
        + "        var txt = document.getElementById('themeText'); if(txt) txt.textContent = '🌙 Темная';"
        + "      } else {"
        + "        document.body.classList.remove('theme-light');"
        + "        var txt = document.getElementById('themeText'); if(txt) txt.textContent = '☀️ Светлая';"
        + "      }"
        + "    } catch(e){}"
        + "  }"
        + "  function toggleTheme() {"
        + "    try {"
        + "      var isLight = document.body.classList.toggle('theme-light');"
        + "      var newT = isLight ? 'light' : 'dark';"
        + "      localStorage.setItem('v8_app_theme', newT);"
        + "      var txt = document.getElementById('themeText'); if(txt) txt.textContent = isLight ? '🌙 Темная' : '☀️ Светлая';"
        + "    } catch(e){}"
        + "  }"
        + "  applySavedTheme();"
        + "  function filterTasks(q) {"
        + "    var query = q.toLowerCase();"
        + "    var cards = document.querySelectorAll('.task-card');"
        + "    cards.forEach(function(card) {"
        + "      card.style.display = (card.textContent.toLowerCase().indexOf(query) >= 0) ? '' : 'none';"
        + "    });"
        + "  }"
        + "  document.addEventListener('click', function(e) {"
        + "    var btn = e.target.closest('.btn-open-edit');"
        + "    if (btn) {"
        + "      var ref = btn.getAttribute('data-ref');"
        + "      var title = btn.getAttribute('data-title');"
        + "      var desc = btn.getAttribute('data-desc');"
        + "      var prio = btn.getAttribute('data-prio');"
        + "      var subject = btn.getAttribute('data-subject');"
        + "      var assignee = btn.getAttribute('data-assignee');"
        + "      document.getElementById('editRef').value = ref;"
        + "      document.getElementById('editTitle').value = title;"
        + "      document.getElementById('editDesc').value = desc;"
        + "      document.getElementById('editPriority').value = prio || 'medium';"
        + "      document.getElementById('editSubject').textContent = subject || 'Без привязки';"
        + "      document.getElementById('editAssignee').textContent = assignee || 'Администратор';"
        + "      document.getElementById('editModal').classList.add('active');"
        + "    }"
        + "  });"
        + "  function openNewTaskModal() {"
        + "    document.getElementById('newTitle').value = '';"
        + "    document.getElementById('newDesc').value = '';"
        + "    document.getElementById('newModal').classList.add('active');"
        + "  }"
        + "  function closeModal(id) {"
        + "    var m = document.getElementById(id); if(m) m.classList.remove('active');"
        + "  }"
        + "  function closeModalBg(ev, id) {"
        + "    if (ev.target.id === id) closeModal(id);"
        + "  }"
        + "  function submitEditTask() {"
        + "    var ref = document.getElementById('editRef').value;"
        + "    var title = document.getElementById('editTitle').value.trim();"
        + "    var desc = document.getElementById('editDesc').value.trim();"
        + "    var prio = document.getElementById('editPriority').value;"
        + "    if (!title) { alert('Укажите название задачи'); return; }"
        + "    closeModal('editModal');"
        + "    window.location.href = '#updateTask?ref=' + encodeURIComponent(ref) + '&title=' + encodeURIComponent(title) + '&desc=' + encodeURIComponent(desc) + '&prio=' + encodeURIComponent(prio);"
        + "  }"
        + "  function submitNewTask() {"
        + "    var title = document.getElementById('newTitle').value.trim();"
        + "    var desc = document.getElementById('newDesc').value.trim();"
        + "    var prio = document.getElementById('newPriority').value;"
        + "    var partner = document.getElementById('newPartner').value;"
        + "    var days = document.getElementById('newDays').value;"
        + "    if (!title) { alert('Укажите название задачи'); return; }"
        + "    closeModal('newModal');"
        + "    window.location.href = '#createTask?title=' + encodeURIComponent(title) + '&desc=' + encodeURIComponent(desc) + '&prio=' + encodeURIComponent(prio) + '&partner=' + encodeURIComponent(partner) + '&days=' + encodeURIComponent(days);"
        + "  }"
        + "</script>"
        + "</body></html>";
    
    Возврат HTML;
КонецФункции

// =============================================================================
// ОБРАБОТЧИК КЛИКОВ И ДЕЙСТВИЙ
// =============================================================================

&НаКлиенте
Процедура КанбанHTMLПриНажатииНаСсылку(Элемент, ДанныеСобытия, СтандартнаяОбработка)
    СтандартнаяОбработка = Ложь;
    
    СтрокаВызова = "";
    Если ТипЗнч(ДанныеСобытия) = Тип("Строка") Тогда
        СтрокаВызова = ДанныеСобытия;
    Иначе
        Попытка
            СтрокаВызова = ДанныеСобытия.Href;
        Исключение
            Попытка
                СтрокаВызова = ДанныеСобытия.href;
            Исключение
                СтрокаВызова = Строка(ДанныеСобытия);
            КонецПопытки;
        КонецПопытки;
    КонецЕсли;
    
    ИндРешетки = СтрНайти(СтрокаВызова, "#");
    Если ИндРешетки > 0 Тогда
        СтрокаВызова = Сред(СтрокаВызова, ИндРешетки + 1);
    ИначеЕсли СтрНайти(СтрокаВызова, "/kanban/") > 0 Тогда
        ИндКанбан = СтрНайти(СтрокаВызова, "/kanban/");
        СтрокаВызова = Сред(СтрокаВызова, ИндКанбан + 8);
    КонецЕсли;
    
    Если СтрНачинаетсяС(СтрокаВызова, "/") Тогда
        СтрокаВызова = Сред(СтрокаВызова, 2);
    КонецЕсли;
    
    ИндВопроса = СтрНайти(СтрокаВызова, "?");
    ИмяКоманды = ?(ИндВопроса > 0, Лев(СтрокаВызова, ИндВопроса - 1), СтрокаВызова);
    СтрокаПараметров = ?(ИндВопроса > 0, Сред(СтрокаВызова, ИндВопроса + 1), "");
    
    мПараметры = РазобратьПараметрыURL(СтрокаПараметров);
    
    Если ИмяКоманды = "moveTask" Тогда
        Ref = мПараметры.Получить("ref");
        ToState = мПараметры.Получить("to");
        
        ТекстОшибки = "";
        ИзменитьСтатусЗадачи1СНаСервере(Ref, ToState, ТекстОшибки);
        Если ЗначениеЗаполнено(ТекстОшибки) Тогда
            ПоказатьПредупреждение(, "Ошибка: " + ТекстОшибки);
        КонецЕсли;
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "createTask" Тогда
        Title = мПараметры.Получить("title");
        Desc = мПараметры.Получить("desc");
        Priority = мПараметры.Получить("prio");
        PartnerRef = мПараметры.Получить("partner");
        Days = мПараметры.Получить("days");
        
        СоздатьЗадачу1СРасширеннуюНаСервере(Title, Desc, PartnerRef, "", "", Priority, Число(Days));
        ОбновитьДоску();
        ПоказатьОповещениеПользователя("Задача создана", , "Новая задача «" + Title + "» добавлена на доску!", БиблиотекаКартинок.Информация);
        
    ИначеЕсли ИмяКоманды = "updateTask" Тогда
        Ref = мПараметры.Получить("ref");
        Title = мПараметры.Получить("title");
        Desc = мПараметры.Получить("desc");
        Priority = мПараметры.Получить("prio");
        
        ОбновитьЗадачу1СНаСервере(Ref, Title, Desc, Priority);
        ОбновитьДоску();
        ПоказатьОповещениеПользователя("Задача обновлена", , "Изменения по задаче сохранены!", БиблиотекаКартинок.Информация);
        
    ИначеЕсли ИмяКоманды = "deleteTask" Тогда
        Ref = мПараметры.Получить("ref");
        УдалитьЗадачу1СНаСервере(Ref);
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "refresh" Тогда
        ОбновитьДоску();
    КонецЕсли;
КонецПроцедуры

// =============================================================================
// СЕРВЕРНЫЕ МЕТОДЫ 1С
// =============================================================================

&НаСервере
Процедура ИзменитьСтатусЗадачи1СНаСервере(RefСтрока, ЦелеваяКолонка, ТекстОшибки = "")
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Ссылка = Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
        Если Не ЗначениеЗаполнено(Ссылка) Тогда
            ТекстОшибки = "Задача не найдена: " + RefСтрока;
            Возврат;
        КонецЕсли;
        
        мОбъектЗадачи = Ссылка.ПолучитьОбъект();
        Если мОбъектЗадачи = Неопределено Тогда
            ТекстОшибки = "Не удалось открыть задачу.";
            Возврат;
        КонецЕсли;
        
        ОписаниеОчищ = СтрЗаменить(мОбъектЗадачи.Описание, "[Статус: На проверке]", "");
        ОписаниеОчищ = СокрЛП(ОписаниеОчищ);
        
        Если ЦелеваяКолонка = "todo" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Ложь;
            мОбъектЗадачи.Выполнена = Ложь;
            мОбъектЗадачи.Описание = ОписаниеОчищ;
        ИначеЕсли ЦелеваяКолонка = "in_progress" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Истина;
            мОбъектЗадачи.Выполнена = Ложь;
            мОбъектЗадачи.Описание = ОписаниеОчищ;
            Если Не ЗначениеЗаполнено(мОбъектЗадачи.ДатаПринятияКИсполнению) Тогда
                мОбъектЗадачи.ДатаПринятияКИсполнению = ТекущаяДатаСеанса();
            КонецЕсли;
        ИначеЕсли ЦелеваяКолонка = "review" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Истина;
            мОбъектЗадачи.Выполнена = Ложь;
            мОбъектЗадачи.Описание = ?(ПустаяСтрока(ОписаниеОчищ), "[Статус: На проверке]", ОписаниеОчищ + " [Статус: На проверке]");
        ИначеЕсли ЦелеваяКолонка = "done" Тогда
            мОбъектЗадачи.Выполнена = Истина;
            мОбъектЗадачи.ДатаИсполнения = ТекущаяДатаСеанса();
            мОбъектЗадачи.Описание = ОписаниеОчищ;
        КонецЕсли;
        
        мОбъектЗадачи.Записать();
    Исключение
        ТекстОшибки = ОписаниеОшибки();
    КонецПопытки;
КонецПроцедуры

&НаСервере
Функция СоздатьЗадачу1СРасширеннуюНаСервере(ЗаголовокЗадачи, Описание, КонтрагентRef, ЗаказRef, ИсполнительRef, ВажностьСтрока, СрокДней)
    Попытка
        НоваяЗадача = Задачи.ЗадачаИсполнителя.СоздатьЗадачу();
        НоваяЗадача.Дата = ТекущаяДатаСеанса();
        НоваяЗадача.Наименование = ?(ПустаяСтрока(ЗаголовокЗадачи), "Новая задача", ЗаголовокЗадачи);
        НоваяЗадача.Описание = Описание;
        
        Попытка
            НоваяЗадача.Автор = ПользователиИнформационнойБазы.ТекущийПользователь();
        Исключение
        КонецПопытки;
        
        Если ЗначениеЗаполнено(КонтрагентRef) Тогда
            Попытка
                УИД = Новый УникальныйИдентификатор(КонтрагентRef);
                КонтрагентСсылка = Справочники.Контрагенты.ПолучитьСсылку(УИД);
                Если ЗначениеЗаполнено(КонтрагентСсылка) Тогда
                    НоваяЗадача.Предмет = КонтрагентСсылка;
                КонецЕсли;
            Исключение
            КонецПопытки;
        КонецЕсли;
        
        Если ВажностьСтрока = "high" Тогда
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая;
        ИначеЕсли ВажностьСтрока = "low" Тогда
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Низкая;
        Иначе
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Обычная;
        КонецЕсли;
        
        Если СрокДней > 0 Тогда
            НоваяЗадача.СрокИсполнения = ТекущаяДатаСеанса() + (86400 * СрокДней);
        КонецЕсли;
        
        НоваяЗадача.Записать();
        Возврат Истина;
    Исключение
        Возврат Ложь;
    КонецПопытки;
КонецФункции

&НаСервере
Процедура ОбновитьЗадачу1СНаСервере(RefСтрока, ЗаголовокЗадачи, Описание, ВажностьСтрока)
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Ссылка = Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
        Если ЗначениеЗаполнено(Ссылка) Тогда
            Объект = Ссылка.ПолучитьОбъект();
            Если Объект <> Неопределено Тогда
                Объект.Наименование = ЗаголовокЗадачи;
                Объект.Описание = Описание;
                Если ВажностьСтрока = "high" Тогда
                    Объект.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая;
                ИначеЕсли ВажностьСтрока = "low" Тогда
                    Объект.Важность = Перечисления.ВариантыВажностиЗадачи.Низкая;
                Иначе
                    Объект.Важность = Перечисления.ВариантыВажностиЗадачи.Обычная;
                КонецЕсли;
                Объект.Записать();
            КонецЕсли;
        КонецЕсли;
    Исключение
    КонецПопытки;
КонецПроцедуры

&НаСервере
Процедура УдалитьЗадачу1СНаСервере(RefСтрока)
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Ссылка = Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
        Если ЗначениеЗаполнено(Ссылка) Тогда
            Объект = Ссылка.ПолучитьОбъект();
            Если Объект <> Неопределено Тогда
                Объект.УстановитьПометкуУдаления(Истина);
            КонецЕсли;
        КонецЕсли;
    Исключение
    КонецПопытки;
КонецПроцедуры

// =============================================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// =============================================================================

&НаСервереБезКонтекста
Функция ЭкранироватьHTML(Знач Текст)
    Если Не ЗначениеЗаполнено(Текст) Тогда Возврат ""; КонецЕсли;
    Текст = Строка(Текст);
    Текст = СтрЗаменить(Текст, "&", "&amp;");
    Текст = СтрЗаменить(Текст, "<", "&lt;");
    Текст = СтрЗаменить(Текст, ">", "&gt;");
    Текст = СтрЗаменить(Текст, Символ(34), "&quot;");
    Текст = СтрЗаменить(Текст, "'", "&#39;");
    Текст = СтрЗаменить(Текст, Символы.ПС, " ");
    Текст = СтрЗаменить(Текст, Символы.ВК, "");
    Возврат Текст;
КонецФункции

&НаКлиенте
Функция РазобратьПараметрыURL(СтрокаПараметров)
    Результат = Новый Соответствие;
    Если ПустаяСтрока(СтрокаПараметров) Тогда Возврат Результат; КонецЕсли;
    
    МассивПар = СтрРазделить(СтрокаПараметров, "&");
    Для Каждого Пара Из МассивПар Цикл
        ИндРавно = СтрНайти(Пара, "=");
        Если ИндРавно > 0 Тогда
            Ключ = Лев(Пара, ИндРавно - 1);
            Значение = Сред(Пара, ИндРавно + 1);
            Результат.Вставить(Ключ, ДекодироватьURL(Значение));
        Иначе
            Результат.Вставить(Пара, "");
        КонецЕсли;
    КонецЦикла;
    
    Возврат Результат;
КонецФункции

&НаКлиенте
Функция ДекодироватьURL(ВходнаяСтрока)
    Текст = СтрЗаменить(ВходнаяСтрока, "+", " ");
    Длина = СтрДлина(Текст);
    Результат = "";
    Инд = 1;
    Пока Инд <= Длина Цикл
        Симв = Сред(Текст, Инд, 1);
        Если Симв = "%" И (Инд + 2 <= Длина) Тогда
            КодСимвола = Сред(Текст, Инд + 1, 2);
            Попытка
                Результат = Результат + ДекодироватьHEX(КодСимвола);
                Инд = Инд + 3;
                Продолжить;
            Исключение
            КонецПопытки;
        КонецЕсли;
        Результат = Результат + Симв;
        Инд = Инд + 1;
    КонецЦикла;
    Возврат Результат;
КонецФункции

&НаКлиенте
Функция ДекодироватьHEX(Hex)
    СимволыHex = "0123456789ABCDEF";
    Hex = ВРег(Hex);
    И1 = СтрНайти(СимволыHex, Сред(Hex, 1, 1)) - 1;
    И2 = СтрНайти(СимволыHex, Сред(Hex, 2, 1)) - 1;
    Если И1 >= 0 И И2 >= 0 Тогда
        Код = (И1 * 16) + И2;
        Возврат Символ(Код);
    КонецЕсли;
    Возврат "%" + Hex;
КонецФункции
