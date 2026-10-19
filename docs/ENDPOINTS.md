# Contratos actuales y mapa de flujo

Documento generado desde app/main.py porque no existia este contrato. Describe el comportamiento observado, incluidas sus debilidades; no las prescribe como requisitos de seguridad ni propone cambiar rutas o formatos. El seguimiento de hallazgos se mantiene exclusivamente en [HALLAZGOS.md](../HALLAZGOS.md).

## Token y respuestas comunes

Las cinco rutas declaradas en la aplicacion dependen de legacy_identity ([app/main.py:17](../app/main.py#L17)). Reciben el encabezado `Authorization: Bearer <token>`; el codigo elimina las apariciones de `Bearer `, decodifica Base64 y separa cuatro campos con `|`: username, role, timestamp de expiracion en segundos Unix y secreto compartido. Compara el secreto con la constante del codigo y rechaza timestamps menores que la hora actual; devuelve username y role. No verifica firma, emisor ni audiencia ([app/main.py:19](../app/main.py#L19), [app/main.py:22](../app/main.py#L22), [app/main.py:24](../app/main.py#L24)).

Los errores de esta dependencia producen HTTP 401 con JSON `{"detail": "Invalid token: <detalle>"}` ([app/main.py:26](../app/main.py#L26)). FastAPI genera HTTP 422 con `detail` para entradas que no cumplen la validacion de sus parametros. No hay un manejador propio de errores de SQLite o escritura; no se garantiza un cuerpo JSON para esos errores.

## Rutas

| Metodo | Ruta | Entrada | Respuesta correcta | Evidencia |
|---|---|---|---|---|
| GET | /api/tasks | Query opcional `owner` (string). Si falta o esta vacio se usa username. | HTTP 200, array de tareas del owner seleccionado, ordenadas por id ascendente; puede ser vacio. | [app/main.py:67](../app/main.py#L67), [app/main.py:69](../app/main.py#L69), [app/main.py:70](../app/main.py#L70), [app/main.py:75](../app/main.py#L75) |
| POST | /api/tasks | Cuerpo JSON objeto obligatorio. Campos opcionales: `title` y `description` (por defecto strings vacios), `status` (TODO), `priority` (MEDIUM), `owner` (username). Los valores recibidos se convierten mediante str; no hay enums ni modelos de dominio. Otros campos se ignoran. | HTTP 201, objeto tarea persistida. | [app/main.py:77](../app/main.py#L77), [app/main.py:78](../app/main.py#L78), [app/main.py:79](../app/main.py#L79), [app/main.py:83](../app/main.py#L83), [app/main.py:88](../app/main.py#L88) |
| GET | /api/summary | Query opcional `owner` (string), con el mismo fallback a username. | HTTP 200, objeto con `owner` (string), `total` (entero), `byStatus` (objeto de conteos por estado) y `highPriorityOpen` (entero). Cuenta prioridad HIGH cuyo estado no sea DONE ni ARCHIVED. Sin tareas: total y highPriorityOpen en 0, byStatus vacio. | [app/main.py:90](../app/main.py#L90), [app/main.py:92](../app/main.py#L92), [app/main.py:94](../app/main.py#L94), [app/main.py:101](../app/main.py#L101), [app/main.py:104](../app/main.py#L104) |
| POST | /api/requirements | `multipart/form-data`, campo obligatorio `file` de tipo archivo. | HTTP 201, objeto con `owner` (username), `fileName` (nombre recibido), `storedAt` (ruta construida, string) y `size` (bytes escritos, entero). | [app/main.py:107](../app/main.py#L107), [app/main.py:108](../app/main.py#L108), [app/main.py:112](../app/main.py#L112) |
| GET | /api/backend-health | Sin parametros propios; usa `AUTH_HEALTH_URL` del entorno o `http://localhost:8080/q/health`. | HTTP 200, objeto con `requestedBy` (username), `status` (codigo HTTP remoto, entero) y `body` (respuesta remota decodificada UTF-8, string). Ante excepcion dentro del try conserva HTTP 200 y devuelve status 0 y body con el texto del error. | [app/main.py:114](../app/main.py#L114), [app/main.py:116](../app/main.py#L116), [app/main.py:118](../app/main.py#L118), [app/main.py:119](../app/main.py#L119), [app/main.py:121](../app/main.py#L121) |

Objeto tarea: `id` (entero), `title`, `description`, `status`, `owner`, `priority` y `createdAt` (strings). createdAt procede de created_at en SQLite, generado con datetime('now') al crear tareas ([app/main.py:56](../app/main.py#L56), [app/main.py:64](../app/main.py#L64), [app/main.py:84](../app/main.py#L84)).

FastAPI tambien registra sus rutas de documentacion por defecto: `/docs`, `/docs/oauth2-redirect`, `/redoc` y `/openapi.json`; no tienen la dependencia legacy_identity declarada para las cinco rutas anteriores ([app/main.py:45](../app/main.py#L45)).

## SQLite y ciclo de vida

create_app selecciona la base por argumento db_path, variable `WORKSHOP_DB_PATH` o `./data/workshop.db`. Crea el directorio padre y abre una conexion SQLite con check_same_thread=False y filas sqlite3.Row. Crea la tabla tasks y, si esta vacia, inserta tres tareas iniciales: dos de student y una de trainer. La conexion queda en app.state.connection y en el cierre de las rutas ([app/main.py:30](../app/main.py#L30), [app/main.py:32](../app/main.py#L32), [app/main.py:35](../app/main.py#L35), [app/main.py:37](../app/main.py#L37), [app/main.py:38](../app/main.py#L38), [app/main.py:40](../app/main.py#L40), [app/main.py:42](../app/main.py#L42), [app/main.py:46](../app/main.py#L46)).

Flujo de lectura: token -> identidad -> owner elegido por el cliente o username -> SELECT concatenado -> filas -> serializacion de tarea o agregado. Flujo de creacion: token -> cuerpo dict -> conversion a strings -> INSERT concatenado -> commit -> SELECT por lastrowid -> serializacion ([app/main.py:69](../app/main.py#L69), [app/main.py:70](../app/main.py#L70), [app/main.py:79](../app/main.py#L79), [app/main.py:84](../app/main.py#L84), [app/main.py:86](../app/main.py#L86), [app/main.py:87](../app/main.py#L87), [app/main.py:93](../app/main.py#L93)).

La conexion se cierra en el evento shutdown. La instancia de modulo app llama a create_app al importar app.main, por lo que importar el modulo puede crear directorios y modificar la base ([app/main.py:123](../app/main.py#L123), [app/main.py:125](../app/main.py#L125), [app/main.py:130](../app/main.py#L130)).

## Carga de archivos y dependencia externa

El directorio de cargas se elige por argumento upload_dir, `WORKSHOP_UPLOAD_DIR` o `./uploads`, se crea al iniciar y se expone en app.state.upload_dir ([app/main.py:31](../app/main.py#L31), [app/main.py:33](../app/main.py#L33), [app/main.py:47](../app/main.py#L47)).

Flujo de carga: token -> identidad -> archivo multipart -> union del directorio con file.filename -> lectura completa en memoria -> write_bytes -> metadatos. La funcion no valida confinamiento de ruta, extension ni tamano, no genera nombres unicos y no registra la carga en SQLite ([app/main.py:108](../app/main.py#L108), [app/main.py:109](../app/main.py#L109), [app/main.py:110](../app/main.py#L110), [app/main.py:111](../app/main.py#L111), [app/main.py:112](../app/main.py#L112)).

backend_health consulta la URL configurada mediante urllib3.PoolManager con timeout=3.0. No reenvia el token: la identidad local solo se usa para requestedBy. Este mapeo se limita al cliente en este repositorio; no requiere inspeccionar ni modificar el backend externo ([app/main.py:116](../app/main.py#L116), [app/main.py:118](../app/main.py#L118), [app/main.py:119](../app/main.py#L119)).