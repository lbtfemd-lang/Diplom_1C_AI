// =============================================================================
// Канбан-доска — 100% нативное решение 1С:Предприятие
// Хранение данных: Задача.ЗадачаИсполнителя / Справочник.Контрагенты / Документы
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

// =============================================================================
// ОБРАБОТЧИКИ КОМАНД ФОРМЫ (Кнопки в шапке 1С)
// =============================================================================

&НаКлиенте
Процедура ОбновитьНажатие(Команда)
    ОбновитьДоску();
КонецПроцедуры

&НаКлиенте
Процедура СоздатьЗадачуНажатие(Команда)
    ПараметрыФормы = Новый Структура;
    ОткрытьФорму("Задача.ЗадачаИсполнителя.ФормаОбъекта", ПараметрыФормы, ЭтотОбъект);
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
        // 1. Инициализация демонстрационных задач в 1С при первом открытии
        ПроверитьИИнициализироватьЗадачи1С();
        
        // 2. Получение списка задач запросом к Задача.ЗадачаИсполнителя
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
            
            // Определение колонки
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
            
            // Важность
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
        
        // 3. Получение списков реальных метаданных 1С для формы создания задачи
        СписокКонтрагентов = ПолучитьСписокКонтрагентов1С();
        СписокИсполнителей = ПолучитьСписокИсполнителей1С();
        СписокЗаказов = ПолучитьСписокЗаказов1С();
        
        Возврат СгенерироватьКанбанHTML(МассивЗадач, СписокКонтрагентов, СписокИсполнителей, СписокЗаказов);
    Исключение
        Возврат "<html><body style='font-family:sans-serif;padding:20px;color:#b91c1c;background:#fff5f5;'>"
            + "<h3>Ошибка загрузки задач 1С:</h3>"
            + "<p>" + ЭкранироватьHTML(ОписаниеОшибки()) + "</p>"
            + "</body></html>";
    КонецПопытки;
КонецФункции

&НаСервере
Функция ПолучитьСписокКонтрагентов1С()
    Массив = Новый Массив;
    Попытка
        Запрос = Новый Запрос(
            "ВЫБРАТЬ Ссылка, Наименование, ИНН 
            |ИЗ Справочник.Контрагенты 
            |ГДЕ НЕ ПометкаУдаления И НЕ ЭтоГруппа 
            |УПОРЯДОЧИТЬ ПО Наименование");
        Выборка = Запрос.Выполнить().Выбрать();
        Пока Выборка.Следующий() Цикл
            Массив.Добавить(Новый Структура("Ref, Name, INN", 
                Строка(Выборка.Ссылка.УникальныйИдентификатор()), 
                СокрЛП(Выборка.Наименование), 
                СокрЛП(Выборка.ИНН)));
        КонецЦикла;
    Исключение КонецПопытки;
    Возврат Массив;
КонецФункции

&НаСервере
Функция ПолучитьСписокИсполнителей1С()
    Массив = Новый Массив;
    Попытка
        Запрос = Новый Запрос(
            "ВЫБРАТЬ Ссылка, Наименование 
            |ИЗ Справочник.Пользователи 
            |ГДЕ НЕ ПометкаУдаления 
            |УПОРЯДОЧИТЬ ПО Наименование");
        Выборка = Запрос.Выполнить().Выбрать();
        Пока Выборка.Следующий() Цикл
            Массив.Добавить(Новый Структура("Ref, Name", 
                Строка(Выборка.Ссылка.УникальныйИдентификатор()), 
                СокрЛП(Выборка.Наименование)));
        КонецЦикла;
    Исключение КонецПопытки;
    Возврат Массив;
КонецФункции

&НаСервере
Функция ПолучитьСписокЗаказов1С()
    Массив = Новый Массив;
    Попытка
        Запрос = Новый Запрос(
            "ВЫБРАТЬ ПЕРВЫЕ 30
            |   Заказ.Ссылка КАК Ссылка,
            |   Заказ.Номер КАК Номер,
            |   Заказ.Дата КАК Дата,
            |   Заказ.СуммаДокумента КАК Сумма,
            |   ПРЕДСТАВЛЕНИЕ(Заказ.Контрагент) КАК Контрагент
            |ИЗ
            |   Документ.ЗаказПокупателя КАК Заказ
            |ГДЕ
            |   НЕ Заказ.ПометкаУдаления
            |УПОРЯДОЧИТЬ ПО
            |   Заказ.Дата УБЫВ");
        Выборка = Запрос.Выполнить().Выбрать();
        Пока Выборка.Следующий() Цикл
            Текст = "Заказ №" + СокрЛП(Выборка.Номер) + " от " + Формат(Выборка.Дата, "ДФ=dd.MM.yyyy") + " (" + СокрЛП(Выборка.Контрагент) + ", " + Формат(Выборка.Сумма, "ЧДЦ=2") + " руб.)";
            Массив.Добавить(Новый Структура("Ref, Name", 
                Строка(Выборка.Ссылка.УникальныйИдентификатор()), 
                Текст));
        КонецЦикла;
    Исключение КонецПопытки;
    Возврат Массив;
КонецФункции

&НаСервере
Процедура ПроверитьИИнициализироватьЗадачи1С()
    Попытка
        Запрос = Новый Запрос("ВЫБРАТЬ ПЕРВЫЕ 1 Задача.Ссылка ИЗ Задача.ЗадачаИсполнителя КАК Задача ГДЕ НЕ Задача.ПометкаУдаления");
        Если НЕ Запрос.Выполнить().Пустой() Тогда
            Возврат;
        КонецЕсли;
        
        КонтрагентАльфа = Справочники.Контрагенты.НайтиПоНаименованию("АЛЬФАМАРТ", Ложь);
        Если Не ЗначениеЗаполнено(КонтрагентАльфа) Тогда
            КонтрагентАльфа = Справочники.Контрагенты.НайтиПоНаименованию("Альфа", Ложь);
        КонецЕсли;
        
        СоздатьДемоЗадачу("Подготовить коммерческое предложение", "Сформировать КП на мониторы и оргтехнику", КонтрагентАльфа, Перечисления.ВариантыВажностиЗадачи.Обычная, Ложь, Ложь);
        СоздатьДемоЗадачу("Проверить складские остатки", "Сверить остатки товара Монитор на основном складе", Неопределено, Перечисления.ВариантыВажностиЗадачи.Высокая, Истина, Ложь);
        СоздатьДемоЗадачу("Согласовать договор поставки", "Проверить реквизиты и согласовать проект договора", КонтрагентАльфа, Перечисления.ВариантыВажностиЗадачи.Высокая, Истина, Ложь);
        СоздатьДемоЗадачу("Отгрузить заказ покупателя", "Провести документ отгрузки и передать на склад", КонтрагентАльфа, Перечисления.ВариантыВажностиЗадачи.Обычная, Истина, Истина);
    Исключение КонецПопытки;
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
        НоваяЗадача.Записать();
    Исключение КонецПопытки;
КонецПроцедуры

&НаСервере
Функция СгенерироватьКанбанHTML(МассивЗадач, СписокКонтрагентов, СписокИсполнителей, СписокЗаказов)
    Колонки = Новый Массив;
    Колонки.Добавить(Новый Структура("id, name, color, badge", "todo", "К выполнению", "#2563eb", "bg-blue"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "in_progress", "В работе", "#d97706", "bg-amber"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "review", "На проверке", "#7c3aed", "bg-purple"));
    Колонки.Добавить(Новый Структура("id, name, color, badge", "done", "Готово", "#059669", "bg-emerald"));
    
    // Векторные SVG иконки
    IconBoard = "<svg width=""16"" height=""16"" viewBox=""0 0 24 24"" fill=""none"" stroke=""#f59e0b"" stroke-width=""2"" style=""vertical-align:middle;margin-right:6px;""><rect x=""3"" y=""3"" width=""18"" height=""18"" rx=""2"" ry=""2""></rect><line x1=""9"" y1=""3"" x2=""9"" y2=""21""></line><line x1=""15"" y1=""3"" x2=""15"" y2=""21""></line></svg>";
    IconUser = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><path d=""M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2""></path><circle cx=""12"" cy=""7"" r=""4""></circle></svg>";
    IconBuilding = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""#2563eb"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><rect x=""4"" y=""2"" width=""16"" height=""20"" rx=""2"" ry=""2""></rect><path d=""M9 22v-4h6v4""></path><path d=""M8 6h.01M16 6h.01M8 10h.01M16 10h.01M8 14h.01M16 14h.01""></path></svg>";
    IconCalendar = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><rect x=""3"" y=""4"" width=""18"" height=""18"" rx=""2"" ry=""2""></rect><line x1=""16"" y1=""2"" x2=""16"" y2=""6""></line><line x1=""8"" y1=""2"" x2=""8"" y2=""6""></line><line x1=""3"" y1=""10"" x2=""21"" y2=""10""></line></svg>";
    IconRefresh = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><polyline points=""23 4 23 10 17 10""></polyline><path d=""M20.49 15a9 9 0 1 1-2.12-9.36L23 10""></path></svg>";
    IconPlus = "<svg width=""12"" height=""12"" viewBox=""0 0 24 24"" fill=""none"" stroke=""currentColor"" stroke-width=""2"" style=""vertical-align:middle;margin-right:4px;""><line x1=""12"" y1=""5"" x2=""12"" y2=""19""></line><line x1=""5"" y1=""12"" x2=""19"" y2=""12""></line></svg>";

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
            
            // Бейдж приоритета
            Если З.priority = "high" Тогда
                ПриорHTML = "<span class=""priority-badge priority-high"">Высокий</span>";
            ИначеЕсли З.priority = "low" Тогда
                ПриорHTML = "<span class=""priority-badge priority-low"">Низкий</span>";
            Иначе
                ПриорHTML = "<span class=""priority-badge priority-med"">Средний</span>";
            КонецЕсли;
            
            // Тег предмета (Контрагент/Документ)
            ПредметHTML = "";
            Если Не ПустаяСтрока(Subject) Тогда
                ПредметHTML = "<div class=""task-subject"" title=""Предмет в 1С"">" + IconBuilding + Subject + "</div>";
            КонецЕсли;
            
            // Дата дедлайна
            ДедлайнHTML = "";
            Если Не ПустаяСтрока(DueDate) Тогда
                КлассДедлайн = ?(IsOverdue, "task-date overdue", "task-date");
                ДедлайнHTML = "<div class=""" + КлассДедлайн + """>" + IconCalendar + DueDate + ?(IsOverdue, " (просрочено!)", "") + "</div>";
            КонецЕсли;
            
            // Кнопки быстрых действий на карточке
            КнопкиДействий = "<div class=""card-actions"">"
                + "<a href=""v8action://openIn1C?ref=" + Ref + """ class=""act-btn"" title=""Открыть в 1С"">📄 1С</a>";
            
            Если Колонка.id = "todo" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""v8action://moveTask?ref=" + Ref + "&to=in_progress"" class=""act-btn act-primary"" title=""Взять в работу"">▶ В работу</a>";
            ИначеЕсли Колонка.id = "in_progress" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""v8action://moveTask?ref=" + Ref + "&to=done"" class=""act-btn act-success"" title=""Завершить задачу"">✓ Готово</a>";
            ИначеЕсли Колонка.id = "review" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""v8action://moveTask?ref=" + Ref + "&to=done"" class=""act-btn act-success"" title=""Утвердить и завершить"">✓ Готово</a>";
            ИначеЕсли Колонка.id = "done" Тогда
                КнопкиДействий = КнопкиДействий + "<a href=""v8action://moveTask?ref=" + Ref + "&to=todo"" class=""act-btn"" title=""Вернуть к выполнению"">↺ Вернуть</a>";
            КонецЕсли;
            
            КнопкиДействий = КнопкиДействий + "<a href=""v8action://deleteTask?ref=" + Ref + """ class=""act-btn act-danger"" title=""Удалить задачу"" onclick=""return confirm('Удалить задачу #" + Id + "?')"">🗑</a></div>";
            
            ЗадачиКолонки = ЗадачиКолонки
                + "<div class=""task-card"" draggable=""true"" data-ref=""" + Ref + """ ondragstart=""drag(event)"">"
                + "  <div class=""card-top"">"
                + "    <span class=""task-id"">#" + Id + "</span>"
                + "    " + ПриорHTML
                + "  </div>"
                + "  <div class=""task-title"" onclick=""openCardModal('" + Ref + "', '" + Title + "', '" + Description + "', '" + Subject + "', '" + Assignee + "', '" + DueDate + "', '" + Колонка.id + "')"">" + Title + "</div>"
                +    ПредметHTML
                + "  <div class=""card-footer"">"
                + "    <div class=""task-assignee"" title=""Исполнитель"">" + IconUser + Assignee + "</div>"
                +      ДедлайнHTML
                + "  </div>"
                +    КнопкиДействий
                + "</div>";
        КонецЦикла;
        
        СтолбцыHTML = СтолбцыHTML
            + "<div class=""column"" ondragover=""allowDrop(event)"" ondragleave=""dragLeave(event)"" ondrop=""drop(event, '" + Колонка.id + "')"">"
            + "  <div class=""column-header"" style=""border-top: 3px solid " + Колонка.color + """>"
            + "    <span class=""column-title"">" + Колонка.name + "</span>"
            + "    <span class=""column-badge " + Колонка.badge + """>" + Счётчик + "</span>"
            + "  </div>"
            + "  <div class=""column-body"" id=""col-" + Колонка.id + """>"
            +      ЗадачиКолонки
            + "  </div>"
            + "</div>";
    КонецЦикла;
    
    // Формирование опций селектов из реальных данных 1С
    ОпцииКонтрагентов = "<option value="""">-- Не выбран (без привязки) --</option>";
    Для Каждого К Из СписокКонтрагентов Цикл
        ОпцииКонтрагентов = ОпцииКонтрагентов + "<option value=""" + К.Ref + """>" + ЭкранироватьHTML(К.Name) + ?(ПустаяСтрока(К.INN), "", " (ИНН: " + К.INN + ")") + "</option>";
    КонецЦикла;
    
    ОпцииИсполнителей = "<option value="""">-- Текущий пользователь --</option>";
    Для Каждого Исп Из СписокИсполнителей Цикл
        ОпцииИсполнителей = ОпцииИсполнителей + "<option value=""" + Исп.Ref + """>" + ЭкранироватьHTML(Исп.Name) + "</option>";
    КонецЦикла;
    
    ОпцииЗаказов = "<option value="""">-- Без привязки к заказу --</option>";
    Для Каждого Зак Из СписокЗаказов Цикл
        ОпцииЗаказов = ОпцииЗаказов + "<option value=""" + Зак.Ref + """>" + ЭкранироватьHTML(Зак.Name) + "</option>";
    КонецЦикла;
    
    // Сборка полного документа с Drag&Drop и модальными окнами
    HTML = "<!DOCTYPE html>"
        + "<html><head><meta charset=""utf-8"">"
        + "<style>"
        + "  * { box-sizing: border-box; margin: 0; padding: 0; }"
        + "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f8fafc; color: #1e293b; padding: 14px; user-select: none; }"
        + "  .header-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; background: #ffffff; padding: 10px 16px; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }"
        + "  .header-title { font-size: 15px; font-weight: 700; color: #0f172a; display: flex; align-items: center; }"
        + "  .controls { display: flex; gap: 8px; align-items: center; }"
        + "  .search-input { padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; width: 220px; outline: none; transition: border 0.2s; }"
        + "  .search-input:focus { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.15); }"
        + "  .btn { padding: 6px 14px; font-size: 13px; font-weight: 600; border-radius: 6px; cursor: pointer; border: none; transition: all 0.2s; display: inline-flex; align-items: center; text-decoration: none; }"
        + "  .btn-primary { background: #f59e0b; color: #ffffff; }"
        + "  .btn-primary:hover { background: #d97706; }"
        + "  .btn-secondary { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }"
        + "  .btn-secondary:hover { background: #e2e8f0; color: #1e293b; }"
        + "  .btn-success { background: #10b981; color: #ffffff; }"
        + "  .btn-success:hover { background: #059669; }"
        + "  .btn-danger { background: #ef4444; color: #ffffff; }"
        + "  .btn-danger:hover { background: #dc2626; }"
        + "  .board { display: flex; gap: 14px; align-items: flex-start; overflow-x: auto; min-height: 80vh; }"
        + "  .column { flex: 1; min-width: 240px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); transition: background 0.15s, border-color 0.15s; }"
        + "  .column.drag-over { background: #fef3c7; border: 2px dashed #f59e0b; }"
        + "  .column-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; background: #fafafa; border-bottom: 1px solid #f1f5f9; border-radius: 8px 8px 0 0; }"
        + "  .column-title { font-size: 13px; font-weight: 700; color: #334155; }"
        + "  .column-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 12px; }"
        + "  .bg-blue { background: #dbeafe; color: #1d4ed8; }"
        + "  .bg-amber { background: #fef3c7; color: #b45309; }"
        + "  .bg-purple { background: #ede9fe; color: #6d28d9; }"
        + "  .bg-emerald { background: #d1fae5; color: #047857; }"
        + "  .column-body { padding: 10px; min-height: 350px; display: flex; flex-direction: column; gap: 8px; }"
        + "  .task-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); cursor: grab; transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s; }"
        + "  .task-card:hover { transform: translateY(-1px); box-shadow: 0 4px 8px rgba(0,0,0,0.07); border-color: #cbd5e1; }"
        + "  .task-card.dragging { opacity: 0.4; transform: scale(0.96); }"
        + "  .card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }"
        + "  .task-id { font-size: 11px; font-weight: 700; color: #64748b; font-family: monospace; }"
        + "  .priority-badge { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }"
        + "  .priority-high { background: #fee2e2; color: #b91c1c; }"
        + "  .priority-med { background: #fef3c7; color: #b45309; }"
        + "  .priority-low { background: #f1f5f9; color: #475569; }"
        + "  .task-title { font-size: 13px; font-weight: 600; color: #1e293b; line-height: 1.35; margin-bottom: 6px; cursor: pointer; }"
        + "  .task-title:hover { color: #2563eb; text-decoration: underline; }"
        + "  .task-subject { font-size: 11px; font-weight: 600; color: #2563eb; background: #eff6ff; padding: 3px 8px; border-radius: 4px; display: inline-flex; align-items: center; margin-bottom: 6px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }"
        + "  .card-footer { display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed #f1f5f9; padding-top: 6px; margin-top: 4px; font-size: 11px; color: #64748b; }"
        + "  .task-assignee { font-weight: 500; color: #475569; display: inline-flex; align-items: center; }"
        + "  .task-date { font-size: 11px; color: #64748b; display: inline-flex; align-items: center; }"
        + "  .task-date.overdue { color: #dc2626; font-weight: 700; }"
        + "  .card-actions { display: flex; gap: 4px; margin-top: 6px; padding-top: 4px; border-top: 1px solid #f8fafc; }"
        + "  .act-btn { font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; text-decoration: none; background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; transition: all 0.15s; }"
        + "  .act-btn:hover { background: #e2e8f0; color: #0f172a; }"
        + "  .act-primary { background: #eff6ff; color: #2563eb; border-color: #bfdbfe; }"
        + "  .act-primary:hover { background: #dbeafe; color: #1d4ed8; }"
        + "  .act-success { background: #ecfdf5; color: #059669; border-color: #a7f3d0; }"
        + "  .act-success:hover { background: #d1fae5; color: #047857; }"
        + "  .act-danger { background: #fef2f2; color: #dc2626; border-color: #fecaca; }"
        + "  .act-danger:hover { background: #fee2e2; color: #b91c1c; }"
        + "  /* Модальное окно */"
        + "  .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(15, 23, 42, 0.45); z-index: 1000; align-items: center; justify-content: center; backdrop-filter: blur(2px); }"
        + "  .modal-overlay.active { display: flex; }"
        + "  .modal-box { background: #ffffff; width: 480px; max-width: 95vw; border-radius: 10px; box-shadow: 0 10px 25px rgba(0,0,0,0.15); border: 1px solid #e2e8f0; overflow: hidden; animation: modalPop 0.18s ease-out; }"
        + "  @keyframes modalPop { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }"
        + "  .modal-header { padding: 12px 16px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }"
        + "  .modal-header h3 { font-size: 15px; font-weight: 700; color: #0f172a; }"
        + "  .modal-close { cursor: pointer; font-size: 18px; color: #94a3b8; line-height: 1; }"
        + "  .modal-close:hover { color: #0f172a; }"
        + "  .modal-body { padding: 16px; display: flex; flex-direction: column; gap: 10px; max-height: 70vh; overflow-y: auto; }"
        + "  .form-group { display: flex; flex-direction: column; gap: 4px; }"
        + "  .form-label { font-size: 12px; font-weight: 600; color: #475569; }"
        + "  .form-input, .form-select, .form-textarea { padding: 7px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; outline: none; width: 100%; box-sizing: border-box; background: #ffffff; }"
        + "  .form-input:focus, .form-select:focus, .form-textarea:focus { border-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245,158,11,0.15); }"
        + "  .modal-footer { padding: 12px 16px; background: #f8fafc; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; gap: 8px; }"
        + "</style></head><body>"
        + "<div class=""header-bar"">"
        + "  <div class=""header-title"">" + IconBoard + " Канбан-доска (1С:Предприятие) <span style=""font-size:12px; font-weight:500; color:#64748b; margin-left:8px;"">• Всего: " + ВсегоЗадач + "</span></div>"
        + "  <div class=""controls"">"
        + "    <input type='text' class=""search-input"" placeholder=""Поиск задач..."" oninput=""filterTasks(this.value)"">"
        + "    <button class=""btn btn-primary"" onclick=""openNewTaskModal()"">" + IconPlus + " Новая задача</button>"
        + "    <a href=""v8action://refresh"" class=""btn btn-secondary"">" + IconRefresh + " Обновить</a>"
        + "  </div>"
        + "</div>"
        + "<div class=""board"">"
        +    СтолбцыHTML
        + "</div>"
        + "<!-- Модальное окно просмотра / действий по карточке -->"
        + "<div id=""cardModal"" class=""modal-overlay"" onclick=""closeModalBg(event, 'cardModal')"">"
        + "  <div class=""modal-box"">"
        + "    <div class=""modal-header"">"
        + "      <h3 id=""modalCardTitle"">Задача</h3>"
        + "      <span class=""modal-close"" onclick=""closeModal('cardModal')"">&times;</span>"
        + "    </div>"
        + "    <div class=""modal-body"">"
        + "      <div class=""form-group""><div class=""form-label"">Описание:</div><div id=""modalCardDesc"" style=""font-size:13px; color:#334155; line-height:1.4; background:#f8fafc; padding:8px; border-radius:6px;"">-</div></div>"
        + "      <div class=""form-group""><div class=""form-label"">Предмет / Контрагент:</div><div id=""modalCardSubject"" style=""font-size:13px; font-weight:600; color:#2563eb;"">-</div></div>"
        + "      <div class=""form-group""><div class=""form-label"">Исполнитель:</div><div id=""modalCardAssignee"" style=""font-size:13px; color:#475569;"">-</div></div>"
        + "      <div class=""form-group""><div class=""form-label"">Срок исполнения:</div><div id=""modalCardDueDate"" style=""font-size:13px; color:#475569;"">-</div></div>"
        + "    </div>"
        + "    <div class=""modal-footer"">"
        + "      <div style=""display:flex; gap:6px;"">"
        + "        <a id=""modalBtnOpen1C"" href=""#"" class=""btn btn-primary"">📄 Открыть в 1С</a>"
        + "        <a id=""modalBtnDelete"" href=""#"" class=""btn btn-danger"" onclick=""return confirm('Удалить эту задачу в 1С?')"">🗑️ Удалить</a>"
        + "      </div>"
        + "      <button class=""btn btn-secondary"" onclick=""closeModal('cardModal')"">Закрыть</button>"
        + "    </div>"
        + "  </div>"
        + "</div>"
        + "<!-- Модальное окно создания новой задачи -->"
        + "<div id=""newTaskModal"" class=""modal-overlay"" onclick=""closeModalBg(event, 'newTaskModal')"">"
        + "  <div class=""modal-box"">"
        + "    <div class=""modal-header"">"
        + "      <h3>+ Новая задача в 1С:Предприятие</h3>"
        + "      <span class=""modal-close"" onclick=""closeModal('newTaskModal')"">&times;</span>"
        + "    </div>"
        + "    <div class=""modal-body"">"
        + "      <div class=""form-group"">"
        + "        <div class=""form-label"">Наименование / Тема задачи *</div>"
        + "        <input type=""text"" id=""newTitle"" class=""form-input"" placeholder=""Например: Подготовить договор поставки"">"
        + "      </div>"
        + "      <div class=""form-group"">"
        + "        <div class=""form-label"">Подробное описание</div>"
        + "        <textarea id=""newDesc"" class=""form-textarea"" rows=""3"" placeholder=""Укажите подробные детали и инструкции...""></textarea>"
        + "      </div>"
        + "      <div class=""form-group"">"
        + "        <div class=""form-label"">Контрагент (из справочника 1С)</div>"
        + "        <select id=""newPartnerRef"" class=""form-select"">"
        +            ОпцииКонтрагентов
        + "        </select>"
        + "      </div>"
        + "      <div class=""form-group"">"
        + "        <div class=""form-label"">Связанный заказ покупателя (из базы 1С)</div>"
        + "        <select id=""newOrderRef"" class=""form-select"">"
        +            ОпцииЗаказов
        + "        </select>"
        + "      </div>"
        + "      <div class=""form-group"">"
        + "        <div class=""form-label"">Ответственный / Исполнитель (из базы 1С)</div>"
        + "        <select id=""newAssigneeRef"" class=""form-select"">"
        +            ОпцииИсполнителей
        + "        </select>"
        + "      </div>"
        + "      <div style=""display:flex; gap:10px;"">"
        + "        <div class=""form-group"" style=""flex:1;"">"
        + "          <div class=""form-label"">Важность</div>"
        + "          <select id=""newPriority"" class=""form-select"">"
        + "            <option value=""medium"">Средняя (Обычная)</option>"
        + "            <option value=""high"">Высокая (Срочно)</option>"
        + "            <option value=""low"">Низкая</option>"
        + "          </select>"
        + "        </div>"
        + "        <div class=""form-group"" style=""flex:1;"">"
        + "          <div class=""form-label"">Срок (дней)</div>"
        + "          <input type=""number"" id=""newDays"" class=""form-input"" value=""2"" min=""1"" max=""365"">"
        + "        </div>"
        + "      </div>"
        + "    </div>"
        + "    <div class=""modal-footer"">"
        + "      <button class=""btn btn-primary"" onclick=""submitNewTask()"">💾 Создать задачу в 1С</button>"
        + "      <button class=""btn btn-secondary"" onclick=""closeModal('newTaskModal')"">Отмена</button>"
        + "    </div>"
        + "  </div>"
        + "</div>"
        + "<script>"
        + "  var selectedRef = '';"
        + "  function allowDrop(ev) { ev.preventDefault(); ev.currentTarget.classList.add('drag-over'); }"
        + "  function dragLeave(ev) { ev.currentTarget.classList.remove('drag-over'); }"
        + "  function drag(ev) {"
        + "    ev.dataTransfer.setData('text/plain', ev.target.getAttribute('data-ref'));"
        + "    ev.target.classList.add('dragging');"
        + "  }"
        + "  function drop(ev, colId) {"
        + "    ev.preventDefault();"
        + "    ev.currentTarget.classList.remove('drag-over');"
        + "    var ref = ev.dataTransfer.getData('text/plain');"
        + "    if (ref) {"
        + "      window.location.href = 'v8action://moveTask?ref=' + encodeURIComponent(ref) + '&to=' + encodeURIComponent(colId);"
        + "    }"
        + "  }"
        + "  function filterTasks(q) {"
        + "    var query = q.toLowerCase();"
        + "    var cards = document.querySelectorAll('.task-card');"
        + "    cards.forEach(function(card) {"
        + "      card.style.display = (card.textContent.toLowerCase().indexOf(query) >= 0) ? '' : 'none';"
        + "    });"
        + "  }"
        + "  function openCardModal(ref, title, desc, subject, assignee, dueDate, col) {"
        + "    selectedRef = ref;"
        + "    document.getElementById('modalCardTitle').textContent = title;"
        + "    document.getElementById('modalCardDesc').textContent = desc || 'Нет описания';"
        + "    document.getElementById('modalCardSubject').textContent = subject || 'Не указан';"
        + "    document.getElementById('modalCardAssignee').textContent = assignee || 'Администратор';"
        + "    document.getElementById('modalCardDueDate').textContent = dueDate || 'Не задан';"
        + "    document.getElementById('modalBtnOpen1C').href = 'v8action://openIn1C?ref=' + encodeURIComponent(ref);"
        + "    document.getElementById('modalBtnDelete').href = 'v8action://deleteTask?ref=' + encodeURIComponent(ref);"
        + "    document.getElementById('cardModal').classList.add('active');"
        + "  }"
        + "  function openNewTaskModal() {"
        + "    document.getElementById('newTitle').value = '';"
        + "    document.getElementById('newDesc').value = '';"
        + "    document.getElementById('newPartnerRef').value = '';"
        + "    document.getElementById('newOrderRef').value = '';"
        + "    document.getElementById('newAssigneeRef').value = '';"
        + "    document.getElementById('newTaskModal').classList.add('active');"
        + "  }"
        + "  function closeModal(id) {"
        + "    document.getElementById(id).classList.remove('active');"
        + "  }"
        + "  function closeModalBg(ev, id) {"
        + "    if (ev.target.id === id) closeModal(id);"
        + "  }"
        + "  function submitNewTask() {"
        + "    var title = document.getElementById('newTitle').value.trim();"
        + "    if (!title) { alert('Укажите наименование задачи'); return; }"
        + "    var desc = document.getElementById('newDesc').value.trim();"
        + "    var partnerRef = document.getElementById('newPartnerRef').value;"
        + "    var orderRef = document.getElementById('newOrderRef').value;"
        + "    var assigneeRef = document.getElementById('newAssigneeRef').value;"
        + "    var priority = document.getElementById('newPriority').value;"
        + "    var days = document.getElementById('newDays').value || '2';"
        + "    closeModal('newTaskModal');"
        + "    window.location.href = 'v8action://createTask?title=' + encodeURIComponent(title) + '&desc=' + encodeURIComponent(desc) + '&partnerRef=' + encodeURIComponent(partnerRef) + '&orderRef=' + encodeURIComponent(orderRef) + '&assigneeRef=' + encodeURIComponent(assigneeRef) + '&priority=' + encodeURIComponent(priority) + '&days=' + encodeURIComponent(days);"
        + "  }"
        + "</script>"
        + "</body></html>";
    
    Возврат HTML;
КонецФункции

// =============================================================================
// ОБРАБОТЧИК НАВИГАЦИИ И СОБЫТИЙ HTML (Drag&Drop, Создание, Открытие, Удаление)
// =============================================================================

&НаКлиенте
Процедура КанбанHTMLПриНажатииНаСсылку(Элемент, Адрес, СтандартнаяОбработка)
    СтандартнаяОбработка = Ложь;
    
    // Извлекаем команду из адреса
    СтрокаВызова = Адрес;
    Если СтрНачинаетсяС(Адрес, "v8action://") Тогда
        СтрокаВызова = Сред(Адрес, 12);
    ИначеЕсли СтрНачинаетсяС(Адрес, "kanban://") Тогда
        СтрокаВызова = Сред(Адрес, 10);
    ИначеЕсли СтрНачинаетсяС(Адрес, "http://kanban/") Тогда
        СтрокаВызова = Сред(Адрес, 15);
    ИначеЕсли СтрНачинаетсяС(Адрес, "https://kanban/") Тогда
        СтрокаВызова = Сред(Адрес, 16);
    КонецЕсли;
    
    ИндВопроса = СтрНайти(СтрокаВызова, "?");
    ИмяКоманды = ?(ИндВопроса > 0, Лев(СтрокаВызова, ИндВопроса - 1), СтрокаВызова);
    СтрокаПараметров = ?(ИндВопроса > 0, Сред(СтрокаВызова, ИндВопроса + 1), "");
    
    мПараметры = РазобратьПараметрыURL(СтрокаПараметров);
    
    Если ИмяКоманды = "moveTask" Тогда
        Ref = мПараметры.Получить("ref");
        ToState = мПараметры.Получить("to");
        ИзменитьСтатусЗадачи1СНаСервере(Ref, ToState);
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "openIn1C" Тогда
        Ref = мПараметры.Получить("ref");
        ОткрытьЗадачуВ1С(Ref);
        
    ИначеЕсли ИмяКоманды = "createTask" Тогда
        Title = мПараметры.Получить("title");
        Desc = мПараметры.Получить("desc");
        PartnerRef = мПараметры.Получить("partnerRef");
        OrderRef = мПараметры.Получить("orderRef");
        AssigneeRef = мПараметры.Получить("assigneeRef");
        Priority = мПараметры.Получить("priority");
        Days = Число(мПараметры.Получить("days"));
        
        СоздатьЗадачу1СРасширеннуюНаСервере(Title, Desc, PartnerRef, OrderRef, AssigneeRef, Priority, Days);
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "deleteTask" Тогда
        Ref = мПараметры.Получить("ref");
        УдалитьЗадачу1СНаСервере(Ref);
        ОбновитьДоску();
        
    ИначеЕсли ИмяКоманды = "refresh" Тогда
        ОбновитьДоску();
    КонецЕсли;
КонецПроцедуры

&НаКлиенте
Процедура ОткрытьЗадачуВ1С(RefСтрока)
    Ссылка = ПолучитьСсылкуЗадачиПоRefНаСервере(RefСтрока);
    Если ЗначениеЗаполнено(Ссылка) Тогда
        ПоказатьЗначение(, Ссылка);
    КонецЕсли;
КонецПроцедуры

&НаСервере
Функция ПолучитьСсылкуЗадачиПоRefНаСервере(RefСтрока)
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Возврат Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
    Исключение
        Возврат Неопределено;
    КонецПопытки;
КонецФункции

&НаСервере
Процедура ИзменитьСтатусЗадачи1СНаСервере(RefСтрока, ЦелеваяКолонка)
    Попытка
        УИД = Новый УникальныйИдентификатор(RefСтрока);
        Ссылка = Задачи.ЗадачаИсполнителя.ПолучитьСсылку(УИД);
        Если ЗначениеЗаполнено(Ссылка) Тогда
            Объект = Ссылка.ПолучитьОбъект();
            Если Объект <> Неопределено Тогда
                Если ЦелеваяКолонка = "todo" Тогда
                    Объект.ПринятаКИсполнению = Ложь;
                    Объект.Выполнена = Ложь;
                ИначеЕсли ЦелеваяКолонка = "in_progress" Тогда
                    Объект.ПринятаКИсполнению = Истина;
                    Объект.Выполнена = Ложь;
                    Если Не ЗначениеЗаполнено(Объект.ДатаПринятияКИсполнению) Тогда
                        Объект.ДатаПринятияКИсполнению = ТекущаяДата();
                    КонецЕсли;
                ИначеЕсли ЦелеваяКолонка = "review" Тогда
                    Объект.ПринятаКИсполнению = Истина;
                    Объект.Выполнена = Ложь;
                    Объект.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая;
                ИначеЕсли ЦелеваяКолонка = "done" Тогда
                    Объект.Выполнена = Истина;
                    Объект.ДатаИсполнения = ТекущаяДата();
                КонецЕсли;
                Объект.Записать();
            КонецЕсли;
        КонецЕсли;
    Исключение КонецПопытки;
КонецПроцедуры

&НаСервере
Функция СоздатьЗадачу1СРасширеннуюНаСервере(Заголовок, Описание, КонтрагентRef, ЗаказRef, ИсполнительRef, ВажностьСтрока, СрокДней)
    Попытка
        НоваяЗадача = Задачи.ЗадачаИсполнителя.СоздатьЗадачу();
        НоваяЗадача.Дата = ТекущаяДата();
        НоваяЗадача.Наименование = ?(ПустаяСтрока(Заголовок), "Новая задача", Заголовок);
        НоваяЗадача.Описание = Описание;
        
        Попытка
            НоваяЗадача.Автор = ПользователиИнформационнойБазы.ТекущийПользователь();
        Исключение КонецПопытки;
        
        // Привязка исполнителя
        Если Не ПустаяСтрока(ИсполнительRef) Тогда
            Попытка
                УИД = Новый УникальныйИдентификатор(ИсполнительRef);
                ИсполнительСсылка = Справочники.Пользователи.ПолучитьСсылку(УИД);
                Если ЗначениеЗаполнено(ИсполнительСсылка) Тогда
                    НоваяЗадача.Исполнитель = ИсполнительСсылка;
                КонецЕсли;
            Исключение КонецПопытки;
        КонецЕсли;
        
        // Привязка предмета (Заказ или Контрагент)
        Если Не ПустаяСтрока(ЗаказRef) Тогда
            Попытка
                УИД = Новый УникальныйИдентификатор(ЗаказRef);
                ЗаказСсылка = Документы.ЗаказПокупателя.ПолучитьСсылку(УИД);
                Если ЗначениеЗаполнено(ЗаказСсылка) Тогда
                    НоваяЗадача.Предмет = ЗаказСсылка;
                КонецЕсли;
            Исключение КонецПопытки;
        ИначеЕсли Не ПустаяСтрока(КонтрагентRef) Тогда
            Попытка
                УИД = Новый УникальныйИдентификатор(КонтрагентRef);
                КонтрагентСсылка = Справочники.Контрагенты.ПолучитьСсылку(УИД);
                Если ЗначениеЗаполнено(КонтрагентСсылка) Тогда
                    НоваяЗадача.Предмет = КонтрагентСсылка;
                КонецЕсли;
            Исключение КонецПопытки;
        КонецЕсли;
        
        // Важность
        Если ВажностьСтрока = "high" Тогда
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Высокая;
        ИначеЕсли ВажностьСтрока = "low" Тогда
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Низкая;
        Иначе
            НоваяЗадача.Важность = Перечисления.ВариантыВажностиЗадачи.Обычная;
        КонецЕсли;
        
        Срок = ?(СрокДней > 0, СрокДней, 2);
        НоваяЗадача.СрокИсполнения = ТекущаяДата() + (Срок * 86400);
        НоваяЗадача.Записать();
        
        Возврат НоваяЗадача.Ссылка;
    Исключение
        Возврат Неопределено;
    КонецПопытки;
КонецФункции

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
    Исключение КонецПопытки;
КонецПроцедуры

// =============================================================================
// ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
// =============================================================================

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
            // Базовое декодирование URI
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
