# 4. CATEGORÍA: Modelo y Estado de Datos

## 4.1. Motor de Base de Datos

* **Motor:** MongoDB Atlas (Capa M0 o Instancia Local en contingencia).
* **Estrategia de Acceso:** Driver asíncrono `motor` para Python.

## 4.2. Esquema Detallado

### Colección: `bienes`

* `_id`: `ObjectId` (Clave Primaria Nativa).
* `item`: `Int` (Corresponde a la columna `ITEM` de la hoja de cálculo).
* `numero_bien`: `String` (Strict, Requerido. Código identificador indexado de forma única).
* `descripcion`: `String` (Strict, Requerido. Almacena la descripción completa y detalles técnicos/seriales).
* `area_ubicacion`: `String` (Strict, Requerido. Ubicación física estandarizada del activo, ej: "Módulo B").
* `fecha_carga`: `DateTime` (Valor por defecto UTC Now).

### Colección: `historial_consultas`

* `_id`: `ObjectId` (Clave Primaria Nativa).
* `valor_buscado`: `String` (Identificador numérico o de texto que el usuario introdujo).
* `fecha_consulta`: `DateTime` (Strict, Requerido. Instante exacto del evento).
* `coincidio`: `Boolean` (Strict, Requerido. `True` si el activo existía, `False` si fue una búsqueda fallida).
* `metadata_cliente`: `Document` (Almacena el User-Agent o datos del navegador para auditoría de seguridad).

## 4.3. Restricciones e Índices Estrictos

* **Índice Único:** `{"numero_bien": 1}`, con restricción de unicidad (`unique=True`) para evitar que la carga masiva duplique el mismo bien en el sistema.
* **Índice de Búsqueda de Bitácora:** `{"fecha_consulta": -1}` para renderizar de manera veloz las últimas consultas en el panel administrativo.

## 4.4. Seeders (Datos Iniciales)

No se requiere siembra estructural de colecciones relacionales. Al igual que el diseño base, las credenciales del operador maestro se inyectan a nivel de variables de infraestructura de ejecución (`ADMIN_USERNAME` y `ADMIN_PASSWORD`).
