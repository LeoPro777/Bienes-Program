import logging
from motor.motor_asyncio import AsyncIOMotorClient
from src import config

logger = logging.getLogger(__name__)

# Instancias globales de base de datos
client = None
db = None

def get_db():
    return db

async def init_db():
    global client, db
    logger.info("Conectando a MongoDB...")
    client = AsyncIOMotorClient(config.MONGODB_URI)
    
    # Extraer el nombre de la base de datos de la URI, por defecto 'esperanza'
    db_name = "esperanza"
    try:
        # Separar por '/'
        parts = config.MONGODB_URI.split("/")
        if len(parts) > 3:
            potential_db = parts[3].split("?")[0]
            if potential_db:
                db_name = potential_db
    except Exception:
        pass
        
    db = client[db_name]
    logger.info(f"Base de datos configurada: {db_name}")
    
    # Configuración de índices requeridos
    try:
        # 1. Índice Único en la colección de bienes por numero_bien
        await db.bienes.create_index(
            [("numero_bien", 1)],
            unique=True,
            name="numero_bien_unique_index"
        )
        logger.info("Índice único 'numero_bien_unique_index' creado/verificado en la colección de bienes.")
        
        # 2. Índice Cronológico en la colección de historial_consultas
        await db.historial_consultas.create_index(
            [("fecha_consulta", -1)],
            name="fecha_consulta_index"
        )
        logger.info("Índice cronológico 'fecha_consulta_index' creado/verificado en la colección de historial_consultas.")
    except Exception as e:
        logger.error(f"Error al verificar/crear índices en MongoDB: {e}")

async def close_db():
    global client
    if client:
        client.close()
        logger.info("Conexión a MongoDB cerrada de manera ordenada.")
