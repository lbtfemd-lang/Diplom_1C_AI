"""
Inject inferred field types into metadata_index_lite.json,
save as metadata_store.json + lite index, then regenerate embeddings.
"""
import os
import json
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
LITE_FILE = os.path.join(BASE, "metadata_index_lite.json")
STORE_FILE = os.path.join(BASE, "metadata_store.json")
EMB_FILE = os.path.join(BASE, "metadata_embeddings.npy")

BOOLEAN_FIELDS = {
    "Зашифрован", "ПодписанЭП", "ПометкаУдаления", "Проведен", "Оплачен",
    "ОтраженВУчете", "Сторно", "Черновик", "Архивный", "Используется",
    "Активность", "Видимость", "Доступность", "Обязательный",
}

DATE_FIELDS = {"Дата", "ДатаРождения", "ДатаСоздания", "ДатаМодификации",
               "ДатаНачала", "ДатаОкончания", "ДатаЗаема", "ДатаПроведения",
               "Период", "ДатаОтгрузки", "ДатаПоступления", "ДатаОплаты"}

NUMBER_FIELDS = {"Сумма", "Цена", "Количество", "Остаток", "Баланс",
                 "Курс", "Вес", "Объем", "Длина", "Ширина", "Высота",
                 "КоличествоУпаковок", "СуммаНДС", "СуммаСкидки", "СуммаДокумента"}

STRING_FIELDS = {"Код", "Наименование", "ФИО", "ИНН", "КПП", "ОГРН",
                 "Адрес", "Телефон", "Email", "Почта", "Сайт",
                 "Номер", "НомерДокумента", "РегистрационныйНомер"}

REFERENCE_SUFFIXES = ("Ссылка", "Владелец", "Родитель", "Организация",
                      "Контрагент", "Номенклатура", "Склад", "Ответственный",
                      "Автор", "Изменил", "Менеджер", "ФизическоеЛицо",
                      "ЕдиницаИзмерения", "Валюта", "Договор", "Счет",
                      "СтатьяДвиженияДенежныхСредств", "СтатьяЗатрат",
                      "Подразделение", "Должность", "Сотрудник", "Касса",
                      "БанковскийСчет", "ЭквайринговыйТерминал", "КассаККМ",
                      "Основание", "ДокументОснование", "Заказ", "ЗаказПокупателя",
                      "Партнер", "КонтактноеЛицо", "Характеристика", "Серия",
                      "Назначение", "Поставщик", "Покупатель", "Грузоотправитель",
                      "Грузополучатель", "Банк", "КорреспондентскийСчет",
                      "МестоХранения", "Ячейка", "Зона", "Группа", "Вид")


def infer_type(field_name, parent_name):
    """Infer 1C field type from field name and parent object name."""
    name = field_name
    parent = parent_name
    parent_kind = parent.split(".")[0] if "." in parent else ""
    parent_short = parent.split(".")[-1] if "." in parent else parent

    # Boolean
    if name in BOOLEAN_FIELDS or any(name.endswith(s) for s in ("Проведен", "Оплачен", "Сторно", "Черновик", "Архивный", "Зашифрован", "ПодписанЭП")):
        return "Булево"

    # Date
    if name in DATE_FIELDS or name.startswith("Дата"):
        return "Дата"

    # Number
    if name in NUMBER_FIELDS or any(name.startswith(p) for p in ("Сумма", "Цена", "Количество", "Остаток", "Баланс", "Курс", "Вес", "Объем")):
        return "Число(15, 2)"

    # String specific
    if name in STRING_FIELDS:
        if name in ("Наименование", "ФИО"):
            return "Строка(150)"
        if name in ("Адрес", "Телефон", "Email", "Почта", "Сайт"):
            return "Строка(250)"
        if name == "Код":
            return "Строка(9)"
        return "Строка(100)"

    # Description / comment
    if name in ("Описание", "Комментарий", "Примечание", "ДополнительнаяИнформация"):
        return "Строка(0)"

    # Reference
    if name.endswith("Ссылка"):
        ref_type = name[:-6]  # remove 'Ссылка'
        if ref_type:
            return f"СправочникСсылка.{ref_type}"
        return "СправочникСсылка"

    if any(name.endswith(suffix) for suffix in REFERENCE_SUFFIXES):
        for suffix in REFERENCE_SUFFIXES:
            if name.endswith(suffix):
                if suffix in ("Владелец", "Родитель"):
                    # Often same kind as parent
                    return f"{parent_kind}Ссылка.{parent_short}"
                return f"СправочникСсылка.{suffix}"

    if name.startswith("Ссылка") or name.startswith("Владелец") or name.startswith("Родитель"):
        return f"{parent_kind}Ссылка.{parent_short}"

    # Default
    return "Строка(100)"


def process():
    print("Loading metadata_index_lite.json...")
    with open(LITE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} items.")

    enriched = []
    for item in data:
        new_item = {
            "name": item["name"],
            "synonym": item["synonym"],
            "fields": [],
        }
        for field in item.get("fields", []):
            field_type = infer_type(field["name"], item["name"])
            new_item["fields"].append({
                "name": field["name"],
                "synonym": field.get("synonym", field["name"]),
                "type": field_type,
            })
        enriched.append(new_item)

    # Save full store
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"Saved enriched metadata to {STORE_FILE}")

    # Save lite index (same structure, just types added)
    with open(LITE_FILE, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"Saved lite index to {LITE_FILE}")

    # Regenerate embeddings
    try:
        from sentence_transformers import SentenceTransformer
        print("Loading model paraphrase-multilingual-MiniLM-L12-v2...")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        print("ERROR: sentence-transformers not installed. Cannot regenerate embeddings.")
        print("Install with: python -m pip install sentence-transformers")
        return

    texts = []
    for item in enriched:
        text = f"{item['synonym']} {item['name']}"
        if item.get("fields"):
            field_texts = []
            for f in item["fields"][:7]:
                field_texts.append(f"{f['synonym']}[{f['type']}]")
            text += " " + " ".join(field_texts)
        texts.append(text)

    print(f"Encoding {len(texts)} items...")
    embeddings = model.encode(texts, convert_to_numpy=True)
    np.save(EMB_FILE, embeddings)
    print(f"Saved embeddings: {embeddings.shape} -> {EMB_FILE}")
    print("Done!")


if __name__ == "__main__":
    process()
