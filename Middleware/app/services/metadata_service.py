import json
import os
import numpy as np

METADATA_FILE = "metadata_store.json"
EMBEDDINGS_FILE = "metadata_embeddings.npy"
INDEX_LITE_FILE = "metadata_index_lite.json"

USE_ML = False
model = None
embeddings = None
metadata_index = []

try:
    from sentence_transformers import SentenceTransformer, util
    import torch
    USE_ML = True
except ImportError:
    USE_ML = False


class MetadataService:
    def __init__(self):
        self.metadata_index = []
        self.embeddings = None
        self.model = None

        if USE_ML:
            print("Loading AI model (paraphrase-multilingual-MiniLM-L12-v2)...")
            try:
                self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                print("Model loaded successfully.")
            except Exception as e:
                print(f"Error loading model: {e}")
                self.model = None
                USE_ML_FALLBACK = True
        else:
            print("Lightweight mode: sentence-transformers not available. Using precomputed embeddings.")

        self.load_metadata()

    def load_metadata(self):
        if os.path.exists(INDEX_LITE_FILE):
            try:
                with open(INDEX_LITE_FILE, "r", encoding="utf-8") as f:
                    self.metadata_index = json.load(f)
                print(f"Loaded {len(self.metadata_index)} items from lite index.")
            except Exception as e:
                print(f"Error loading lite index: {e}")
        elif os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    self.metadata_index = json.load(f)
                print(f"Loaded {len(self.metadata_index)} items from full index.")
            except Exception as e:
                print(f"Error loading metadata: {e}")

        if self.metadata_index:
            self._load_embeddings()

    def _load_embeddings(self):
        if os.path.exists(EMBEDDINGS_FILE):
            try:
                self.embeddings = np.load(EMBEDDINGS_FILE)
                print(f"Loaded precomputed embeddings: shape {self.embeddings.shape}")
                return
            except Exception as e:
                print(f"Error loading embeddings: {e}")

        if USE_ML and self.model:
            self._update_embeddings()

    def update_metadata(self, metadata_list: list):
        self.metadata_index = metadata_list
        try:
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.metadata_index, f, ensure_ascii=False, indent=2)
            print(f"Metadata updated. Count: {len(self.metadata_index)}")

            if USE_ML and self.model:
                self._update_embeddings()
        except Exception as e:
            print(f"Error saving metadata: {e}")

    def _update_embeddings(self):
        if not self.metadata_index or not self.model:
            return

        print("Updating embeddings...")

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

        texts = []
        for item in self.metadata_index:
            text = f"{item['synonym']} {item.get('name', '')}"
            object_name_clean = item.get('name', '').split('.')[-1]
            if object_name_clean in SYNONYM_MAP:
                text += " " + SYNONYM_MAP[object_name_clean]
            if "fields" in item and item["fields"]:
                field_names = " ".join([
                    f.get("synonym", f.get("name", "")) +
                    (" " + f["type"] if f.get("type") else "")
                    for f in item["fields"][:5]
                ])
                text += " " + field_names
            texts.append(text)

        self.embeddings = self.model.encode(texts, convert_to_numpy=True)

        np.save(EMBEDDINGS_FILE, self.embeddings)
        print("Embeddings updated and saved.")

    def find_top_matches(self, user_query: str, top_k: int = 5):
        if not self.metadata_index or self.embeddings is None:
            return []

        try:
            if USE_ML and self.model:
                query_embedding = self.model.encode(user_query, convert_to_numpy=True)
            else:
                return self._find_top_matches_fallback(user_query, top_k)

            scores = self._cosine_sim(query_embedding, self.embeddings)

            top_indices = np.argsort(scores)[::-1][:top_k]

            matches = []
            for idx in top_indices:
                if scores[idx] >= 0.15:
                    item = self.metadata_index[idx]
                    matches.append({
                        "name":    item["name"],
                        "synonym": item["synonym"],
                        "score":   float(scores[idx]),
                        "fields":  item.get("fields", []),
                    })

            return matches
        except Exception as e:
            print(f"Error in find_top_matches: {e}")
            return []

    def _cosine_sim(self, query_emb: np.ndarray, corpus_emb: np.ndarray) -> np.ndarray:
        query_norm = query_emb / np.linalg.norm(query_emb)
        corpus_norms = np.linalg.norm(corpus_emb, axis=1, keepdims=True)
        corpus_norms[corpus_norms == 0] = 1
        corpus_normalized = corpus_emb / corpus_norms
        return corpus_normalized @ query_norm

    def _find_top_matches_fallback(self, user_query: str, top_k: int = 5):
        query_lower = user_query.lower()
        words = set(query_lower.split())
        scored = []

        for i, item in enumerate(self.metadata_index):
            text = f"{item['synonym']} {item.get('name', '')}".lower()
            item_words = set(text.split())
            overlap = len(words & item_words)
            if overlap > 0:
                scored.append((overlap, i))

        scored.sort(key=lambda x: x[0], reverse=True)

        matches = []
        for score, idx in scored[:top_k]:
            item = self.metadata_index[idx]
            matches.append({
                "name":    item["name"],
                "synonym": item["synonym"],
                "score":   min(score / max(len(words), 1), 1.0),
                "fields":  item.get("fields", []),
            })

        return matches

    def find_semantic_match(self, user_query: str, threshold: float = 0.25, allowed_types: list = None):
        matches = self.find_top_matches(user_query, top_k=5)
        for m in matches:
            if m['score'] < threshold:
                continue
            item = next((x for x in self.metadata_index if x["name"] == m["name"]), None)
            if not item:
                continue
            if allowed_types:
                obj_type = item.get("name", "").split(".")[0]
                if obj_type not in allowed_types:
                    continue
            return item
        return None


metadata_service = MetadataService()
