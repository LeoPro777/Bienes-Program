# 5. CATEGORÍA: Seguridad, Autenticación y Sesiones

## 5.1. Estrategia de Autenticación

Autenticación basada en el proveedor local estricto de la aplicación. Las credenciales se leen directamente desde el entorno seguro del contenedor del servidor sin persistencia en colecciones para mitigar riesgos de filtración.

## 5.2. Ciclo de Vida de la Sesión

* **Tipo de Token:** Token JWT firmado digitalmente bajo el algoritmo `HS256`.
* **Persistencia:** Guardado en el cliente en una Cookie segura con propiedades restrictivas activas (`HttpOnly=True`, `SameSite=Strict`, `Secure=True` en producción).
* **Expiración:** Tiempo de vida fijo de **6 horas** desde el inicio de sesión del operador.

## 5.3. Modelo de Autorización (Matriz RBAC)

| Endpoint / Ruta | Método | Rol: Público (Consultor) | Rol: Admin (Operador) |
| --- | --- | --- | --- |
| `/` (Buscador General) | `GET` | **PERMITIDO** (Genera bitácora automática) | **PERMITIDO** |
| `/login` | `GET`/`POST` | **PERMITIDO** | **PERMITIDO** (Redirige a panel) |
| `/admin` (Panel Auditoría) | `GET` | DENEGADO (Redirige a /login) | **PERMITIDO** |
| `/admin/cargar-bienes` | `POST` | DENEGADO (`401 Unauthorized`) | **PERMITIDO** |
