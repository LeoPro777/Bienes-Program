# 2. CATEGORÍA: Arquitectura y Estructura

## 2.1. Patrón Arquitectónico

Se mantiene el patrón de **Monolito Clásico estructurado por responsabilidades** (Controladores de rutas HTTP, Servicios aislados para procesamiento de archivos y Plantillas de Presentación del lado del Servidor). Esto elimina la latencia de peticiones asíncronas cruzadas y problemas de CORS.

## 2.2. Árbol de Directorios Objetivo

```text
sistema-bienes-auditoria/
├── src/
│   ├── __init__.py
│   ├── main.py              # Inicialización de FastAPI, Middlewares y Enrutamiento Core
│   ├── database.py          # Conexión asíncrona a MongoDB Atlas e Inicialización de Índices
│   ├── auth.py              # Validación de Tokens JWT por Cookies HttpOnly
│   ├── config.py            # Gestión e inyección de variables de entorno (.env)
│   └── services/
│       ├── __init__.py
│       └── excel_service.py # Lógica de procesamiento de Pandas/Openpyxl para estructura de bienes
├── templates/               # Motor de Plantillas Jinja2
│   ├── buscador.html        # Interfaz de consulta de bienes con feedback visual
│   ├── admin.html           # Panel de visualización de bitácora y carga masiva
│   └── login.html           # Formulario de autenticación para el operador
├── static/
│   └── style.css            # Estilos CSS Nativos optimizados
├── Dockerfile               # Despliegue de contenedor único ligero
└── requirements.txt         # Dependencias estrictas del ecosistema
```

## 2.3. Responsabilidad de Componentes

* `src/main.py`: Captura los formularios web nativos, intercepta los parámetros de búsqueda, despacha la escritura inmediata en la bitácora de auditoría y renderiza las respuestas.
* `src/services/excel_service.py`: Encapsula de forma estricta la librería de lectura de datos, transformando los binarios de Excel en documentos estructurados que respeten la nomenclatura limpia del esquema NoSQL.

## 2.4. Protocolos y Canales de Comunicación

* **REST HTTP/S:** Uso exclusivo y plano de métodos `GET` para visualización/búsqueda y `POST` para procesamiento de datos de carga, inicio de sesión y adición al historial.
