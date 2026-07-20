import io
from datetime import datetime, timezone
import csv
import openpyxl
import logging
from typing import List, Dict, Tuple, Any
from src import database

logger = logging.getLogger(__name__)

def clean_string(val: Any) -> str | None:
    """Limpia cadenas, quitando espacios en blanco y manejando None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None

def clean_numero_bien(val: Any) -> str | None:
    """Sanitiza el número de bien. Evita decimales agregados por Excel (ej: '8.0' -> '8')."""
    if val is None:
        return None
    s = str(val).strip()
    # Si viene como float en string ("8.0"), remover el decimal
    if s.endswith(".0"):
        s = s[:-2]
    return s if s else None

def clean_item_correlativo(val: Any) -> int | None:
    """Convierte el valor de ITEM a un número entero o retorna None si no es válido."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return int(s)
    except ValueError:
        return None

def procesar_csv(file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], str | None]:
    """Procesa un archivo CSV en memoria."""
    try:
        content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            content = file_bytes.decode("latin-1")
        except Exception as e:
            return [], [], f"Error de codificación: {str(e)}"
            
    f = io.StringIO(content)
    reader = csv.reader(f)
    try:
        rows = list(reader)
    except Exception as e:
        return [], [], f"Error al leer el CSV: {str(e)}"
        
    if not rows:
        return [], [], "El archivo CSV está vacío."
        
    headers = [str(h).strip().lower() for h in rows[0] if h is not None]
    data_rows = []
    
    for r in rows[1:]:
        if not any(r): # Ignorar filas vacías
            continue
        row_dict = {}
        for idx, h in enumerate(headers):
            val = r[idx] if idx < len(r) else None
            if val == "":
                val = None
            row_dict[h] = val
        data_rows.append(row_dict)
        
    return headers, data_rows, None

def procesar_xlsx(file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], str | None]:
    """Procesa un archivo Excel moderno (.xlsx) en memoria usando openpyxl."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        sheet = wb.active
        if not sheet:
            return [], [], "No se encontró hoja activa en el archivo Excel."
            
        rows_generator = sheet.iter_rows(values_only=True)
        try:
            first_row = next(rows_generator)
        except StopIteration:
            return [], [], "El archivo Excel está vacío."
            
        headers = [str(h).strip().lower() for h in first_row if h is not None]
        data_rows = []
        
        for r in rows_generator:
            if not any(v is not None for v in r):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                val = r[idx] if idx < len(r) else None
                if val == "":
                    val = None
                row_dict[h] = val
            data_rows.append(row_dict)
            
        wb.close()
        return headers, data_rows, None
    except Exception as e:
        return [], [], f"Error al leer el archivo Excel: {str(e)}"

async def procesar_archivo(file_bytes: bytes, filename: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Procesa un archivo binario subido (.xlsx, .xls, .csv).
    Retorna (registros_validos, errores).
    """
    registros_validos: List[Dict[str, Any]] = []
    errores: List[Dict[str, Any]] = []
    bienes_en_archivo = set()
    
    # Distinguir formato
    if filename.endswith(".csv"):
        headers, data_rows, error_read = procesar_csv(file_bytes)
    elif filename.endswith((".xlsx", ".xls")):
        headers, data_rows, error_read = procesar_xlsx(file_bytes)
    else:
        return [], [{"fila": 0, "error": "Formato de archivo no soportado. Suba un archivo .xlsx o .csv."}]
        
    if error_read:
        return [], [{"fila": 0, "error": error_read}]
        
    # Mapeo de alias a campos estándar
    col_mapping = {
        "item": ["item", "correlativo", "nº", "nro", "item_correlativo"],
        "numero_bien": ["numero_bien", "nº de bien", "nro de bien", "nro_bien", "nro bien", "numero de bien", "codigo", "código", "bien", "nº bien"],
        "serial": ["serial", "seriales", "nº de serie", "nro de serie", "nro_serie", "nro serie", "numero_serie", "nº serie", "sn", "s/n"],
        "descripcion": ["descripcion", "descripción", "detalles", "detalle", "nombre", "activo"],
        "area_ubicacion": ["area_ubicacion", "área de ubicación", "ubicacion", "ubicación", "area", "área", "modulo", "módulo", "área de ubicacion"]
    }
    
    # Resolver qué encabezado del archivo mapea a qué campo
    resolved_headers = {}
    for key, aliases in col_mapping.items():
        found = False
        for h in headers:
            # Comparar removiendo acentos y espacios para mayor tolerancia
            import unicodedata
            h_norm = "".join(c for c in unicodedata.normalize('NFD', h) if unicodedata.category(c) != 'Mn').lower().strip()
            aliases_norm = ["".join(c for c in unicodedata.normalize('NFD', a) if unicodedata.category(c) != 'Mn').lower().strip() for a in aliases]
            
            if h_norm in aliases_norm or h in aliases:
                resolved_headers[key] = h
                found = True
                break
        if not found:
            resolved_headers[key] = None

    # Validar que al menos la columna obligatoria 'numero_bien' esté mapeada
    if not resolved_headers["numero_bien"]:
        return [], [{"fila": 0, "error": "Falta la columna mandatoria en el archivo cargado: 'numero_bien'"}]
        
    # Obtener los número_bien existentes en base de datos para prevenir duplicados en DB en una sola consulta
    db = database.get_db()
    existing_biens = set()
    if db is not None:
        try:
            existing_biens = set(await db.bienes.distinct("numero_bien"))
        except Exception as e:
            logger.error(f"Error al pre-cargar números de bienes existentes: {e}")

    # Procesar fila por fila
    for idx, row in enumerate(data_rows):
        num_fila = idx + 2 # Fila 1 es el header
        
        # Extraer valores usando el mapeo resuelto
        raw_item = row.get(resolved_headers["item"]) if resolved_headers["item"] else None
        raw_num_bien = row.get(resolved_headers["numero_bien"]) if resolved_headers["numero_bien"] else None
        raw_serial = row.get(resolved_headers["serial"]) if resolved_headers["serial"] else None
        raw_descripcion = row.get(resolved_headers["descripcion"]) if resolved_headers["descripcion"] else None
        raw_area = row.get(resolved_headers["area_ubicacion"]) if resolved_headers["area_ubicacion"] else None
        
        # Limpieza de campos
        item = clean_item_correlativo(raw_item)
        numero_bien = clean_numero_bien(raw_num_bien)
        serial = clean_string(raw_serial)
        descripcion = clean_string(raw_descripcion)
        area_ubicacion = clean_string(raw_area)
        
        errores_fila = []
        
        # Validar campos obligatorios
        if not numero_bien:
            errores_fila.append("El campo 'numero_bien' es obligatorio.")
        if not descripcion:
            errores_fila.append("El campo 'descripcion' es obligatorio.")
        if not area_ubicacion:
            errores_fila.append("El campo 'area_ubicacion' es obligatorio.")
            
        # Validar duplicación
        if numero_bien:
            if numero_bien in bienes_en_archivo:
                errores_fila.append(f"El bien con Nº de Bien '{numero_bien}' ya está duplicado dentro de este archivo.")
            else:
                bienes_en_archivo.add(numero_bien)
                
            if numero_bien in existing_biens:
                errores_fila.append(f"El bien con Nº de Bien '{numero_bien}' ya está registrado en la base de datos.")

        # Si hay errores en esta fila, registrarlos
        if errores_fila:
            identificador = numero_bien or f"Fila {num_fila}"
            errores.append({
                "fila": num_fila,
                "error": " | ".join(errores_fila),
                "nombre_persona": identificador  # Reutilizamos este campo de la plantilla vieja para mostrar el identificador del bien
            })
        else:
            documento = {
                "item": item,
                "numero_bien": numero_bien,
                "serial": serial,
                "descripcion": descripcion,
                "area_ubicacion": area_ubicacion,
                "fecha_carga": datetime.now(timezone.utc)
            }

            registros_validos.append(documento)
            
    return registros_validos, errores
