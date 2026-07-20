import logging
import io
import cloudinary
import cloudinary.uploader
from src import config

logger = logging.getLogger(__name__)

_configured = False

def init_cloudinary():
    global _configured
    if config.CLOUDINARY_CLOUD_NAME and config.CLOUDINARY_CLOUD_NAME != "tu_cloud_name":
        cloudinary.config(
            cloud_name=config.CLOUDINARY_CLOUD_NAME,
            api_key=config.CLOUDINARY_API_KEY,
            api_secret=config.CLOUDINARY_API_SECRET,
            secure=True
        )
        _configured = True

async def upload_image_bytes(image_bytes: bytes, folder: str = "bienes") -> str | None:
    """
    Subes la imagen en bytes a Cloudinary y retorna la URL pública (secure_url).
    """
    if not image_bytes:
        return None
        
    init_cloudinary()
    
    if not config.CLOUDINARY_CLOUD_NAME or config.CLOUDINARY_CLOUD_NAME == "tu_cloud_name":
        logger.warning("Cloudinary no configurado con credenciales válidas en .env. Omitiendo subida remota.")
        return None

    try:
        # Se suben los bytes directamente a Cloudinary mediante un buffer en memoria
        buffer = io.BytesIO(image_bytes)
        result = cloudinary.uploader.upload(
            buffer,
            folder=folder,
            resource_type="image"
        )
        url = result.get("secure_url")
        logger.info(f"Imagen subida exitosamente a Cloudinary: {url}")
        return url
    except Exception as e:
        logger.error(f"Error al subir la imagen a Cloudinary: {e}")
        raise RuntimeError(f"Error en el servicio de imágenes Cloudinary: {str(e)}")
