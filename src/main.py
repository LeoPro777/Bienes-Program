import logging
import os
import asyncio
import urllib.request
import re
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Form, File, UploadFile, Depends, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from src import config, database, auth
from src.services import excel_service
from bson import ObjectId, errors as bson_errors

# Configuración del Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("esperanza")

def format_spanish_number(num: int) -> str:
    """Formatea un número entero con punto como separador de miles."""
    return f"{num:,}".replace(",", ".")

def format_relative_time(dt: datetime) -> str:
    """Calcula y formatea el tiempo transcurrido desde un datetime dado."""
    if not dt:
        return "Sin registros"
    now = datetime.now(timezone.utc)
    diff = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    seconds = diff.total_seconds()
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return "Hace unos instantes"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"Hace {minutes} min"
    hours = int(minutes // 60)
    if hours < 24:
        return f"Hace {hours}h {minutes % 60}min"
    days = int(hours // 24)
    return f"Hace {days} día{'s' if days > 1 else ''}"

async def keep_alive_routine():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("RENDER_EXTERNAL_URL no configurada. Saltando rutina de keep-alive.")
        return
        
    logger.info(f"Iniciando rutina de keep-alive para {url}")
    await asyncio.sleep(60)
    
    while True:
        try:
            def ping():
                try:
                    with urllib.request.urlopen(f"{url.rstrip('/')}/ping", timeout=10) as response:
                        return response.status
                except Exception as e:
                    return str(e)
                    
            status_or_err = await asyncio.to_thread(ping)
            logger.info(f"Ping keep-alive enviado a {url}/ping. Resultado: {status_or_err}")
        except Exception as e:
            logger.warning(f"Error en ping de keep-alive: {e}")
            
        await asyncio.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Conexión a Base de Datos en el inicio
    await database.init_db()
    
    # Iniciar la tarea de keep-alive en segundo plano
    keep_alive_task = asyncio.create_task(keep_alive_routine())
    
    yield
    
    # Cancelar la tarea de keep-alive ordenadamente al apagar
    keep_alive_task.cancel()
    try:
        await keep_alive_task
    except asyncio.CancelledError:
        pass
        
    # Cierre de conexión al apagar
    await database.close_db()

app = FastAPI(
    title="Sistema de Control de Bienes e Historial de Auditorías",
    lifespan=lifespan
)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurar motor de plantillas Jinja2
templates = Jinja2Templates(directory="templates")

def format_datetime_spanish(dt) -> str:
    if not dt:
        return "Fecha desconocida"
    from datetime import datetime, timezone, timedelta
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt

    caracas_tz = timezone(timedelta(hours=-4))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_local = dt.astimezone(caracas_tz)
    
    months = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]
    month_name = months[dt_local.month - 1]
    
    hour = dt_local.hour
    am_pm = "a. m." if hour < 12 else "p. m."
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12
        
    return f"{dt_local.day} {month_name} {dt_local.year}, {hour_12}:{dt_local.minute:02d} {am_pm}"

templates.env.filters["format_datetime"] = format_datetime_spanish

# Manejador de excepciones 401 para redirigir vistas al Login
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        if request.url.path.startswith("/admin"):
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": exc.detail}
            )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# ---------------------------------------------------------
# RUTAS PÚBLICAS
# ---------------------------------------------------------

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.get("/")
async def get_buscador(
    request: Request,
    numero_bien: str = None,
    q: str = None, # Soporte para ambos nombres de parámetro
    exito: str = None,
    error: str = None
):
    db = database.get_db()
    resultado = None
    buscado = False
    error_busqueda = None
    
    # Unificar los parámetros de búsqueda
    search_term = numero_bien or q
    if search_term is not None:
        search_term = search_term.strip()
        
    autenticado = auth.is_authenticated(request)
    
    # Obtener estadísticas dinámicas para las métricas del dashboard
    try:
        total_bienes = await db.bienes.count_documents({})
        total_consultas = await db.historial_consultas.count_documents({})
        
        # Calcular porcentaje de coincidencia
        if total_consultas > 0:
            exitosas = await db.historial_consultas.count_documents({"coincidio": True})
            porcentaje_coincidencia = round((exitosas / total_consultas) * 100, 1)
        else:
            porcentaje_coincidencia = 0.0
            
        # Buscar el log más reciente
        cursor_recent = db.historial_consultas.find({}, {"fecha_consulta": 1}).sort("fecha_consulta", -1).limit(1)
        recent_list = await cursor_recent.to_list(length=1)
        if recent_list:
            dt = recent_list[0].get("fecha_consulta")
            ultima_actualizacion = format_relative_time(dt)
        else:
            ultima_actualizacion = "Sin registros"
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}")
        total_bienes = 0
        total_consultas = 0
        porcentaje_coincidencia = 0.0
        ultima_actualizacion = "Desconocida"

    # Procesar búsqueda
    if search_term:
        buscado = True
        try:
            # Consulta exacta contra la colección bienes
            resultado = await db.bienes.find_one({"numero_bien": search_term})
            coincidio = (resultado is not None)
            
            # Registrar auditoría obligatoriamente en segundo plano
            log_doc = {
                "valor_buscado": search_term,
                "fecha_consulta": datetime.now(timezone.utc),
                "coincidio": coincidio,
                "metadata_cliente": {
                    "ip": request.client.host,
                    "user_agent": request.headers.get("user-agent", "Desconocido")
                }
            }
            
            # VETO-01: Prohibido omitir el guardado en el historial bajo cualquier condición
            try:
                await db.historial_consultas.insert_one(log_doc)
            except Exception as log_err:
                logger.critical(f"FALLO CRÍTICO: No se pudo escribir en la bitácora de auditoría: {log_err}")
                raise HTTPException(
                    status_code=500,
                    detail="Error crítico del servidor: Fallo en la persistencia del registro de auditoría. Búsqueda abortada."
                )
                
            # Formatear ID a string
            if resultado:
                resultado["_id"] = str(resultado["_id"])
                
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error al realizar la búsqueda del bien: {e}")
            error_busqueda = "Ocurrió un error en el servidor al procesar la consulta."

    return templates.TemplateResponse(
        "buscador.html",
        {
            "request": request,
            "numero_bien": search_term,
            "resultado": resultado,
            "buscado": buscado,
            "error_busqueda": error_busqueda,
            "exito": exito,
            "error_msg": error,
            "autenticado": autenticado,
            "total_bienes": format_spanish_number(total_bienes),
            "total_consultas": format_spanish_number(total_consultas),
            "porcentaje_coincidencia": porcentaje_coincidencia,
            "ultima_actualizacion": ultima_actualizacion
        }
    )

@app.get("/login")
async def get_login(request: Request):
    if auth.is_authenticated(request):
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def post_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        token = auth.create_access_token(username)
        response = RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        is_secure = request.url.scheme == "https"
        response.set_cookie(
            key=auth.COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=6 * 60 * 60,
            expires=6 * 60 * 60,
            samesite="strict",
            secure=is_secure
        )
        logger.info(f"Sesión iniciada con éxito para el administrador: {username}")
        return response
    
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Credenciales inválidas. Intente de nuevo."}
    )

@app.post("/logout")
async def post_logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=auth.COOKIE_NAME)
    logger.info("Sesión cerrada correctamente.")
    return response

# ---------------------------------------------------------
# RUTAS DE ADMINISTRACIÓN (PROTEGIDAS)
# ---------------------------------------------------------

async def obtener_datos_admin():
    db = database.get_db()
    
    total_bienes = await db.bienes.count_documents({})
    total_consultas = await db.historial_consultas.count_documents({})
    consultas_fallidas = await db.historial_consultas.count_documents({"coincidio": False})
    consultas_exitosas = await db.historial_consultas.count_documents({"coincidio": True})
    
    # Bitácora cronológica descendente (limitada a las últimas 150 consultas)
    historial = []
    cursor = db.historial_consultas.find({}).sort("fecha_consulta", -1).limit(150)
    async for log in cursor:
        log["_id"] = str(log["_id"])
        historial.append(log)
        
    return {
        "total_bienes": total_bienes,
        "total_consultas": total_consultas,
        "consultas_fallidas": consultas_fallidas,
        "consultas_exitosas": consultas_exitosas,
        "historial": historial
    }

@app.get("/admin")
async def get_admin(
    request: Request,
    exito: str = None,
    error: str = None,
    username: str = Depends(auth.get_current_admin)
):
    stats = await obtener_datos_admin()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": exito,
            "error_msg": error,
            "autenticado": True,
            **stats
        }
    )

@app.post("/admin/vaciar-bienes")
async def post_vaciar_bienes(
    request: Request,
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    try:
        # RN-02: Solo eliminamos los bienes, el historial de consultas es estrictamente Append-Only
        res = await db.bienes.delete_many({})
        logger.info(f"El operador '{username}' vació el inventario de bienes. Registros eliminados: {res.deleted_count}.")
        return RedirectResponse(
            url=f"/admin?exito=Se+eliminaron+exitosamente+{res.deleted_count}+bienes+del+inventario.+El+historial+de+auditoria+permanece+intacto.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        logger.error(f"Error al vaciar bienes del inventario: {e}")
        return RedirectResponse(url="/admin?error=Error+interno+al+vaciar+el+inventario", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/cargar-bienes")
async def post_cargar_bienes(
    request: Request,
    file: UploadFile = File(...),
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    exito_msg = None
    errores_list = None
    rejected_count = 0
    
    try:
        file_bytes = await file.read()
        filename = file.filename
        
        registros, errores_list = await excel_service.procesar_archivo(file_bytes, filename)
        
        if errores_list:
            rejected_count = sum(1 for err in errores_list if err.get("fila", 0) > 0)
            
        inserted_count = 0
        if registros:
            # Operación atómica de inserción por lotes
            result = await db.bienes.insert_many(registros)
            inserted_count = len(result.inserted_ids)
            exito_msg = f"Se cargaron exitosamente {inserted_count} bienes."
            if rejected_count > 0:
                exito_msg += f" Se rechazaron {rejected_count} filas por inconsistencias."
            logger.info(f"Carga de inventario: {inserted_count} bienes insertados, {rejected_count} rechazados por operador '{username}'.")
        elif rejected_count > 0:
            logger.info(f"Carga de inventario: 0 bienes insertados, {rejected_count} rechazados por operador '{username}'.")
        
        if not registros and not errores_list:
            errores_list = [{"fila": 0, "error": "El archivo cargado no contiene filas procesables."}]
            
    except Exception as e:
        logger.error(f"Error al procesar la carga masiva: {e}")
        errores_list = [{"fila": 0, "error": f"Error interno del servidor al procesar el archivo: {str(e)}"}]
        
    stats = await obtener_datos_admin()
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "username": username,
            "exito": exito_msg,
            "errores": errores_list,
            "rejected_count": rejected_count,
            "autenticado": True,
            **stats
        }
    )

@app.get("/admin/descargar-datos")
async def get_descargar_datos(
    username: str = Depends(auth.get_current_admin)
):
    import json
    from fastapi.responses import StreamingResponse
    from bson import json_util
    import io
    
    db = database.get_db()
    try:
        cursor = db.bienes.find({}).sort("item", 1)
        bienes = await cursor.to_list(length=None)
        
        data_str = json_util.dumps(bienes, indent=2, ensure_ascii=False)
        bio = io.BytesIO(data_str.encode("utf-8"))
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bienes_backup_{timestamp}.json"
        
        logger.info(f"Base de datos de bienes exportada y descargada por {username}.")
        return StreamingResponse(
            bio,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Error al descargar la base de datos de bienes: {e}")
        return RedirectResponse(url=f"/admin?error=Error+al+descargar+los+datos", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/restaurar-datos")
async def post_restaurar_datos(
    request: Request,
    backup_file: UploadFile = File(...),
    username: str = Depends(auth.get_current_admin)
):
    import urllib.parse
    from bson import json_util
    db = database.get_db()
    
    try:
        content = await backup_file.read()
        try:
            data = json_util.loads(content.decode("utf-8"))
        except Exception as parse_err:
            logger.warning(f"Error parseando archivo de respaldo por {username}: {parse_err}")
            return RedirectResponse(
                url=f"/admin?error=Error+de+formato+JSON:+{urllib.parse.quote(str(parse_err))}",
                status_code=status.HTTP_303_SEE_OTHER
            )
            
        if not isinstance(data, list):
            if isinstance(data, dict):
                data = [data]
            else:
                return RedirectResponse(
                    url="/admin?error=El+archivo+debe+contener+una+lista+de+bienes.",
                    status_code=status.HTTP_303_SEE_OTHER
                )
                
        if len(data) == 0:
            return RedirectResponse(
                url="/admin?error=El+archivo+de+respaldo+está+vacío.",
                status_code=status.HTTP_303_SEE_OTHER
            )
            
        # Vaciar bienes e importar los nuevos. No tocamos el historial de consultas para resguardar la auditoría.
        delete_result = await db.bienes.delete_many({})
        insert_result = await db.bienes.insert_many(data)
        
        logger.info(f"Restauración de backup de bienes exitosa: {delete_result.deleted_count} eliminados, {len(insert_result.inserted_ids)} restaurados por {username}.")
        
        return RedirectResponse(
            url=f"/admin?exito=Base+de+datos+de+bienes+restaurada+con+éxito.+Se+cargaron+{len(insert_result.inserted_ids)}+bienes.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        logger.error(f"Error al restaurar base de datos de bienes: {e}")
        return RedirectResponse(
            url=f"/admin?error=Error+interno+al+restaurar+la+base+de+datos:+{urllib.parse.quote(str(e))}",
            status_code=status.HTTP_303_SEE_OTHER
        )
