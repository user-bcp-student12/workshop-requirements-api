# API - Contrato de integracion actual

Actualizado el 2026-10-19 desde el codigo refactorizado. Describe lo que la API hace hoy, incluidos defectos pendientes; no implica que sea apta para produccion. El seguimiento permanece exclusivamente en [HALLAZGOS.md](../HALLAZGOS.md).

## Preparacion y convenciones

Base local usada en los ejemplos: `http://127.0.0.1:8000`. El proceso se inicia con `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`, despues de instalar las dependencias, como indica [README.md](../README.md).

Los comandos usan cURL con sintaxis Bash. La variable `TOKEN` debe contener un JWT RS256 valido emitido y firmado por un emisor compatible; no debe contener el prefijo Bearer. `${TOKEN}` es una sustitucion de credencial, no un token de ejemplo valido por si mismo. En PowerShell se puede usar `curl.exe` y sustituir `${TOKEN}` por `$env:TOKEN`. La API no tiene un endpoint de login ni emite tokens. El antiguo token Base64 no se acepta.

Configuracion del servidor:

| Variable | Tipo | Valor predeterminado / efecto |
|---|---|---|
| WORKSHOP_JWT_PUBLIC_KEY | string PEM | Sin valor por defecto. Clave publica RSA de verificacion, no una clave privada ni una ruta de archivo. Si falta o es invalida, la autenticacion devuelve 401. |
| WORKSHOP_JWT_ISSUER | string no vacio | workshop-auth; debe coincidir con iss. |
| WORKSHOP_JWT_AUDIENCE | string no vacio | workshop-requirements-api; aud debe contener esta audiencia. |
| WORKSHOP_DB_PATH | string de ruta | ./data/workshop.db, salvo argumento db_path de create_app. |
| WORKSHOP_UPLOAD_DIR | string de ruta | ./uploads, salvo argumento upload_dir de create_app. |
| WORKSHOP_UPLOAD_MAX_FILE_BYTES | integer positivo | 5242880 (5 MiB), limite del archivo. |
| WORKSHOP_UPLOAD_MAX_BODY_BYTES | integer positivo | 6291456 (6 MiB), limite del multipart completo antes del parser. |
| WORKSHOP_UPLOAD_CHUNK_BYTES | integer positivo | 65536 (64 KiB), bloque de lectura y copia. |
| WORKSHOP_UPLOAD_ALLOWED_EXTENSIONS | string separado por comas | .txt,.md,.pdf; comparacion sin distinguir mayusculas. El nombre simple sin extension se permite. |
| AUTH_HEALTH_URL | string URL | http://localhost:8080/q/health; solo la configura el servidor. |

La politica exige bloque <= archivo < cuerpo; valores invalidos impiden iniciar la aplicacion. El limite de cuerpo cuenta bytes reales y no confia en Content-Length. Los errores de este limite pueden preceder a la autenticacion y al parsing del multipart.

El JWT requiere firma RS256, iss, aud, exp y sub. sub es un string no vacio ni compuesto solo de espacios, y define el propietario efectivo. exp es un numero JSON finito que debe seguir vigente. role es opcional, string, y no concede acceso a otros propietarios. nbf e iat se verifican cuando aparecen. La clave publica y los valores esperados proceden de configuracion confiable, no del token ([app/security.py:13](../app/security.py#L13), [app/security.py:26](../app/security.py#L26), [app/security.py:51](../app/security.py#L51), [app/schemas.py:10](../app/schemas.py#L10), [app/schemas.py:22](../app/schemas.py#L22)).

Todos los ejemplos usan identidad sub=student. Cada ejemplo de tareas parte de una base recien inicializada: dos tareas de student y una de trainer. Los ids y las fechas varian con el estado de la base; los valores mostrados son ejemplos verificables de esos formatos, no constantes del contrato. createdAt usa el texto UTC producido por SQLite, `YYYY-MM-DD HH:MM:SS`, sin T ni sufijo Z. Los campos JSON son sensibles a mayusculas y conservan createdAt, byStatus, highPriorityOpen, fileName, storedAt y requestedBy.

Las respuestas JSON tienen Content-Type application/json. Los errores de validacion tienen detail como array de objetos; los HTTPException propios tienen detail como string. Fallos no capturados pueden producir HTTP 500 con Content-Type text/plain; no debe suponerse que toda respuesta sea JSON. La lectura/parsing del cuerpo puede fallar antes de la autenticacion: por ejemplo, JSON malformado sin token puede devolver 422, no necesariamente 401.

Swagger, ReDoc y OpenAPI estan disponibles en `/docs`, `/redoc` y `/openapi.json`, con `/docs/oauth2-redirect` auxiliar. No se les declara la dependencia de autenticacion de las cinco rutas de negocio.

## GET /api/tasks

### 1. Que hace

Lista las tareas del usuario autenticado, ordenadas por id ascendente ([app/main.py:58](../app/main.py#L58), [app/task_repository.py:6](../app/task_repository.py#L6)).

### 2. Autenticacion

Si. Enviar el header exacto `Authorization: Bearer ${TOKEN}`, con el JWT configurado en Preparacion. El esquema Bearer se compara sin distinguir mayusculas; se exige un unico token. No se permiten credenciales Base64 legacy.

### 3. Request

| Campo/parametro | Tipo | Obligatorio | Descripcion |
|---|---|---|---|
| Authorization (header) | string | Si | Bearer seguido de un JWT RS256 valido. |
| owner (query) | string | No | Se acepta por compatibilidad, pero se ignora. Nunca permite elegir al propietario consultado. |

Sin cuerpo. Ejemplo completo: aun enviando owner=trainer, un token de student consulta solo student.

```bash
curl --request GET 'http://127.0.0.1:8000/api/tasks?owner=trainer' --header "Authorization: Bearer ${TOKEN}"
```

### 4. Response exitosa

HTTP **200**. La raiz es un array, no un objeto envoltorio; sin tareas devuelve `[]`.

| Campo | Tipo | Descripcion |
|---|---|---|
| raiz | array de objetos tarea | Todas las tareas de la identidad, en orden ascendente de id. Sin paginacion. |
| [].id | integer | Identificador SQLite. |
| [].title | string | Titulo almacenado. |
| [].description | string | Descripcion almacenada. |
| [].status | string | Estado; no esta restringido a un enum. |
| [].owner | string | Propietario, igual al usuario autenticado. |
| [].priority | string | Prioridad; no esta restringida a un enum. |
| [].createdAt | string | Fecha de creacion en el formato indicado en Preparacion. |

```json
[
	{
		"id": 1,
		"title": "Refactor login",
		"description": "Separar responsabilidades en frontend",
		"status": "TODO",
		"owner": "student",
		"priority": "HIGH",
		"createdAt": "2026-10-19 21:55:09"
	},
	{
		"id": 2,
		"title": "Review API",
		"description": "Revisar seguridad de endpoints",
		"status": "IN_PROGRESS",
		"owner": "student",
		"priority": "MEDIUM",
		"createdAt": "2026-10-19 21:55:09"
	}
]
```

Los siete campos de cada tarea proceden de [app/schemas.py:45](../app/schemas.py#L45).

### 5. Respuestas de error

**401**: header ausente/malformado, token invalido/vencido, claims incorrectos o configuracion de clave/emisor/audiencia invalida.

```json
{"detail": "Invalid token: authentication failed"}
```

**500 JSON**: sqlite3.Error al leer las tareas, traducido por el adaptador HTTP ([app/main.py:22](../app/main.py#L22)).

```json
{"detail": "Task storage unavailable"}
```

**500 no controlado**: otra excepcion no traducida, por ejemplo datos SQLite incompatibles con el modelo de respuesta. Con la configuracion actual debug=False, el cuerpo estandar es texto, no JSON:

```text
Internal Server Error
```

OpenAPI tambien anuncia 422 por validacion automatica de parametros; no se identifico un request HTTP normal que lo reproduzca para owner/header, ambos strings sin restricciones adicionales. Es una pregunta abierta, no un motivo para inventar un cuerpo de error (Q-1).

### 6. Notas de seguridad

La autorizacion usa la identidad verificada, no owner; role no permite consultar tareas ajenas ([app/task_service.py:10](../app/task_service.py#L10), [app/task_service.py:22](../app/task_service.py#L22)). El filtro SQL esta parametrizado. No hay limite de cantidad/paginacion: el repositorio lee y serializa todas las filas del usuario.

## POST /api/tasks

### 1. Que hace

Crea una tarea perteneciente al usuario autenticado y devuelve sus datos ([app/main.py:63](../app/main.py#L63)).

### 2. Autenticacion

Si. Enviar `Authorization: Bearer ${TOKEN}`. La firma y los claims se validan como indica Preparacion. La identidad determina owner aunque el cuerpo contenga otro valor.

### 3. Request

| Campo/parametro | Tipo | Obligatorio | Descripcion |
|---|---|---|---|
| Authorization (header) | string | Si | Bearer seguido de un JWT RS256 valido. |
| Content-Type (header) | string | No, recomendado application/json | Con application/json, el cuerpo se parsea como JSON; si se omite, FastAPI tambien intenta JSON. Un tipo incompatible puede hacer que el cuerpo no sea validado como objeto. |
| cuerpo | objeto JSON | Si | Puede ser {}; null, un array o un string no sustituyen al objeto. |
| title (cuerpo) | valor JSON, convertido a string | No | Por defecto "". Se aplica str de Python al valor recibido. |
| description (cuerpo) | valor JSON, convertido a string | No | Por defecto "". Misma conversion que title. |
| status (cuerpo) | valor JSON, convertido a string | No | Por defecto TODO. No se impone un enum. |
| priority (cuerpo) | valor JSON, convertido a string | No | Por defecto MEDIUM. No se impone un enum. |
| owner (cuerpo) | cualquier valor JSON | No | Aceptado, pero ignorado. Se persiste el sub verificado. |

Los campos adicionales se ignoran. Las conversiones no equivalen a serializar JSON: por ejemplo 42 -> "42", null -> "None", false -> "False" y [1, 2] -> "[1, 2]" ([app/schemas.py:35](../app/schemas.py#L35)). Ejemplo completo:

```bash
curl --request POST 'http://127.0.0.1:8000/api/tasks' --header "Authorization: Bearer ${TOKEN}" --header 'Content-Type: application/json' --data '{"title":"Add tests","description":"Improve coverage","status":"TODO","priority":"HIGH","owner":"trainer"}'
```

```json
{
	"title": "Add tests",
	"description": "Improve coverage",
	"status": "TODO",
	"priority": "HIGH",
	"owner": "trainer"
}
```

### 4. Response exitosa

HTTP **201**, objeto tarea sin envoltorio ni header Location definido por esta ruta.

| Campo | Tipo | Descripcion |
|---|---|---|
| id | integer | Identificador asignado por SQLite; en una base inicial sin otras inserciones, 4. |
| title | string | Titulo despues de la conversion indicada. |
| description | string | Descripcion despues de la conversion indicada. |
| status | string | Estado recibido o TODO. |
| owner | string | Usuario autenticado; no el owner enviado por el cliente. |
| priority | string | Prioridad recibida o MEDIUM. |
| createdAt | string | Fecha UTC generada por datetime('now') de SQLite, sin T ni Z. |

```json
{
	"id": 4,
	"title": "Add tests",
	"description": "Improve coverage",
	"status": "TODO",
	"owner": "student",
	"priority": "HIGH",
	"createdAt": "2026-10-19 21:55:09"
}
```

Persistencia y serializacion: [app/task_repository.py:29](../app/task_repository.py#L29), [app/task_service.py:25](../app/task_service.py#L25), [app/schemas.py:45](../app/schemas.py#L45).

### 5. Respuestas de error

**400**: excepcion durante el parsing del cuerpo distinta de JSONDecodeError; comprobado con bytes JSON que no se pueden decodificar.

```json
{"detail": "There was an error parsing the body"}
```

**401**: fallo de autenticacion o configuracion del verificador.

```json
{"detail": "Invalid token: authentication failed"}
```

**422, cuerpo ausente/null**:

```json
{"detail": [{"type": "missing", "loc": ["body"], "msg": "Field required", "input": null}]}
```

**422, cuerpo no objeto**, por ejemplo un array vacio:

```json
{"detail": [{"type": "dict_type", "loc": ["body"], "msg": "Input should be a valid dictionary", "input": []}]}
```

**422, JSON malformado**, ejemplo al enviar unicamente `{`:

```json
{"detail": [{"type": "json_invalid", "loc": ["body", 1], "msg": "JSON decode error", "input": {}, "ctx": {"error": "Expecting property name enclosed in double quotes"}}]}
```

La posicion en loc, input y ctx dependen del request; los ejemplos reflejan los casos indicados, no un texto universal para todo error 422.

**500 JSON**: sqlite3.Error durante insert, recuperacion de la fila o commit. El repositorio intenta rollback y el adaptador oculta el detalle del error.

```json
{"detail": "Task storage unavailable"}
```

**500 no controlado**: otra excepcion fuera de sqlite3.Error, por ejemplo un fallo de codificacion al enviar un string incompatible con SQLite. Cuerpo estandar text/plain con debug=False:

```text
Internal Server Error
```

### 6. Notas de seguridad

owner se fuerza a la identidad en la normalizacion y en el servicio; los roles no conceden excepciones ([app/schemas.py:41](../app/schemas.py#L41), [app/task_service.py:26](../app/task_service.py#L26)). El insert usa parametros, no interpolacion de valores. No hay restricciones de dominio de estados/prioridades, longitud ni idempotencia: repetir un POST puede crear otra tarea.

La conexion SQLite es compartida por instancia de aplicacion, pero un RLock por conexion protege las lecturas y la transaccion completa de creacion, incluido rollback. Una peticion fallida ya no revierte la insercion de otra sobre esa conexion; la regresion concurrente queda cubierta. No se altera el contrato de requests, campos o codigos HTTP. El bloqueo es local al proceso, no un mecanismo distribuido ([app/task_repository.py:18](../app/task_repository.py#L18), [app/task_repository.py:35](../app/task_repository.py#L35)).

## GET /api/summary

### 1. Que hace

Resume las tareas del usuario autenticado por estado y cuenta las de prioridad alta todavia abiertas ([app/main.py:69](../app/main.py#L69), [app/task_service.py:29](../app/task_service.py#L29)).

### 2. Autenticacion

Si. Enviar `Authorization: Bearer ${TOKEN}` con el JWT de Preparacion. No hay autorizacion adicional por rol para consultar otros usuarios.

### 3. Request

| Campo/parametro | Tipo | Obligatorio | Descripcion |
|---|---|---|---|
| Authorization (header) | string | Si | Bearer seguido de un JWT RS256 valido. |
| owner (query) | string | No | Aceptado por compatibilidad e ignorado; el resumen usa la identidad. |

Sin cuerpo. Ejemplo completo:

```bash
curl --request GET 'http://127.0.0.1:8000/api/summary?owner=trainer' --header "Authorization: Bearer ${TOKEN}"
```

### 4. Response exitosa

HTTP **200**, objeto sin envoltorio.

| Campo | Tipo | Descripcion |
|---|---|---|
| owner | string | Usuario autenticado cuyo resumen se devuelve. |
| total | integer | Cantidad total de sus tareas. |
| byStatus | objeto de string a integer | Cada clave es un estado almacenado y su valor es el conteo. No hay conjunto fijo de claves. |
| highPriorityOpen | integer | Conteo con priority exactamente HIGH y status distinto de DONE y ARCHIVED. Comparacion sensible a mayusculas. |

```json
{
	"owner": "student",
	"total": 2,
	"byStatus": {"TODO": 1, "IN_PROGRESS": 1},
	"highPriorityOpen": 1
}
```

Sin tareas, el resultado completo es:

```json
{"owner": "student", "total": 0, "byStatus": {}, "highPriorityOpen": 0}
```

Campos y agregacion: [app/schemas.py:55](../app/schemas.py#L55), [app/task_service.py:33](../app/task_service.py#L33).

### 5. Respuestas de error

**401**: autenticacion o configuracion invalida.

```json
{"detail": "Invalid token: authentication failed"}
```

**500 JSON**: sqlite3.Error al consultar las filas del resumen.

```json
{"detail": "Task storage unavailable"}
```

**500 no controlado**: error no SQLite durante la agregacion o validacion de la respuesta, por ejemplo datos persistidos incompatibles. Cuerpo estandar text/plain:

```text
Internal Server Error
```

OpenAPI anuncia tambien 422 para validacion de parametros; su escenario HTTP concreto y cuerpo no se han reproducido para esta ruta. Ver Q-1; no se afirma que owner=trainer sea un error de validacion.

### 6. Notas de seguridad

owner nunca elige otra identidad; los agregados no deben exponerse como resumen global. La consulta usa parametros y las reglas se ejecutan en el servicio. Todo el conjunto de filas se carga para calcular el resumen; no hay cache ni limite propio de cantidad. Un estado arbitrario puede aparecer como clave de byStatus y, si no es DONE/ARCHIVED, contar como abierto cuando su prioridad sea HIGH.

## POST /api/requirements

### 1. Que hace

Guarda de forma limitada y sin sobrescribir cargas previas un archivo de requerimientos del usuario y devuelve sus metadatos ([app/requirement_storage.py](../app/requirement_storage.py)).

### 2. Autenticacion

Si. Enviar `Authorization: Bearer ${TOKEN}` con el JWT de Preparacion. owner en la respuesta procede de la identidad, no de un campo de formulario.

### 3. Request

| Campo/parametro | Tipo | Obligatorio | Descripcion |
|---|---|---|---|
| Authorization (header) | string | Si | Bearer seguido de un JWT RS256 valido. |
| Content-Type (header) | string | Si para el ejemplo multipart | multipart/form-data con boundary valido; cURL lo genera al usar --form. No fijarlo manualmente sin boundary. |
| file (formulario) | archivo multipart: bytes y filename | Si | Nombre de campo exacto file. Un campo de texto no sustituye a UploadFile. Enviar filename no vacio. |

No tiene parametros query propios. No enviar JSON/base64 en lugar de multipart. Los campos adicionales de formulario no se usan. Ejemplo completo, con un archivo local requirements.txt de 24 bytes que contiene `Login must be accessible`, sin salto de linea final:

Se admiten .txt, .md y .pdf (tambien mayusculas), nombres simples sin extension y archivos vacios. Por defecto el archivo no puede exceder 5 MiB y el cuerpo completo, con boundaries/campos, 6 MiB. Son limites configurables del servidor. La extension no valida el contenido ni acredita que un archivo sea realmente PDF.

```bash
curl --request POST 'http://127.0.0.1:8000/api/requirements' --header "Authorization: Bearer ${TOKEN}" --form 'file=@requirements.txt;type=text/plain'
```

Contenido exacto del archivo de ejemplo:

```text
Login must be accessible
```

### 4. Response exitosa

HTTP **201**, objeto de metadatos; no devuelve el archivo, un identificador de requerimiento ni una URL de descarga.

| Campo | Tipo | Descripcion |
|---|---|---|
| owner | string | Usuario autenticado. No implica un directorio privado por usuario. |
| fileName | string | Nombre recibido del parser multipart, conservado como metadato. No puede ser null en una carga aceptada. El parser puede eliminar una ruta Windows de cliente antes de la validacion. |
| storedAt | string | Ruta real del archivo, relativa o absoluta segun configuracion y con separadores de la plataforma. El nombre de destino se normaliza y puede llevar sufijo unico en una colision. No es una URL. |
| size | integer | Longitud del contenido leido y escrito, en bytes. |

Ejemplo con WORKSHOP_UPLOAD_DIR=./uploads y separadores POSIX:

```json
{
	"owner": "student",
	"fileName": "requirements.txt",
	"storedAt": "uploads/requirements.txt",
	"size": 24
}
```

En Windows la misma ruta puede serializarse como `"uploads\\requirements.txt"`. Un directorio absoluto produce storedAt absoluto. La ruta actual se verifica en [app/main.py:75](../app/main.py#L75).

Si requirements.txt ya existe, la nueva carga obtiene un destino como uploads/requirements-<identificador-unico>.txt, conservando fileName="requirements.txt" y sin alterar los bytes del archivo anterior. No debe suponerse que storedAt termine exactamente en fileName.

### 5. Respuestas de error

**400**: el parser rechaza el multipart, por ejemplo Content-Type multipart/form-data sin boundary. Otros mensajes 400 del parser dependen del defecto del cuerpo y sus limites internos.

```json
{"detail": "Missing boundary in multipart."}
```

**400, nombre inseguro**: nombre vacio, ruta/unidad/separadores, traversal, controles o nombre reservado; tambien un destino simbolico/junction o fuera del directorio. La validacion opera sobre el nombre recibido del parser, tras decodificacion porcentual y normalizacion Unicode NFKC.

```json
{"detail": "Invalid filename"}
```

**400, extension no permitida**:

```json
{"detail": "File extension not allowed"}
```

**401**: autenticacion o configuracion invalida, si el parsing previo no ha fallado.

```json
{"detail": "Invalid token: authentication failed"}
```

**422, file ausente**, incluso si se envio un formulario con otro nombre de campo:

```json
{"detail": [{"type": "missing", "loc": ["body", "file"], "msg": "Field required", "input": null}]}
```

**422, file es texto y no archivo**, ejemplo al recibir el string content:

```json
{"detail": [{"type": "value_error", "loc": ["body", "file"], "msg": "Value error, Expected UploadFile, received: <class 'str'>", "input": "content", "ctx": {"error": {}}}]}
```

**413**: el archivo supera su limite o el multipart completo supera su limite antes de entrar al parser. La igualdad con el limite se permite. No se confia en Content-Length; un valor falso no evita el contador real.

```json
{"detail": "Upload too large"}
```

**500 JSON**: fallo I/O de recepcion, lectura, escritura o limpieza, o agotamiento de intentos de destino exclusivo. El mensaje no expone la excepcion ni rutas internas.

```json
{"detail": "Requirement storage unavailable"}
```

Fallos inesperados fuera de esos errores manejados aun pueden producir el 500 text/plain global; no debe asumirse JSON para toda excepcion no controlada. No hay 415 propio por MIME ni 409 propio por colision. Los limites adicionales del proxy/servidor externo no forman parte de esta politica.

### 6. Notas de seguridad

La carga valida el nombre, confina el destino y usa creacion exclusiva, limites de archivo/cuerpo y copias en bloques. El cuerpo se recibe en un temporal acotado antes del parser y las escrituras se ejecutan en threadpool. Al exceder el limite, fallar o cancelarse se cierran recursos y se intenta eliminar solo el parcial de esa operacion, sin borrar cargas previas. El directorio sigue compartido entre usuarios, pero las colisiones no sobrescriben datos. Debe estar bajo control del proceso; no se promete proteccion frente a un administrador local que modifique el directorio maliciosamente. No existe registro de estas cargas en SQLite ni endpoint para recuperarlas. La revision SCA de dependencias sigue siendo un item distinto y pendiente.

## GET /api/backend-health

### 1. Que hace

Consulta la salud del backend configurado y devuelve al usuario el codigo y el texto de su respuesta ([app/main.py:81](../app/main.py#L81)).

### 2. Autenticacion

Si. Enviar `Authorization: Bearer ${TOKEN}`. La identidad se usa para requestedBy; el token no se reenvia al backend remoto.

### 3. Request

| Campo/parametro | Tipo | Obligatorio | Descripcion |
|---|---|---|---|
| Authorization (header) | string | Si | Bearer seguido de un JWT RS256 valido. |

Sin cuerpo ni query propios. El cliente no selecciona la URL: procede de AUTH_HEALTH_URL o http://localhost:8080/q/health. La llamada remota es GET y recibe timeout=3.0 de urllib3; ese parametro no constituye una promesa de tiempo total de extremo a extremo.

```bash
curl --request GET 'http://127.0.0.1:8000/api/backend-health' --header "Authorization: Bearer ${TOKEN}"
```

### 4. Response exitosa

HTTP **200**, siempre que la autenticacion sea correcta y la ruta termine. status en el cuerpo es el codigo remoto, no el HTTP de esta API.

| Campo | Tipo | Descripcion |
|---|---|---|
| requestedBy | string | Usuario autenticado que solicito la consulta. |
| status | integer | Codigo HTTP remoto; 0 si se capturo una excepcion. No hay un enum propio. |
| body | string | Texto remoto decodificado como UTF-8, sin parsearlo como JSON; en fallo, str(exception). |

Ejemplo completo si el backend remoto devuelve HTTP 200 y el texto {"status":"UP"}:

```json
{
	"requestedBy": "student",
	"status": 200,
	"body": "{\"status\":\"UP\"}"
}
```

Campos y tratamiento de respuesta: [app/main.py:84](../app/main.py#L84), [app/main.py:85](../app/main.py#L85).

### 5. Respuestas de error

**401**: autenticacion o configuracion invalida; no se debe consultar el backend.

```json
{"detail": "Invalid token: authentication failed"}
```

**HTTP 200 con fallo logico, status=0**: excepcion dentro del try, incluidos fallos de red/timeout, URL rechazada por urllib3 o decodificacion UTF-8. Ejemplo verificable simulando HTTPError('Backend unavailable'); el mensaje real depende de la excepcion:

```json
{"requestedBy": "student", "status": 0, "body": "Backend unavailable"}
```

**HTTP 200 con status remoto no exitoso**: si urllib3 devuelve una respuesta remota de error, se conserva su codigo/texto sin traducirlo a 502/503 de esta API. Ejemplo completo con respuesta remota HTTP 503:

```json
{"requestedBy": "student", "status": 503, "body": "{\"status\":\"DOWN\"}"}
```

**500 fuera del control propio de la ruta**: un fallo no capturado en una dependencia o middleware puede generar el cuerpo estandar text/plain. Las excepciones del bloque de consulta remoto si se capturan y producen el 200/status=0 anterior; no documentar un 500 como su respuesta normal.

```text
Internal Server Error
```

OpenAPI anuncia 422 por validacion del header; no se identifico un caso HTTP reproducible con un header string. Ver Q-1. La ruta no define HTTP 502, 503 ni 504 propios por fallos remotos.

### 6. Notas de seguridad

La consulta requiere identidad, pero devuelve el texto remoto completo y el texto de excepciones, que pueden revelar detalles internos. No hay limite propio de bytes de respuesta ni streaming; se accede a response.data y se decodifica completa. La biblioteca urllib3 fijada tiene avisos pendientes de revision SCA. No proporcionar URLs no confiables en AUTH_HEALTH_URL ni exponer esta API de laboratorio a Internet. El endpoint no acredita por si mismo que el emisor entregue JWT compatibles.

## Preguntas abiertas

- **Q-1:** OpenAPI genera una respuesta 422 para las rutas GET por sus headers/query tipados, pero el codigo usa strings sin restricciones y las pruebas HTTP ordinarias no reprodujeron ese estado. Que request real lo activa y cual seria su cuerpo? No se inventa un ejemplo operativo de 422 para esas rutas.
- **Q-2 (defensa local resuelta):** UploadFile.filename es nullable en la biblioteca, pero el servicio rechaza None o vacio; una carga aceptada devuelve fileName string. Los formularios sin archivo siguen produciendo 422; no se afirma que HTTP pueda enviar un archivo con filename null sin pasar por la validacion del parser.
- **Q-3:** El componente ya fija limites configurables de archivo/cuerpo y extensiones segun la politica anterior. Que limites adicionales aplicaran proxy, servidor y almacenamiento del despliegue, y que limite tendran las respuestas remotas? Eso no fue configurado ni verificado aqui.
- **Q-4:** Como obtiene el integrador un JWT del emisor externo con este perfil? No hay endpoint local de emision, ni se verifico la integracion del backend externo. No se debe reutilizar el token Base64 legacy.

## Documentos consultados

[README.md](../README.md), [PLAN.md](../PLAN.md), [HALLAZGOS.md](../HALLAZGOS.md) y la version previa de este documento. Cada campo y regla se contrasto con las rutas, modelos, seguridad, servicio y repositorio enlazados; los cuerpos de error se comprobaron con TestClient y recursos aislados dentro del repositorio. Esta actualizacion es solo documentacion.