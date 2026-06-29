# 1. CATEGORÍA: Visión General y Alcance

## 1.1. Propósito del Sistema

El sistema resuelve la falta de trazabilidad y verificación inmediata en sitio de los activos físicos institucionales. Su objetivo principal es proveer una plataforma web ultra-ligera, resiliente y de alta velocidad que actúe como un buscador rápido de bienes por su número identificador (`Nº DE BIEN`), automatizando por completo el registro inmutable de cada consulta efectuada para auditar patrones de búsqueda, incidencias o intentos de verificación de activos inexistentes.

## 1.2. Alcance del Proyecto

* **Dentro del Alcance (In Scope):**
  * Interfaz pública/operadora optimizada para teléfonos móviles y terminales antiguos (HTML/CSS prerenderizado en servidor).
  * Motor de búsqueda exacta basado en el campo numérico o alfanumérico `Nº DE BIEN`.
  * Sistema de registro en segundo plano (*Audit Trail*) que guarda de forma obligatoria cada consulta (exista o no el bien), marcando un indicador booleano de coincidencia (`coincidio`).
  * Panel administrativo protegido con las credenciales maestras del entorno (`admin`/`admin`) para visualización cronológica del historial de consultas y carga masiva de inventarios.
  * Módulo de carga en lote mediante archivos Excel (`.xlsx`) y `.csv` parametrizados según las columnas extraídas del libro contable conteniendo: `ITEM`, `Nº DE BIEN`, `DESCRIPCIÓN`, `ÁREA DE UBICACIÓN`.

* **Fuera del Alcance (Out of Scope):**
  * Depreciación contable automatizada de activos financieros o cálculo de amortizaciones.
  * Seguimiento por geolocalización satelital (GPS) en tiempo real o integraciones activas con tags RFID/Hardware dedicado.

## 1.3. Reglas de Negocio Globales

* **RN-01 (Cero Dependencias en Cliente):** La vista del buscador y de administración se generará del lado del servidor (SSR) mediante FastAPI y Jinja2, eliminando sobrecargas de Javascript para asegurar la operabilidad en redes lentas.
* **RN-02 (Inmutabilidad del Historial):** El módulo de consultas es estrictamente de tipo *Append-Only*. Ningún usuario u operador administrativo puede editar, truncar o eliminar registros del historial de consultas una vez insertados.
* **RN-03 (Registro Obligatorio):** Toda petición enviada al motor de búsqueda debe generar un documento de auditoría de forma atómica antes de retornar la respuesta HTTP al cliente.

## 1.4. Glosario de Términos

* **Nº de Bien:** Identificador único correlativo o código de barra asignado físicamente a un activo de la organización (ej: "8").
* **Historial de Consulta:** Colección cronológica que almacena quién, cuándo y qué identificador se buscó.
* **Coincidió (Match Flag):** Atributo booleano que determina si el bien consultado existía en la base de datos al momento de la revisión.
