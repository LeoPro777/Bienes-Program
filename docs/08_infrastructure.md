# 8. CATEGORÍA: Infraestructura, DevOps y Resiliencia

## 8.1. Entornos y Configuración (`.env`)

Variables requeridas en el panel de control del entorno del servidor de aplicaciones (ej: Render):

* `MONGODB_URI`: Cadena de conexión de producción a la base de datos Atlas (`mongodb+srv://...`).
* `JWT_SECRET`: Llave de alta seguridad criptográfica utilizada para firmar las cookies de sesión del operador.
* `ADMIN_USERNAME`: Nombre de acceso del operador (por defecto: `admin`).
* `ADMIN_PASSWORD`: Contraseña secreta de acceso del operador (por defecto: `admin`).

## 8.2. Containerización / Despliegue

Se mantiene el uso del archivo `Dockerfile` optimizado basado en una distribución ligera para ejecutar el servidor mediante Uvicorn escuchando dinámicamente en el puerto inyectado por la plataforma de la nube.

## 8.3. Mecanismo de Logs y Monitoreo

* Configuración del nivel de logging global en `INFO`.
* Cada evento de carga masiva de inventario debe registrar en la salida estándar la identidad del operador y la cantidad de registros inyectados para auditorías externas del sistema.

## 8.4. Resiliencia de Red

* **Estrategia de Conexión:** Límite estricto en el pool de conexiones (`maxPoolSize=10`) para no desbordar los límites operativos de la infraestructura NoSQL gratuita de MongoDB Atlas.
* **Timeout de Seguridad:** Umbral máximo de espera de peticiones a base de datos configurado en 5000ms. Si se excede, el sistema aborta de forma segura la consulta para liberar los hilos de ejecución de la aplicación web.
