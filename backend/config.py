import os
from dotenv import load_dotenv
load_dotenv()

SECRET_KEY       = os.getenv("SECRET_KEY", "change_me")
MONGO_URI        = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME    = os.getenv("MONGO_DB_NAME", "caretrust_ai")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "caretrust-index")
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY", "")
BACKEND_URL      = os.getenv("BACKEND_URL", "http://localhost:8000")
