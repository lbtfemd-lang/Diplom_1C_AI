import json
import logging
import os
import numpy as np

logger = logging.getLogger(__name__)

_BASE_DIR = os.getenv("METADATA_DATA_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
METADATA_FILE = os.path.join(_BASE_DIR, "metadata_store.json")
EMBEDDINGS_FILE = os.path.join(_BASE_DIR, "metadata_embeddings.npy")
INDEX_LITE_FILE = os.path.join(_BASE_DIR, "metadata_index_lite.json")

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

        if USE_ML and os.getenv("METADATA_ML_ENABLED", "true").lower() == "true":
            logger.info("Loading AI model (paraphrase-multilingual-MiniLM-L12-v2)...")
            try:
                self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("Model loaded successfully.")
            except Exception as e:
                logger.error("Error loading model: %s", e)
                self.model = None
                USE_ML_FALLBACK = True
        else:
            logger.info("Lightweight mode: sentence-transformers not available. Using precomputed embeddings.")

        self.load_metadata()

    def load_metadata(self):
        if os.path.exists(INDEX_LITE_FILE):
            try:
                with open(INDEX_LITE_FILE, "r", encoding="utf-8") as f:
                    self.metadata_index = json.load(f)
                logger.info("Loaded %d items from lite index.", len(self.metadata_index))
            except Exception as e:
                logger.error("Error loading lite index: %s", e)
        elif os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    self.metadata_index = json.load(f)
                logger.info("Loaded %d items from full index.", len(self.metadata_index))
            except Exception as e:
                logger.error("Error loading metadata: %s", e)

        if self.metadata_index:
            self._load_embeddings()

    def _load_embeddings(self):
        if os.path.exists(EMBEDDINGS_FILE):
            try:
                self.embeddings = np.load(EMBEDDINGS_FILE)
                logger.info("Loaded precomputed embeddings: shape %s", self.embeddings.shape)
                return
            except Exception as e:
                logger.error("Error loading embeddings: %s", e)

        if USE_ML and self.model:
            self._update_embeddings()

    def update_metadata(self, metadata_list: list):
        self.metadata_index = metadata_list
        try:
            with open(METADATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.metadata_index, f, ensure_ascii=False, indent=2)
            logger.info("Metadata updated. Count: %d", len(self.metadata_index))

            if USE_ML and self.model:
                self._update_embeddings()
        except Exception as e:
            logger.error("Error saving metadata: %s", e)

    def _update_embeddings(self):
        if not self.metadata_index or not self.model:
            return

        logger.info("Updating embeddings...")

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
        logger.info("Embeddings updated and saved.")

    def find_top_matches(self, user_query: str, top_k: int = 5):
        if not self.metadata_index:
            return []

        if USE_ML and self.model and self.embeddings is not None:
            try:
                query_embedding = self.model.encode(user_query, convert_to_numpy=True)
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
                logger.error("Error in find_top_matches: %s", e)

        return self._find_top_matches_fallback(user_query, top_k)

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
