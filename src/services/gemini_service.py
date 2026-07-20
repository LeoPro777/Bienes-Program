import logging
import base64
import json
import urllib.request
import urllib.error
from typing import Tuple
from src import config

logger = logging.getLogger(__name__)

async def verificar_foto_numero_bien(image_bytes: bytes, numero_bien_esperado: str) -> Tuple[bool, str]:
    """
    Verifica mediante la API de Google Gemini si el número de bien en la imagen de la etiqueta
    coincide con el numero_bien_esperado.
    
    Retorna: (es_valido: bool, motivo_o_explicacion: str)
    """
    if not image_bytes:
        return False, "No se recibió el archivo de imagen para la verificación."

    api_key = config.GEMINI_API_KEY
    if not api_key or api_key == "tu_gemini_api_key":
        logger.warning("GEMINI_API_KEY no configurada en .env.")
        return False, "La API de Gemini no está configurada en las variables de entorno (.env). Configure GEMINI_API_KEY para habilitar la verificación por IA."

    prompt = (
        f"Analiza la siguiente imagen de una etiqueta, placa, grabado o chapa de inventario.\n"
        f"El número de bien o activo esperado es: '{numero_bien_esperado}'.\n"
        "Determina si la foto muestra claramente esa etiqueta y si el número impreso/etiquetado coincide o contiene el número de bien esperado.\n"
        "Responde EXCLUSIVAMENTE en formato JSON plano sin bloques de código Markdown con la estructura:\n"
        '{"coincide": true|false, "numero_detectado": "texto o numero detectado", "explicacion": "breve explicacion de lo que observas"}'
    )

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # Intentar llamadas a modelos recientes de Gemini (gemini-2.5-flash, gemini-1.5-flash)
    modelos = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
    
    last_error = ""
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": base64_image
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "response_mime_type": "application/json"
            }
        }
        
        headers = {"Content-Type": "application/json"}
        req_data = json.dumps(payload).encode("utf-8")
        
        try:
            req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=25) as response:
                if response.status == 200:
                    resp_body = response.read().decode("utf-8")
                    data = json.loads(resp_body)
                    
                    try:
                        text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        # Limpiar posible bloque ```json ... ```
                        if text_response.startswith("```"):
                            lines = text_response.splitlines()
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            text_response = "\n".join(lines).strip()
                            
                        result_json = json.loads(text_response)
                        coincide = bool(result_json.get("coincide", False))
                        explicacion = result_json.get("explicacion", "Verificación realizada por IA.")
                        num_detectado = result_json.get("numero_detectado", "N/A")
                        
                        if coincide:
                            msg = f"IA confirmó coincidencia. Número detectado: {num_detectado}. ({explicacion})"
                            logger.info(f"Verificación exitosa por Gemini ({modelo}): {msg}")
                            return True, msg
                        else:
                            msg = f"La foto de la etiqueta fue rechazada por la IA. Número detectado: '{num_detectado}'. Observación: {explicacion}"
                            logger.warning(f"Rechazo de etiqueta por Gemini ({modelo}): {msg}")
                            return False, msg
                    except Exception as parse_err:
                        logger.error(f"Error parseando respuesta de Gemini: {parse_err}. Respuesta pura: {text_response}")
                        return False, f"La respuesta de la IA no tuvo el formato esperado ({str(parse_err)})."
        except urllib.error.HTTPError as http_err:
            err_msg = http_err.read().decode("utf-8") if http_err.fp else str(http_err)
            logger.warning(f"Fallo Gemini modelo {modelo}: {http_err.code} - {err_msg}")
            last_error = f"Error de API Gemini ({http_err.code}): {err_msg}"
        except Exception as e:
            logger.warning(f"Fallo conexión con Gemini {modelo}: {e}")
            last_error = str(e)

    return False, f"No se pudo completar la verificación con la API de Gemini. Detalle: {last_error}"
