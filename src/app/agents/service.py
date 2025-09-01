from src.app.agents.dao import AgentsDao
from src.helpers.base_service import BaseService
from pymongo.database import Database
from bson import ObjectId


class AgentsService(BaseService):

    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.dao = AgentsDao(self.db)

    def find_all(self):
        agents = self.dao.find(projection={"path": 0})
        models = []
        for agent in agents:
            model_data = {}
            if agent.get("model"):
                model_data = self.dao.serialize(
                    self.dao.db["models"].find_one(
                        {"_id": ObjectId(agent.get("model"))},
                        projection={"mapper": 0, "configuration": 0, "entities": 0, "labels": 0, "randomizers": 0}
                    )
                )

            if agent.get("created_by"):
                model_data["created_by"] = self.dao.serialize(
                    self.dao.db["users"].find_one(
                        {"_id": ObjectId(agent.get("created_by"))},
                        projection={"password": 0, "apikey": 0, "role": 0}
                    )
                )

            model_data["agent"] = str(agent.get("_id"))
            model_data["status"] = agent.get("status", "")
            model_data["version"] = agent.get("version", "")
            models.append(model_data)

        return models