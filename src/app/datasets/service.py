from src.helpers import utils
from src.helpers.base_service import BaseService
from .dao import DatasetsDao
from bson import ObjectId
from pymongo.database import Database

class DatasetsService(BaseService):
    
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.dao = DatasetsDao(db)

    def find_all(self):
        datasets = self.dao.find(projection={"parameters": 0, "last_log": 0})
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
            models.append(model_data)

        return models

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