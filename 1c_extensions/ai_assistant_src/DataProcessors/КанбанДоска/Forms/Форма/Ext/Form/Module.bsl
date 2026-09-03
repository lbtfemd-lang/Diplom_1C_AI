// =============================================================================
// Канбан-доска — 100% нативное решение 1С:Предприятие
// =============================================================================

&НаСервере
Процедура ПриСозданииНаСервере(Отказ, СтандартнаяОбработка)
    КанбанHTML = ПолучитьДоску1СНаСервере();
КонецПроцедуры

&НаКлиенте
Процедура ПриОткрытии(Отказ)
    Если ПустаяСтрока(КанбанHTML) Тогда
        ОбновитьДоску();
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура ОбработкаОповещения(ИмяСобытия, Параметр, Источник)
    ОбновитьДоску();
КонецПроцедуры

// =============================================================================
// ОТКРЫТИЕ ФОРМЫ РЕДАКТИРОВАНИЯ И СОЗДАНИЯ ЗАДАЧИ
// =============================================================================

&НаКлиенте
Процедура ОткрытьФормуЗадачи(КлючУИД = "")
    ПараметрыФормы = Новый Структура;
    Если ЗначениеЗаполнено(КлючУИД) Тогда
        ПараметрыФормы.Вставить("Ключ", КлючУИД);
    КонецЕсли;
    
    // Динамическое определение точного пути к ФормаЗадачи
    ИндПервойТочки = СтрНайти(ЭтотОбъект.ИмяФормы, ".");
    ИндВторойТочки = ?(ИндПервойТочки > 0, СтрНайти(ЭтотОбъект.ИмяФормы, ".", , ИндПервойТочки + 1), 0);
    Если ИндВторойТочки > 0 Тогда
        ПрефиксОбъекта = Лев(ЭтотОбъект.ИмяФормы, ИндВторойТочки - 1);
    Иначе
        ПрефиксОбъекта = "Обработка.КанбанДоска";
    КонецЕсли;
    
    ИмяФормыЗадачи = ПрефиксОбъекта + ".Форма.ФормаЗадачи";
    
    Попытка
        ОткрытьФорму(ИмяФормыЗадачи, ПараметрыФормы, ЭтотОбъект);
    Исключение
        Попытка
            ОткрытьФорму("Обработка.КанбанДоска.Форма.ФормаЗадачи", ПараметрыФормы, ЭтотОбъект);
        Исключение
            ПоказатьПредупреждение(, "Не удалось открыть форму задачи: " + ОписаниеОшибки());
        КонецПопытки;
    КонецПопытки;
КонецПроцедуры

// =============================================================================
// ОТРИСОВКА И ГЕНЕРАЦИЯ HTML ДОСКИ
// =============================================================================

&НаКлиенте
Процедура ОбновитьДоску()
    КанбанHTML = ПолучитьДоску1СНаСервере();
КонецПроцедуры

&НаСервере
Функция ПолучитьДоску1СНаСервере()
    Попытка
        // ПроверитьИИнициализироватьЗадачи1С();
        
        Запрос = Новый Запрос;
        Запрос.Текст = 
            "ВЫБРАТЬ
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
            
            Если Выборка.Выполнена Тогда
                Колонка = "done";
            ИначеЕсли Выборка.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая И Выборка.ПринятаКИсполнению Тогда
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
                СтруктураЗ.Вставить("is_overdue", (Выборка.КрайнийСрок < ТекущаяДата() И НЕ Выборка.Выполнена));
            Иначе
                СтруктураЗ.Вставить("due_date", "");
                СтруктураЗ.Вставить("is_overdue", Ложь);
            КонецЕсли;
            
            МассивЗадач.Добавить(СтруктураЗ);
        КонецЦикла;
        
        Возврат СгенерироватьКанбанHTML(МассивЗадач);
    Исключение
        Возврат "<html><body style='font-family:sans-serif;padding:20px;color:#b91c1c;background:#fff5f5;'>"
            + "<h3>Ошибка загрузки задач 1С:</h3>"
            + "<p>" + ЭкранироватьHTML(ОписаниеОшибки()) + "</p>"
            + "</body></html>";
    КонецПопытки;
КонецФункции

&НаСервере
Процедура ПроверитьИИнициализироватьЗадачи1С()
    // Автоматическое пересоздание отключено, чтобы удаленные задачи не восстанавливались
    Возврат;
КонецПроцедуры

&НаСервере
Процедура СоздатьДемоЗадачу(Заголовок, Описание, Предмет, Важность, Принята, Выполнена)
    Попытка
        НоваяЗадача = Задачи.ЗадачаИсполнителя.СоздатьЗадачу();
        НоваяЗадача.Дата = ТекущаяДата();
        НоваяЗадача.Наименование = Заголовок;
        НоваяЗадача.Описание = Описание;
        Если ЗначениеЗаполнено(Предмет) Тогда
            НоваяЗадача.Предмет = Предмет;
        КонецЕсли;
        НоваяЗадача.Важность = Важность;
        НоваяЗадача.ПринятаКИсполнению = Принята;
        НоваяЗадача.Выполнена = Выполнена;
        Если Выполнена Тогда
            НоваяЗадача.ДатаИсполнения = ТекущаяДата();
        КонецЕсли;
        НоваяЗадача.СрокИсполнения = ТекущаяДата() + 86400 * 2;
        
        Попытка
            НоваяЗадача.Исполнитель = Пользователи.АвторизованныйПользователь();
        Исключение
            НоваяЗадача.Исполнитель = Справочники.Пользователи.НайтиПоНаименованию("Администратор");
        КонецПопытки;
        
        НоваяЗадача.ОбменДанными.Загрузка = Истина;
        НоваяЗадача.Записать();
    Исключение КонецПопытки;
КонецПроцедуры

&НаСервере
Функция СгенерироватьКанбанHTML(МассивЗадач)
    Колонки = Новый Массив;
    Колонки.Добавить(Новый Структура("id, name, color, badge", "todo", "К выполнению", "#3b82f6", "bg-blue"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "in_progress", "В работе", "#f59e0b", "bg-amber"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "review", "На проверке", "#a855f7", "bg-purple"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "done", "Готово", "#10b981", "bg-emerald"));
    
    IconBoard = "<svg width=""16"" height=""16"" viewBox=""0 0 24 24"" fill=""none"" stroke=""#f59e0b"" stroke-width=""2"" style=""vertical-align:middle;margin-right:6px;""><rect x=""3"" y=""3"" width=""18"" height=""18"" rx=""2"" ry=""2""></rect><line x1=""9"" y1=""3"" x2=""9"" y2=""21""></line><line x1=""15"" y1=""3"" x2=""15"" y2=""21""></line></svg>";
    IconUser = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><path d=""M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2""></path><circle cx=""12"" cy=""7"" r=""4""></circle></svg>";
    IconBuilding = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""#60a5fa"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><rect x=""4"" y=""2"" width=""16"" height=""20"" rx=""2"" ry=""2""></rect><path d=""M9 22v-4h6v4""></path><path d=""M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01""></path></svg>";
    IconCalendar = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><rect x=""3"" y=""4"" width=""18"" height=""18"" rx=""2"" ry=""2""></rect><line x1=""16"" y1=""2"" x2=""16"" y2=""6""></line><line x1=""8"" y1=""2"" x2=""8"" y2=""6""></line><line x1=""3"" y1=""10"" x2=""21"" y2=""10""></line></svg>";
    IconRefresh = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><polyline points=""23 4 23 10 17 10""></polyline><path d=""M20.49 15a9 9 0 1 1-2.12-9.36L23 10""></path></svg>";
    IconPlus = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><line x1=""12"" y1=""5"" x2=""12"" y2=""19""></line><line x1=""5"" y1=""12"" x2=""19"" y2=""12""></line></svg>";
    IconTheme = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><path d=""M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z""></path></svg>";

    СтолбцыHTML = "";
    ВсегоЗадач = 0;
    
    Для Каждого Колонка Из Колонки Цикл
        ЗадачиКолонки = "";
        Счётчик = 0;
        
        Для Каждого З Из МассивЗадач Цикл
            Если З.column <> Колонка.id Тогда Продолжить; КонецЕсли;
            
            Счётчик = Счётчик + 1;
            ВсегоЗадач = ВсегоЗадач + 1;
            
            Ref = З.ref;
            Id = З.id;
            Title = ЭкранироватьHTML(З.title);
            Description = ЭкранироватьHTML(З.description);
            Assignee = ЭкранироватьHTML(З.assignee);
            Subject = ЭкранироватьHTML(З.subject);
            DueDate = З.due_date;
            IsOverdue = З.is_overdue;
            
            Если З.priority = "high" Тогда
                ПриорHTML = "<span class=""priority-badge priority-high"">Высокий</span>";
            ИначеЕсли З.priority = "low" Тогда
                ПриорHTML = "<span class=""priority-badge priority-low"">Низкий</span>";
            Иначе
                ПриорHTML = "<span class=""priority-badge priority-med"">Средний</span>";
            КонецЕсли;
            
            ПредметHTML = "";
            Если Не ПустаяСтрока(Subject) Тогда
                ПредметHTML = "<div class=""task-subject"" title=""Предмет в 1С"">" + IconBuilding + Subject + "</div>";
            КонецЕсли;
            
            ДедлайнHTML = "";
            Если Не ПустаяСтрока(DueDate) Тогда
                КлассДедлайн = ?(IsOverdue, "task-date overdue", "task-date");
                ДедлайнHTML = "<div class=""" + КлассДедлайн + """>" + IconCalendar + DueDate + ?(IsOverdue, " (просрочено!)", "") + "</div>";
            КонецЕсли;
            
            КнопкиДействий = "<div class=""card-actions"">";
            
            Если Колонка.id = "todo" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=in_progress"" class=""act-btn act-primary"" title=""Взять в работу"">▶ В работу</a>";
            ИначеЕсли Колонка.id = "in_progress" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=review"" class=""act-btn act-purple"" title=""Передать на проверку"">⏳ Проверить</a>";
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=done"" class=""act-btn act-success"" title=""Завершить задачу"">✓ Готово</a>";
            ИначеЕсли Колонка.id = "review" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=done"" class=""act-btn act-success"" title=""Утвердить и завершить"">✓ Готово</a>";
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=in_progress"" class=""act-btn"" title=""Вернуть на доработку"">↺ В работу</a>";
            ИначеЕсли Колонка.id = "done" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""#moveTask?ref=" + Ref + "&to=todo"" class=""act-btn"" title=""Вернуть к выполнению"">↺ Вернуть</a>";
            КонецЕсли;
            
            КнопкиДействий = КнопкиДействий + "<a href=""#openIn1C?ref=" + Ref + """ class=""act-btn"" title=""Открыть задачу в форме 1С"">✏️ 1С</a>";
            КнопкиДействий = КнопкиДействий + "<a href=""#deleteTask?ref=" + Ref + """ class=""act-btn act-danger"" title=""Удалить задачу в 1С"">🗑</a></div>";
            
            ЗадачиКолонки = ЗадачиКолонки
                + "<div class=""task-card"">"
                + "  <div class=""card-top"">"
                + "    <span class=""task-id"">#" + Id + "</span>"
                + "    " + ПриорHTML
                + "  </div>"
                + "  <a href=""#openIn1C?ref=" + Ref + """ class=""task-title-link"" title=""Нажмите, чтобы открыть задачу в 1С""><div class=""task-title"">" + Title + "</div></a>"
                +    ПредметHTML
                + "  <div class=""card-footer"">"
                + "    <div class=""task-assignee"" title=""Исполнитель"">" + IconUser + Assignee + "</div>"
                +      ДедлайнHTML
                + "  </div>"
                +    КнопкиДействий
                + "</div>";
        КонецЦикла;
        
        СтолбцыHTML = СтолбцыHTML
            + "<div class=""column"">"
            + "  <div class=""column-header"" style=""border-top: 3px solid " + Колонка.color + """>"
            + "    <span class=""column-title"">" + Колонка.name + "</span>"
            + "    <span class=""column-badge " + Колонка.badge + """>" + Счётчик + "</span>"
            + "  </div>"
            + "  <div class=""column-body"">"
            +      ЗадачиКолонки
            + "  </div>"
            + "</div>";
    КонецЦикла;
    
    HTML = "<!DOCTYPE html>"
        + "<html><head><meta charset=""utf-8"">"
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
        + "  .search-input { padding: 6px 12px; background: var(--input-bg); border: 1px solid var(--input-border); color: var(--input-text); border-radius: 6px; font-size: 13px; width: 220px; outline: none; transition: border 0.2s; }"
        + "  .search-input:focus { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.2); }"
        + "  .btn { padding: 6px 12px; font-size: 13px; font-weight: 600; border-radius: 6px; cursor: pointer; border: none; transition: all 0.2s; display: inline-flex; align-items: center; text-decoration: none; }"
        + "  .btn-primary { background: #f59e0b; color: #ffffff; }"
        + "  .btn-primary:hover { background: #d97706; }"
        + "  .btn-secondary { background: var(--sec-btn-bg); color: var(--sec-btn-text); border: 1px solid var(--sec-btn-border); }"
        + "  .btn-secondary:hover { background: var(--sec-btn-hover); color: var(--text-main); }"
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
        + "  .task-title-link { text-decoration: none; color: inherit; display: block; }"
        + "  .task-title { font-size: 13px; font-weight: 600; color: var(--text-main); line-height: 1.35; margin-bottom: 6px; }"
        + "  .task-title:hover { color: #60a5fa; }"
        + "  .task-subject { font-size: 11px; font-weight: 600; color: var(--subject-text); background: var(--subject-bg); border: 1px solid var(--subject-border); padding: 3px 8px; border-radius: 4px; display: inline-flex; align-items: center; margin-bottom: 6px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }"
        + "  .card-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed var(--border-subtle); padding-top: 6px; margin-top: 4px; font-size: 11px; color: var(--text-muted); }"
        + "  .task-assignee { font-weight: 500; color: var(--text-muted); display: inline-flex; align-items: center; }"
        + "  .task-date { font-size: 11px; color: var(--text-muted); display: inline-flex; align-items: center; }"
        + "  .task-date.overdue { color: #f87171; font-weight: 700; }"
        + "  .card-actions { display: flex; gap: 4px; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border-subtle); flex-wrap: wrap; }"
        + "  .act-btn { font-size: 11px; font-weight: 600; padding: 3px 7px; border-radius: 4px; text-decoration: none; background: var(--act-btn-bg); color: var(--act-btn-text); border: 1px solid var(--act-btn-border); transition: all 0.15s; display: inline-flex; align-items: center; }"
        + "  .act-btn:hover { background: var(--act-btn-hover); color: var(--text-main); }"
        + "  .act-primary { background: rgba(37,99,235,0.2); color: #60a5fa; border-color: rgba(96,165,250,0.4); }"
        + "  .act-primary:hover { background: #2563eb; color: #ffffff; }"
        + "  .act-purple { background: rgba(124,58,237,0.2); color: #c084fc; border-color: rgba(192,132,252,0.4); }"
        + "  .act-purple:hover { background: #7c3aed; color: #ffffff; }"
        + "  .act-success { background: rgba(5,150,105,0.2); color: #34d399; border-color: rgba(52,211,153,0.4); }"
        + "  .act-success:hover { background: #059669; color: #ffffff; }"
        + "  .act-danger { background: rgba(220,38,38,0.2); color: #f87171; border-color: rgba(248,113,113,0.4); margin-left: auto; }"
        + "  .act-danger:hover { background: #dc2626; color: #ffffff; }"
        + "</style></head><body>"
        + "<div class=""header-bar"">"
        + "  <div class=""header-title"">" + IconBoard + " Канбан-доска <span style=""font-size:12px; font-weight:500; color:var(--text-muted); margin-left:8px;"">• Всего: " + ВсегоЗадач + "</span></div>"
        + "  <div class=""controls"">"
        + "    <input type='text' class=""search-input"" placeholder=""Поиск задач..."" oninput=""filterTasks(this.value)"">"
        + "    <a href=""#openNewIn1C"" class=""btn btn-primary"">" + IconPlus + " Задача (1С)</a>"
        + "    <a href=""#refresh"" class=""btn btn-secondary"">" + IconRefresh + " Обновить</a>"
        + "    <button onclick=""toggleTheme()"" class=""btn btn-secondary"" id=""themeToggleBtn"" title=""Переключить тему"">" + IconTheme + " <span id=""themeText"">Тема</span></button>"
        + "  </div>"
        + "</div>"
        + "<div class=""board"">"
        +    СтолбцыHTML
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
        + "</script>"
        + "</body></html>";
    
    Возврат HTML;
КонецФункции

// =============================================================================
// ОБРАБОТЧИК ДЕЙСТВИЙ И КЛИКОВ ПО ССЫЛКАМ В 1С
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
    
    Если ИмяКоманды = "openNewIn1C" Тогда
        ОткрытьФормуЗадачи();
        
    ИначеЕсли ИмяКоманды = "openIn1C" Тогда
        Ref = мПараметры.Получить("ref");
        ОткрытьФормуЗадачи(Ref);
        
    ИначеЕсли ИмяКоманды = "moveTask" Тогда
        Ref = мПараметры.Получить("ref");
        ToState = мПараметры.Получить("to");
        
        ТекстОшибки = "";
        ИзменитьСтатусЗадачи1СНаСервере(Ref, ToState, ТекстОшибки);
        Если ЗначениеЗаполнено(ТекстОшибки) Тогда
            ПоказатьПредупреждение(, "Ошибка перемещения задачи: " + ТекстОшибки);
        КонецЕсли;
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "deleteTask" Тогда
        Ref = мПараметры.Получить("ref");
        УдалитьЗадачу1СНаСервере(Ref);
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "refresh" Тогда
        ОбновитьДоску();
    КонецЕсли;
КонецПроцедуры

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
            ТекстОшибки = "Не удалось открыть объект задачи для записи.";
            Возврат;
        КонецЕсли;
        
        Если Не ЗначениеЗаполнено(мОбъектЗадачи.Исполнитель) Тогда
            Попытка
                мОбъектЗадачи.Исполнитель = Пользователи.АвторизованныйПользователь();
            Исключение
                мОбъектЗадачи.Исполнитель = Справочники.Пользователи.НайтиПоНаименованию("Администратор");
            КонецПопытки;
        КонецЕсли;
        
        Если ЦелеваяКолонка = "todo" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Ложь;
            мОбъектЗадачи.Выполнена = Ложь;
        ИначеЕсли ЦелеваяКолонка = "in_progress" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Истина;
            мОбъектЗадачи.Выполнена = Ложь;
            Если Не ЗначениеЗаполнено(мОбъектЗадачи.ДатаПринятияКИсполнению) Тогда
                мОбъектЗадачи.ДатаПринятияКИсполнению = ТекущаяДатаСеанса();
            КонецЕсли;
        ИначеЕсли ЦелеваяКолонка = "review" Тогда
            мОбъектЗадачи.ПринятаКИсполнению = Истина;
            мОбъектЗадачи.Выполнена = Ложь;
            мОбъектЗадачи.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая;
        ИначеЕсли ЦелеваяКолонка = "done" Тогда
            мОбъектЗадачи.Выполнена = Истина;
            мОбъектЗадачи.ДатаИсполнения = ТекущаяДатаСеанса();
        КонецЕсли;
        
        мОбъектЗадачи.ОбменДанными.Загрузка = Истина;
        мОбъектЗадачи.Записать();
    Исключение
        ТекстОшибки = ОписаниеОшибки();
    КонецПопытки;
КонецПроцедуры

&НаСервере
Процедура УдалитьЗадачу1СНаСервере(RefСтрока)
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Ссылка = Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
        Если ЗначениеЗаполнено(Ссылка) Тогда
            мОбъектЗадачи = Ссылка.ПолучитьОбъект();
            Если мОбъектЗадачи <> Неопределено Тогда
                мОбъектЗадачи.ОбменДанными.Загрузка = Истина;
                мОбъектЗадачи.УстановитьПометкуУдаления(Истина);
            КонецЕсли;
        КонецЕсли;
    Исключение КонецПопытки;
КонецПроцедуры

&НаСервереБезКонтекста
Функция ЭкранироватьHTML(Текст)
    Если Текст = Неопределено Тогда
        Возврат "";
    КонецЕсли;
    Рез = СтрЗаменить(Строка(Текст), "&", "&amp;");
    Рез = СтрЗаменить(Рез, "<", "&lt;");
    Рез = СтрЗаменить(Рез, ">", "&gt;");
    Рез = СтрЗаменить(Рез, """", "&quot;");
    Рез = СтрЗаменить(Рез, "'", "&#39;");
    Рез = СтрЗаменить(Рез, Символы.ПС, " ");
    Рез = СтрЗаменить(Рез, Символы.ВК, "");
    Возврат Рез;
КонецФункции

&НаКлиенте
Функция РазобратьПараметрыURL(СтрокаПараметров)
    Результат = Новый Соответствие;
    Если ПустаяСтрока(СтрокаПараметров) Тогда
        Возврат Результат;
    КонецЕсли;
    
    МассивПар = СтрРазделить(СтрокаПараметров, "&");
    Для Каждого Пара Из МассивПар Цикл
        ИндРавно = СтрНайти(Пара, "=");
        Если ИндРавно > 0 Тогда
            Ключ = Лев(Пара, ИндРавно - 1);
            Значение = Сред(Пара, ИндРавно + 1);
            Значение = СтрЗаменить(Значение, "+", " ");
            Значение = СтрЗаменить(Значение, "%20", " ");
            Значение = СтрЗаменить(Значение, "%23", "#");
            Значение = СтрЗаменить(Значение, "%26", "&");
            Значение = СтрЗаменить(Значение, "%3D", "=");
            Значение = СтрЗаменить(Значение, "%2F", "/");
            Значение = СтрЗаменить(Значение, "%3A", ":");
            Значение = СтрЗаменить(Значение, "%3F", "?");
            Результат.Вставить(Ключ, Значение);
        КонецЕсли;
    КонецЦикла;
    
    Возврат Результат;
КонецФункции
