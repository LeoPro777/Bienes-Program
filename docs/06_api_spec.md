# 6. CATEGORÍA: Contratos de Integración y API

## 6.1. Especificación de Endpoints Administrativos

* **Ruta:** `/admin/cargar-bienes`
* **Método:** `POST`
* **Content-Type:** `multipart/form-data`

## 6.2. Contrato de Entrada (Estructura Tabular Esperada)

El archivo cargado por el operador debe contar con una fila inicial de encabezados que contenga explícita o implícitamente variantes de las siguientes palabras clave:

```text
item, numero_bien, descripcion, area_ubicacion
```

*(El servicio resolverá automáticamente sin importar mayúsculas, minúsculas o espacios gracias al mapeo dinámico del diccionario de alias).*

## 6.3. Contrato de Salida Exitosa (API interna de carga)

* **Código HTTP:** `200 OK`
* **Payload JSON:**

```json
{
  "status": "Éxito",
  "bienes_insertados": 145,
  "mensaje": "El inventario de activos ha sido actualizado correctamente."
}
```

## 6.4. Catálogo de Errores Estándar

* **Error 400 Bad Request (Estructura Rota o Inválida):**

```json
{
  "detail": "Falta la columna mandatoria en el archivo cargado: 'numero_bien'"
}
```

* **Error 401 Unauthorized (Sesión Expirada):**

```json
{
  "detail": "Acceso denegado: Sesión inválida o token ausente."
}
```
