import os
from dotenv import load_dotenv

# Cargar variables desde el archivo .env si existe
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/esperanza")
JWT_SECRET = os.getenv("JWT_SECRET", "default_secret_key_change_me_in_production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
PORT = int(os.getenv("PORT", "8000"))

# Cloudinary
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
