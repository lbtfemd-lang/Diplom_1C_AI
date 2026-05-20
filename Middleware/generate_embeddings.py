"""
Локальный скрипт для генерации предрасчётанных эмбеддингов.
Запускается на ПК разработчика (где есть sentence-transformers).
Результат: metadata_embeddings.npy + metadata_index_lite.json — для загрузки на сервер.
"""
import os
import json
import numpy as np

METADATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_store.json")
EMBEDDINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_embeddings.npy")
INDEX_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_index_lite.json")

SYNONYM_MAP = {
    "Контрагенты":          "Клиент Покупатель Поставщик Заказчик Юрлицо Партнёр Дебитор",
    "Номенклатура":         "Товар Услуга Продукция Материал Запас Артикул SKU",
    "ЗаказПокупателя":      "Заказ клиента Заявка Счет на оплату Продажа Сделка",
    "РасходнаяНакладная":   "Реализация Отгрузка ТОРГ-12 Накладная Продажа",
    "ПриходнаяНакладная":   "Поступление Закупка Приход Приёмка",
    "СчетНаОплату":         "Счет-фактура Выставить счет Invoice",
    "ПоступлениеНаСчет":    "Оплата от клиента Деньги на счет Входящий платеж",
    "СписаниеСоСчета":      "Оплата поставщику Исходящий платеж Расход денег",
    "Продажи":              "Выручка Прибыль Оборот Реализация (отчет)",
    "Сотрудники":           "Персонал Работник Штат HR Кадры",
    "Склады":               "Склад Кладовая Хранилище Магазин",
    "БанковскиеСчета":      "Банк Расчётный счёт IBAN Реквизиты",
    "Валюты":               "Курс Валюта Доллар Евро USD EUR",
    "ПеремещениеТоваров":   "Перемещение Переброска Внутреннее перемещение Склад-Склад",
    "КлассификаторЕдиницИзмерения": "Единица Шт кг м л ЕдИзм",
}


def generate():
    if not os.path.exists(METADATA_FILE):
        print(f"ERROR: {METADATA_FILE} not found. Run 1C metadata export first.")
        return

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata_index = json.load(f)

    print(f"Loaded {len(metadata_index)} items from metadata_store.json")

    try:
        from sentence_transformers import SentenceTransformer
        print("Loading model paraphrase-multilingual-MiniLM-L12-v2...")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    except ImportError:
        print("ERROR: sentence-transformers not installed. Install with: pip install sentence-transformers")
        return

    texts = []
    for item in metadata_index:
        text = f"{item['synonym']} {item.get('name', '')}"
        object_name_clean = item.get('name', '').split('.')[-1]
        if object_name_clean in SYNONYM_MAP:
            text += " " + SYNONYM_MAP[object_name_clean]
        if "fields" in item and item["fields"]:
            field_names = " ".join([
                f.get("synonym", f.get("name", ""))
                for f in item["fields"][:5]
            ])
            text += " " + field_names
        texts.append(text)

    print("Computing embeddings...")
    embeddings = model.encode(texts, convert_to_numpy=True)
    print(f"Embeddings shape: {embeddings.shape}")

    np.save(EMBEDDINGS_FILE, embeddings)
    print(f"Saved embeddings to {EMBEDDINGS_FILE}")

    lite_index = []
    for item in metadata_index:
        lite_index.append({
            "name": item["name"],
            "synonym": item["synonym"],
            "fields": item.get("fields", []),
        })

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(lite_index, f, ensure_ascii=False, indent=2)
    print(f"Saved lite index to {INDEX_FILE}")

    print("Done! Copy these files to the server:")
    print(f"  - {EMBEDDINGS_FILE}")
    print(f"  - {INDEX_FILE}")


if __name__ == "__main__":
    generate()
