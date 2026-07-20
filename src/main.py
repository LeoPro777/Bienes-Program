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
from src.services import excel_service, cloudinary_service, gemini_service
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
    resultados_lista = []
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

    ya_marcado = request.query_params.get("marcado") == "true"
    log_id = None

    # Búsqueda inteligente:
    # Si el término es numérico y de menos de 5 dígitos (< 5), busca específicamente por Nº DE BIEN.
    # En caso contrario (>= 5 dígitos o texto con letras/guiones), busca en seriales y descripciones.
    if search_term:
        buscado = True
        try:
            is_bien_num = search_term.isdigit() and len(search_term) < 5
            
            if is_bien_num:
                query = {
                    "$or": [
                        {"numero_bien": search_term},
                        {"numero_bien": {"$regex": f"^{re.escape(search_term)}$", "$options": "i"}}
                    ]
                }
            else:
                query = {
                    "$or": [
                        {"serial": search_term},
                        {"serial": {"$regex": re.escape(search_term), "$options": "i"}},
                        {"descripcion": {"$regex": re.escape(search_term), "$options": "i"}}
                    ]
                }
            
            cursor_bienes = db.bienes.find(query).limit(50)
            resultados_lista = await cursor_bienes.to_list(length=50)
            
            for b in resultados_lista:
                b["_id"] = str(b["_id"])
                
            if resultados_lista:
                resultado = resultados_lista[0]
            else:
                resultado = None

            
            skip_log = request.query_params.get("skip_log") == "true"
            
            if not skip_log:
                log_doc = {
                    "valor_buscado": search_term,
                    "fecha_consulta": datetime.now(timezone.utc),
                    "coincidio": False,
                    "metadata_cliente": {
                        "ip": request.client.host,
                        "user_agent": request.headers.get("user-agent", "Desconocido")
                    }
                }
                
                try:
                    insert_result = await db.historial_consultas.insert_one(log_doc)
                    log_id = str(insert_result.inserted_id)
                except Exception as log_err:
                    logger.critical(f"FALLO CRÍTICO: No se pudo escribir en la bitácora de auditoría: {log_err}")
                    raise HTTPException(
                        status_code=500,
                        detail="Error crítico del servidor: Fallo en la persistencia del registro de auditoría. Búsqueda abortada."
                    )
            else:
                log_id = request.query_params.get("log_id")
                
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
            "resultados_lista": resultados_lista,
            "buscado": buscado,
            "error_busqueda": error_busqueda,
            "exito": exito,
            "error_msg": error,
            "autenticado": autenticado,
            "total_bienes": format_spanish_number(total_bienes),
            "total_consultas": format_spanish_number(total_consultas),
            "porcentaje_coincidencia": porcentaje_coincidencia,
            "ultima_actualizacion": ultima_actualizacion,
            "log_id": log_id,
            "ya_marcado": ya_marcado
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

@app.post("/marcar-exitoso")
async def post_marcar_exitoso(
    request: Request,
    log_id: str = Form(...),
    numero_bien: str = Form(...),
    ubicacion_encontrado: str = Form(...),
    detalles: str = Form(None),
    cedula: str = Form(None),
    nombre_apellido: str = Form(None),
    foto_numero_bien: UploadFile = File(...),
    foto_bien_completo: UploadFile = File(...)
):
    import urllib.parse
    db = database.get_db()
    
    try:
        bytes_foto_1 = await foto_numero_bien.read()
        bytes_foto_2 = await foto_bien_completo.read()
        
        if not bytes_foto_1 or not bytes_foto_2:
            msg_err = urllib.parse.quote("Debe adjuntar ambas fotografías (foto del número de bien y foto del bien completo).")
            return RedirectResponse(
                url=f"/?numero_bien={numero_bien}&error={msg_err}&skip_log=true&log_id={log_id}",
                status_code=status.HTTP_303_SEE_OTHER
            )
            
        # 1. Verificación de Foto 1 (Número de bien) mediante la API de Gemini
        es_valido_ia, detalle_ia = await gemini_service.verificar_foto_numero_bien(bytes_foto_1, numero_bien)
        if not es_valido_ia:
            logger.warning(f"Rechazo de verificación por IA para el bien {numero_bien}: {detalle_ia}")
            msg_err = urllib.parse.quote(f"Rechazado por verificación de IA: {detalle_ia}")
            return RedirectResponse(
                url=f"/?numero_bien={numero_bien}&error={msg_err}&skip_log=true&log_id={log_id}",
                status_code=status.HTTP_303_SEE_OTHER
            )
            
        # 2. Subida de fotos a Cloudinary
        url_foto_1 = None
        url_foto_2 = None
        try:
            url_foto_1 = await cloudinary_service.upload_image_bytes(bytes_foto_1, folder="bienes_etiquetas")
            url_foto_2 = await cloudinary_service.upload_image_bytes(bytes_foto_2, folder="bienes_completos")
        except Exception as cloud_err:
            logger.error(f"Error subiendo imágenes a Cloudinary: {cloud_err}")
            
        url_foto_1 = url_foto_1 or "Sin URL remota (Cloudinary sin configurar)"
        url_foto_2 = url_foto_2 or "Sin URL remota (Cloudinary sin configurar)"
        
        # 3. Guardar verificación en la bitácora de auditoría
        obj_id = ObjectId(log_id)
        update_data = {
            "coincidio": True,
            "ubicacion_encontrado": ubicacion_encontrado,
            "url_foto_numero_bien": url_foto_1,
            "url_foto_bien_completo": url_foto_2,
            "detalles_hallazgo": detalles,
            "cedula_operador": cedula or "Sin Cédula",
            "nombre_operador": nombre_apellido or "Sin Nombre",
            "fecha_verificacion": datetime.now(timezone.utc),
            "verificacion_ia": detalle_ia
        }
        
        await db.historial_consultas.update_one(
            {"_id": obj_id},
            {"$set": update_data}
        )
        
        # Actualizar estado actual del bien
        await db.bienes.update_one(
            {"numero_bien": numero_bien},
            {"$set": {
                "verificado": True,
                "ubicacion_actual": ubicacion_encontrado,
                "foto_etiqueta": url_foto_1,
                "foto_completo": url_foto_2,
                "ultimas_observaciones": detalles,
                "ultimo_operador_cedula": cedula or "Sin Cédula",
                "ultimo_operador_nombre": nombre_apellido or "Sin Nombre"
            }}
        )

        
        logger.info(f"Bien Nº {numero_bien} verificado exitosamente por IA y guardado en Cloudinary.")
        msg_exito = urllib.parse.quote(f"¡El bien Nº {numero_bien} fue verificado con éxito por la IA y registrado correctamente!")
        return RedirectResponse(
            url=f"/?numero_bien={numero_bien}&exito={msg_exito}&skip_log=true&marcado=true&log_id={log_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )
        
    except Exception as e:
        logger.error(f"Error general en verificación de bien {numero_bien}: {e}")
        msg_err = urllib.parse.quote(f"Error interno al procesar la verificación: {str(e)}")
        return RedirectResponse(
            url=f"/?numero_bien={numero_bien}&error={msg_err}&skip_log=true&log_id={log_id}",
            status_code=status.HTTP_303_SEE_OTHER
        )


@app.post("/admin/marcar-exitoso")
async def post_admin_marcar_exitoso(
    request: Request,
    log_id: str = Form(...),
    username: str = Depends(auth.get_current_admin)
):
    db = database.get_db()
    try:
        obj_id = ObjectId(log_id)
        log_entry = await db.historial_consultas.find_one({"_id": obj_id})
        if not log_entry:
            return RedirectResponse(url="/admin?error=Registro+no+encontrado", status_code=status.HTTP_303_SEE_OTHER)
            
        await db.historial_consultas.update_one(
            {"_id": obj_id},
            {"$set": {"coincidio": True}}
        )
        logger.info(f"Administrador {username} marcó consulta {log_id} ({log_entry.get('valor_buscado')}) como exitosa.")
        return RedirectResponse(
            url=f"/admin?exito=Registro+de+bien+{log_entry.get('valor_buscado')}+marcado+como+exitoso+manualmente.",
            status_code=status.HTTP_303_SEE_OTHER
        )
    except Exception as e:
        logger.error(f"Error al marcar consulta desde admin: {e}")
        return RedirectResponse(url="/admin?error=Error+al+marcar+el+registro", status_code=status.HTTP_303_SEE_OTHER)

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
