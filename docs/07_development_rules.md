# 7. CATEGORÍA: Reglas de Desarrollo y Estilo

## 7.1. Stack Tecnológico

* **Lenguaje:** Python `3.10-slim` o superior.
* **Framework Backend:** FastAPI `>=0.100.0`.
* **Template Engine:** Jinja2 v3.1.
* **Manejo de Estructuras Tabulares:** Pandas v2.0 + Openpyxl v3.1.
* **Acceso NoSQL:** Driver asíncrono Motor `>=3.3`.

## 7.2. Convenciones de Código

* Cumplimiento riguroso de las directrices de estilo `PEP 8`.
* Tipado explícito obligatorio (*Type Hints*) en todos los argumentos de funciones y modelos de entrada/salida apoyados en `Pydantic v2`.

## 7.3. Estrategia de Manejo de Errores

* Las excepciones en tiempo de lectura de los archivos de Excel no deben tumbar el proceso del servidor. Se capturarán mediante bloques `try/except` estructurados informando la fila exacta que causó la anomalía al operador.

## 7.4. Lista de "Prohibiciones Strict"

* **VETO-01:** Queda prohibido omitir el guardado en el historial de consultas bajo cualquier condición. Si la inserción en la bitácora falla, la búsqueda entera debe retornar un error de servidor para proteger la integridad de la auditoría.
* **VETO-02:** Prohibido el uso de operaciones bloqueantes de la base de datos de MongoDB. Cada llamada debe ser asíncrona usando la palabra clave `await`.
