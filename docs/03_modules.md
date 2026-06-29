# 3. CATEGORÍA: Especificación Modular y Requerimientos

## 3.1. Listado de Módulos

* **Módulo 01: Buscador de Activos e Historial Automatizado (Público/Operador).**
* **Módulo 02: Panel de Control de Auditoría y Gestión Masiva (Autenticado).**

## 3.2. Especificación Detallada de Módulos

### 3.2.1. Módulo 01: Buscador de Activos e Historial

* **Requerimientos Funcionales:**
  * El usuario ingresa un identificador en la barra de búsqueda.
  * El sistema consulta de manera exacta contra la colección de bienes.
  * Si el bien existe, despliega en pantalla de forma clara: `Nº DE BIEN`, `DESCRIPCIÓN` (ej: *Mouse Óptico, Marca Genius, Serial...*) y `ÁREA DE UBICACIÓN`.
  * Independientemente del resultado, el sistema guarda en la colección de logs: el valor buscado, la fecha/hora exacta en formato UTC, el origen del cliente y si `coincidio` (`True` o `False`).

* **Flujo de Datos / Algoritmo:**
  1. Cliente ejecuta `GET /?numero_bien=valor`.
  2. El backend intercepta el valor y realiza la consulta en la base de datos de manera asíncrona.
  3. Paralelamente (o inmediatamente antes de responder), ejecuta un `insert_one()` en la colección de logs estableciendo el estado de la búsqueda.
  4. Retorna la plantilla con los datos del activo o un mensaje de "Bien no registrado", guardando el registro histórico de forma exitosa.

* **Wireframe / UI Concept:**
  Barra superior minimalista. Un input centralizado optimizado para números o texto corto con el botón "Verificar Bien". Al buscar, si es exitoso, muestra una tarjeta con un borde limpio conteniendo los datos descriptivos organizados en filas claras; si no existe, muestra un banner de advertencia sutil indicando que el código no está en la base de datos pero ha sido reportado en el registro de auditoría.

### 3.2.2. Módulo 02: Panel de Control de Auditoría y Gestión Masiva

* **Requerimientos Funcionales:**
  * El operador inicia sesión en `/login` con credenciales de entorno (`admin`/`admin`).
  * Acceso a una tabla cronológica que lista todas las búsquedas del sistema (mostrando las alertas resaltadas donde `coincidio == False`).
  * Área de carga *Drag & Drop* para subir el archivo Excel/CSV que contiene las columnas estandarizadas de bienes.

* **Flujo de Datos:**
  1. Operador sube archivo vía `POST /admin/cargar-bienes` (`multipart/form-data`).
  2. `excel_service` mapea las columnas (`ITEM`, `Nº DE BIEN`, `DESCRIPCIÓN`, `ÁREA DE UBICACIÓN`), limpia nulos y ejecuta un `insert_many` en bloques atómicos para poblar el inventario.
