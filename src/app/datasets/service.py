from src.helpers import utils
from src.helpers.base_service import BaseService
from .dao import DatasetsDao
from bson import ObjectId
from pymongo.database import Database
import random

class DatasetsService(BaseService):
    
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.dao = DatasetsDao(db)

    def find_all(self):
        datasets = self.dao.find({"status": {"$ne": "completed"}}, projection={"parameters": 0, "last_log": 0})
        models = []
        for dataset in datasets:
            model_data = {}
            if dataset.get("model"):
                model_data = self.dao.serialize(
                    self.dao.db["models"].find_one(
                        {"_id": ObjectId(dataset.get("model"))},
                        projection={"mapper": 0, "configuration": 0, "entities": 0, "labels": 0, "randomizers": 0}
                    )
                )

            if dataset.get("created_by"):
                model_data["created_by"] = self.dao.serialize(
                    self.dao.db["users"].find_one(
                        {"_id": ObjectId(dataset.get("created_by"))},
                        projection={"password": 0, "apikey": 0, "role": 0}
                    )
                )

            model_data["dataset"] = str(dataset.get("_id"))
            model_data["status"] = dataset.get("status", "")
            model_data["version"] = dataset.get("version", "")
            model_data["progress"] = dataset.get("progress", None)
            models.append(model_data)

        return models
    
    def find_examples(self, dataset_id: str, size: int = 10):
        dataset = self.get_document(id=dataset_id)
        model = self.dao.db["models"].find_one({"_id": ObjectId(dataset.get("model"))})

        dataset_data = list(self.dao.db["datasets_data"].find({"dataset": ObjectId(dataset_id)}))
    
        ddselected = random.choices(dataset_data, k=size)
        entities = model.get("entities", []) if model else []

        examples = []
        for d in ddselected:
            data = d.get("data", {})
            text = data.get("text", "")

            example_entities = []
            for s, e, k in data.get("entities", []):
                key = entities[k]
                example_entities.append({
                    "start": s,
                    "end": e,
                    "key": key
                })
            
            examples.append({
                "text": text,
                "entities": example_entities
            })
        
        return examples

    def add_data(self, dataset_id: str, data: dict):
        return self.db["datasets_data"].insert_one({
            "dataset": ObjectId(dataset_id),
            "data": data,
            "created_at": utils.get_current_time()
        })

    def update_status(self, dataset_id: str, status: str):
        return self.dao.update_one(
            {"_id": ObjectId(dataset_id)},
            {"status": status}
        )

    def train_dataset(self, dataset_id: str, user_id: str, parameters: dict):
        self.update_status(dataset_id, "ready")
        self.dao.update_one(
            {"_id": ObjectId(dataset_id)},
            {"parameters": parameters, "trained_by": ObjectId(user_id)}
        )
        return {"status": "training started"}