from typing import Any, Dict
from src.app.users.dao import UsersDao
from pymongo.database import Database
from bson.objectid import ObjectId
from src.helpers.base_service import BaseService
from src.helpers.avatar import save_avatar, generate_avatar
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity
import os

from src.helpers import utils

class AuthService(BaseService):

    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self.dao = UsersDao(self.db)

    def register(self, data: Dict[str, Any]) -> Dict[str, Any]:
        email = (data.get("email") or "").strip().lower()

        if not email or "@" not in email:
            raise ValueError("Email invalide")

        if self.document_exists({"email": email}):
            raise ValueError("Email déjà utilisé")

        if not data.get("firstname") or not data.get("lastname"):
            raise ValueError("First name et last name requis")
        
        if not data.get("password"):
            raise ValueError("Password requis")

        apikey = utils.generate_apikey()
        user = {
            "email": email,
            "firstname": data["firstname"],
            "lastname": data["lastname"],
            "apikey": apikey,
            "password": utils.hash_password(data["password"], apikey),
            "role": "user",
        }

        self.dao.insert_one(user)

        save_avatar(
            generate_avatar(email, 800),
            os.path.join("src", "public", "avatars"),
            f"{user['_id']}.png"
        )

        token, refresh = self.token(user=user)
        user.pop("password", None)

        return {"token": token, "refresh_token": refresh, "user": user}

    def login(self, data: Dict[str, Any]) -> Dict[str, Any]:
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not email or not password:
            raise ValueError("Email et password requis")

        user = self.dao.find_one({"email": email})
        if not user or not utils.verify_password(password, user["password"], user["apikey"]):
            raise ValueError("Email ou mot de passe invalide")

        user.pop("password", None)

        token, refresh = self.token(user=user)

        return {"token": token, "refresh_token": refresh, "user": user}
    
    def token(self, *, user_id: str = None, user: Dict[str, Any]) -> tuple:
        if not user:
            user = self.get_document(id=user_id)
        
        token = create_access_token(identity=str(user["_id"]), additional_claims={"role": user.get("role", 1)})
        refresh = create_refresh_token(identity=str(user["_id"]))

        return (token, refresh)
    
    def login_token(self, user_id: str) -> Dict[str, Any]:
        user = self.get_document(id=user_id)
        user.pop("password", None)
        token, refresh = self.token(user=user)
        return {"token": token, "refresh_token": refresh, "user": user}

    def email_exists(self, email: str) -> bool:
        email = email.strip().lower()
        return self.document_exists({"email": email})