# Рецепты промптов для генераторов презентаций (Prompt Recipes)

В данном документе собраны оптимизированные шаблоны промптов для различных ИИ-инструментов, позволяющие получить презентацию максимального визуального и технического качества.

---

## 1. Рецепт для Gamma.app

**Инструкция по использованию:**
1. Откройте Gamma.app $\to$ «Create new» $\to$ «Paste in text» $\to$ «Presentation».
2. Выберите режим: **18 карточек / слайдов**, формат **16:9 widescreen**.
3. В настройках темы выберите темную палитру: *Onyx*, *Obsidian* или настройте Custom Theme:
   - Primary: `#FFB300` (1C Gold)
   - Background: `#0F172A` (Slate 900)
   - Accent: `#06B6D4` (Cyan)
   - Card Background: `#1E293B` (Slate 800)
4. Вставьте текст системного блока из [text/МАСТЕР_ПРОМПТ_ДЛЯ_ПРЕЗЕНТАЦИИ.md](../../text/МАСТЕР_ПРОМПТ_ДЛЯ_ПРЕЗЕНТАЦИИ.md).

**Дополнительная директива стиля для Gamma (AI Instructions):**
```
Generate an 18-slide executive corporate presentation in 16:9 format.
Theme: Deep dark slate (#0F172A) with semi-transparent cards (#1E293B, thin borders), accenting with 1C brand amber (#FFB300) and tech cyan (#06B6D4).
Use large bold statistic callouts for metrics (e.g. 945.6 RPS, 62/62 Tests, 150 ACID ops).
Strictly keep all mathematical formulas, legal references (115-ФЗ, ст. 395 ГК РФ), and technical terms (CFE, FastAPI, Qdrant, Action Whitelist).
Avoid filler words, keep bullet points punchy and short. Output in Russian with «...» quotation marks.
```

---

## 2. Рецепт для Claude 3.5 Sonnet / ChatGPT Canvas (Генерация через `python-pptx`)

**Инструкция по использованию:**
Отправьте модели следующий системный запрос вместе с файлом [resources/design_tokens.json](./design_tokens.json):

```markdown
Напиши законченный Python-скрипт с использованием библиотеки python-pptx, который генерирует 18-слайдовую презентацию в формате 16:9 (slide_width = Inches(13.333), slide_height = Inches(7.5)).

Требования к оформлению:
1. Задний фон каждого слайда: прямоугольник на весь слайд без контура с заливкой RGB(15, 23, 42) (#0F172A).
2. Карточки контента: скругленные прямоугольники (MSO_SHAPE.ROUNDED_RECTANGLE) с заливкой RGB(30, 41, 59) (#1E293B) и контуром RGB(51, 65, 85) (#334155) толщиной 1 pt.
3. Заголовки слайдов: размер 28 pt, белый цвет RGB(255, 255, 255), шрифт Inter / Arial.
4. Заголовки карточек: размер 16 pt, золотой цвет RGB(255, 179, 0) (#FFB300) или циан RGB(6, 182, 212).
5. Основной текст карточек: размер 13 pt, пепельно-серый цвет RGB(148, 163, 184), word_wrap = True.
6. Таблицы: строки чередуются (RGB(30, 41, 59) и RGB(22, 32, 50)), текст 12 pt, шапка с золотыми заголовками.
7. В слайды 1–18 внедри текст заметок спикера через slide.notes_slide.notes_text_frame.text.

Используй структуру слайдов и данные из приложенного мастер-промпта (62 теста, 945.6 RPS, 1.06 мс, 150 WAL транзакций, 6 бизнес-модулей, Enterprise-масштабирование, СанПиН 6.2 м2).
```

---

## 3. Рецепт для генерации иллюстраций (Midjourney / DALL-E)

Если требуется внедрить авторские графические иллюстрации на слайды:

- **Архитектурная экосистема (Слайды 1, 6, 14):**
  > `Isometric 3D blueprint of a modern high-tech enterprise data architecture, glowing data pipelines connecting 1C ERP database, FastAPI server node, and neural network vector space, glassmorphism aesthetic, dark slate background #0F172A, amber gold glowing connectors #FFB300, neon cyan data particles #06B6D4, clean corporate minimalist render, 8k resolution, octane render style --ar 16:9`

- **Безопасность и Action Whitelist (Слайд 7):**
  > `Isometric high-tech cybersecurity shield protecting an enterprise database core, green laser firewall perimeter, zero trust architecture illustration, holographic padlock, dark futuristic room, dark slate and emerald green glow, sleek premium finish --ar 16:9`

- **Роботизированный склад и автозаказ (Слайд 10):**
  > `Futuristic automated smart warehouse with automated guided vehicles, digital inventory tracking HUD overlay, supply chain logistics balance, dark tech aesthetic, amber and cyan lighting --ar 16:9`
