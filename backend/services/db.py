from pymongo import MongoClient
from backend.config import MONGO_URI, MONGO_DB_NAME

_client = None
_db     = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db     = _client[MONGO_DB_NAME]
    return _db
