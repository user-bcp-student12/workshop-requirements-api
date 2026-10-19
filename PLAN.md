# Plan de correccion de hallazgos de severidad alta

## Alcance y condiciones

Propuesta exclusivamente documental para H-01, H-02, H-03 y H-04 de [HALLAZGOS.md](HALLAZGOS.md), seleccionados por severidad alta y estado Pendiente. Se interpreta H.04 del pedido como H-04. Este plan no implementa cambios ni sustituye el seguimiento: los estados solo se actualizaran en HALLAZGOS.md despues de verificar cada correccion.

Fuentes: [docs/ENDPOINTS.md](docs/ENDPOINTS.md), [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md), [REGLAS.md](REGLAS.md), [app/main.py](app/main.py) y [tests/test_api.py](tests/test_api.py).

- Mantener las cinco rutas, metodos, nombres de parametros y campos JSON; los exitos siguen siendo 200 o 201 segun la ruta. Mantener create_app(db_path, upload_dir), los nombres de variables de entorno existentes y las rutas de documentacion.
- Conservar el encabezado Authorization Bearer, la autenticacion obligatoria en las cinco rutas y los errores JSON con detail. No introducir nuevos requisitos de campos, enums o formatos de fecha durante estas correcciones.
- Antes de tocar codigo productivo, ampliar tests/test_api.py con caracterizacion del comportamiento valido actual y ejecutar esas pruebas sobre el monolito. Las regresiones de seguridad son pruebas distintas: pueden fallar inicialmente y deben pasar tras la correccion; no se debe preservar una vulnerabilidad para mantenerlas verdes.
- Usar exclusivamente recursos temporales dentro del repositorio y datos sinteticos. Configurar WORKSHOP_DB_PATH y WORKSHOP_UPLOAD_DIR antes de importar app.main para evitar efectos sobre los datos habituales; fijar tambien basetemp de pytest dentro del repositorio. Simular HTTP externo, sin consultar otros componentes.
- No modificar docs/ENDPOINTS.md, docs/GOOD_PRACTICES.md ni REGLAS.md en esta propuesta. No incluir H-05, H-06 o H-07 como trabajos independientes; las extracciones y modelos siguientes son solo los necesarios para estos cuatro hallazgos.

### Compatibilidad que debe resolverse antes de implementar

docs/ENDPOINTS.md distingue comportamientos observados de requisitos de seguridad. Aun asi, documenta Base64, seleccion de owner por el cliente y ausencia de limites de carga. Conservar literalmente esos comportamientos es incompatible con corregir H-01, H-02 y H-04.

Este plan conserva la interfaz y los resultados de solicitudes validas y autorizadas. Describe como objetivo los cambios de seguridad, pero no da por autorizada una modificacion de la semantica documentada. Antes de implementarlos, confirmar que las debilidades descritas no son garantias de compatibilidad. Si se exige preservarlas literalmente, esas partes no son ejecutables bajo las restricciones actuales: detenerlas y solicitar una decision, sin editar el contrato ni introducir excepciones inseguras. H-03 puede corregirse internamente sin esta incompatibilidad.

## H-01 - Autenticacion con token verificable

### Hallazgo y problema

H-01, Auth: token Base64 con secreto embebido. El secreto esta en [app/main.py:14](app/main.py#L14); legacy_identity decodifica datos y acepta username y role despues de comparar secreto y timestamp, sin firma, emisor ni audiencia ([app/main.py:19](app/main.py#L19), [app/main.py:22](app/main.py#L22), [app/main.py:24](app/main.py#L24)). Permite fabricar identidades al conocer el secreto. La expiracion ya se comprueba parcialmente; no debe describirse como inexistente.

### Cambio propuesto

1. Separar extraccion estricta del encabezado Bearer, validacion criptografica y construccion de la identidad tipada. Las rutas consumiran la misma dependencia de identidad, sin duplicar verificaciones.
2. Verificar un JWT firmado mediante biblioteca mantenida: firma, algoritmo permitido fijado por configuracion confiable, issuer, audience y exp obligatorio. No aceptar alg=none ni elegir algoritmos o ubicaciones de claves a partir de datos no confiables del token. Comprobar nbf si el emisor lo utiliza y rechazar claims de identidad ausentes o invalidos.
3. Obtener claves de verificacion y configuracion del entorno de laboratorio; nunca incluir secretos reales o claves privadas en el repositorio. Usar un modelo Pydantic interno para identidad y configuracion validada, con mapeo explicito del claim de usuario confirmado por el emisor. No inventar privilegios a partir de role.
4. Traducir excepciones especificas de autenticacion a HTTP 401 con detail generico, manteniendo el prefijo Invalid token: sin exponer el error criptografico. No capturar Exception para ocultar errores de programacion.
5. Retirar el secreto embebido y no mantener un fallback que acepte el Base64 antiguo: permitirlo conservaria el bypass.

**Dependencia y coordinacion previa:** el codigo local no demuestra que el emisor externo entregue JWT. Solicitar fuera del codigo un token de prueba sintetico y la especificacion de algoritmo, clave publica o mecanismo de claves, issuer, audience y claims; no leer ni modificar el otro componente. El cambio de formato Base64 a JWT no es transparente para el emisor. Si este solo emite Base64, no afirmar que H-01 puede resolverse solo en esta API conservando ese token; dejar su implementacion condicionada a una solucion compatible acordada.

**Dependencias nuevas:** justificar PyJWT y, solo si el algoritmo asimetrico lo requiere, su soporte criptografico. La razon es evitar implementar criptografia y validacion JWT manualmente; las dependencias actuales no incluyen un verificador JWT. Seleccionar una version mantenida y revisar sus advisories antes de fijarla en requirements.txt. No instalar nada durante esta fase documental.

### Archivos a tocar

- [app/main.py](app/main.py): conectar la dependencia de identidad verificada a las rutas existentes y conservar create_app.
- Nuevo modulo propuesto app/security.py: validacion, configuracion de autenticacion y excepciones especificas.
- Nuevo modulo compartido propuesto app/schemas.py: modelo de identidad, reutilizado por los siguientes cambios.
- [requirements.txt](requirements.txt): solo la biblioteca JWT justificada, una vez resuelta la coordinacion.
- [tests/test_api.py](tests/test_api.py): fixtures sinteticos de identidad y pruebas de autenticacion.

### Prueba de caracterizacion antes de tocar codigo

Parametrizar las cinco rutas con credenciales legacy validas y verificar sus codigos y esquemas actuales; simular urllib3 para backend-health. Comprobar que username se refleja en owner o requestedBy donde corresponda. Caracterizar ausencia de encabezado, token malformado y expirado: HTTP 401 y detail string, sin fijar textos internos de excepciones como contrato. Estas pruebas legacy describen el punto de partida, no una via de aceptacion que deba sobrevivir a la correccion.

**Regresion posterior:** con reloj controlado y claves solo de prueba, aceptar JWT correcto y rechazar firma alterada, algoritmo no permitido, emisor o audiencia incorrectos, exp ausente o vencido y usuario ausente. Verificar que un Base64 antiguo no autentica y que las cinco rutas usan el mismo control. Adaptar los fixtures al mecanismo acordado sin cambiar las aserciones de negocio y formato.

## H-02 - Autorizacion ligada a la identidad

### Hallazgo y problema

H-02, el cliente puede consultar otro owner. list_tasks y summary priorizan owner del query ([app/main.py:69](app/main.py#L69), [app/main.py:92](app/main.py#L92)); create_task acepta el owner del cuerpo ([app/main.py:83](app/main.py#L83)). No existe una comprobacion que vincule esos valores al usuario autenticado.

### Cambio propuesto

1. Una unica funcion del servicio determinara el propietario efectivo a partir de identity.username verificado. list_tasks, create_task y summary la reutilizaran. Los repositorios recibiran ese propietario explicito y nunca el owner sin verificar de la peticion.
2. Conservar owner como parametro opcional y como campo aceptado en el cuerpo para no alterar la interfaz. La propuesta de seguridad es que no pueda ampliar acceso: omitirlo o indicar el propio usuario mantiene el resultado actual; indicar otro usuario no seleccionara ni asignara datos ajenos. Se propone usar siempre la identidad y conservar 200/201 y los esquemas actuales, sin inventar una respuesta 403 no definida. Esta semantica para owner ajeno requiere la confirmacion de compatibilidad indicada al inicio.
3. No crear excepciones para TRAINER o ADMIN: las convenciones locales exigen consultas por identidad y no definen permisos especiales. Un rol no verificado tampoco puede conceder acceso.
4. Introducir modelos Pydantic de entrada y salida en los puntos modificados. Mantener defaults, campos adicionales ignorados y conversiones a string del contrato actual mediante normalizacion explicita; no confiar en que Pydantic reproduzca str automaticamente ni introducir enums. La conversion de owner recibido nunca definira el propietario persistido.

### Archivos a tocar

- [app/main.py](app/main.py): delegar autorizacion y operaciones de tareas al servicio, conservando firmas HTTP.
- Nuevo modulo propuesto app/task_service.py: propietario efectivo y operaciones de negocio; reutilizado en H-03.
- app/schemas.py, propuesto en H-01: entrada de tarea, respuesta Task y Summary, conservando createdAt y highPriorityOpen como aliases de salida.
- [tests/test_api.py](tests/test_api.py): usuarios aislados, propietarios y esquemas.

### Prueba de caracterizacion antes de tocar codigo

Con dos usuarios y datos distintos, verificar que owner omitido, vacio en query o igual al usuario devuelve sus tareas en orden y su resumen. Caracterizar POST con owner omitido o propio, defaults, conversiones actuales, claves desconocidas ignoradas y los siete campos de la tarea, incluido createdAt. Verificar que las operaciones de un usuario no cambian los datos del otro en los casos autorizados.

**Regresion posterior:** solicitar el owner de otro usuario en GET y enviarlo en POST; verificar que solo se consulta o persiste bajo la identidad autenticada, tambien en summary. Repetir con distintos roles sin conceder privilegios adicionales. Mantener query y campo aceptados, codigos 200/201 y estructura de respuesta. H-02 no se considera cerrado con una identidad todavia falsificable por H-01.

## H-03 - SQL parametrizado

### Hallazgo y problema

H-03, filtros e inserts concatenados. Las entradas llegan a SELECT e INSERT mediante concatenacion ([app/main.py:70](app/main.py#L70), [app/main.py:84](app/main.py#L84), [app/main.py:93](app/main.py#L93)). Ademas de la inyeccion, un titulo legitimo con apostrofo puede romper una creacion.

### Cambio propuesto

1. Extraer exclusivamente la persistencia de tareas a un repositorio con funciones pequenas para listar por propietario, insertar, consultar por id y obtener filas del resumen. Las rutas no contendran SQL. Reutilizar el servicio de H-02 para reglas y los modelos para serializacion, sin crear una segunda implementacion.
2. Usar placeholders ? y parametros separados en todos los valores variables, incluido lastrowid. Mantener nombres de tabla, columnas y ORDER BY id estaticos; no intentar escapar comillas manualmente ni usar f-strings para construir valores SQL.
3. Mantener esquema SQLite, datos iniciales, defaults, datetime('now'), orden y transaccion de creacion. Ejecutar commit al completar la escritura y rollback ante sqlite3.Error, sin convertir errores en exitos ni exponer su texto al cliente.
4. Conservar la conexion por instancia y su cierre actual durante este cambio acotado; no introducir ORM, migraciones ni un rediseño independiente del ciclo de vida. Usar los modelos compatibles para devolver los mismos campos, no filas SQLite crudas.

### Archivos a tocar

- [app/main.py](app/main.py): quitar SQL de las rutas y conectar servicio y repositorio a la conexion existente.
- Nuevo modulo propuesto app/task_repository.py: consultas parametrizadas y transaccion de insercion.
- app/task_service.py y app/schemas.py, propuestos antes: reutilizar reglas y mapeo sin duplicar capas.
- [tests/test_api.py](tests/test_api.py): integracion con SQLite temporal y comprobacion de datos.

### Prueba de caracterizacion antes de tocar codigo

Caracterizar listado ordenado de tareas iniciales, creacion con todos los campos y con defaults, consulta posterior del registro y resumen con estados TODO, IN_PROGRESS, DONE y ARCHIVED. Verificar byStatus y highPriorityOpen, incluso propietario sin tareas. Mantener formato de createdAt sin fijar su instante exacto. No cambiar tipos ni defaults mediante validacion mas restrictiva.

**Regresion posterior:** guardar y recuperar texto legitimo con apostrofos, comillas y caracteres Unicode en titulo y descripcion; comprobar que se conserva literalmente y solo se inserta una tarea. Probar el repositorio con nombres de usuario que contengan esos caracteres para demostrar parametrizacion aunque H-02 impida seleccionar otro owner. Verificar aislamiento por propietario y rollback de una escritura fallida. No incluir payloads de explotacion en la documentacion.

**Dependencias nuevas:** ninguna; sqlite3 y las transacciones existentes son suficientes.

## H-04 - Carga segura de archivos

### Hallazgo y problema

H-04, uso directo de file.filename y ausencia de controles propios. El destino se construye con el nombre recibido, se lee el archivo completo y se escribe sin controlar confinamiento ni colisiones ([app/main.py:109](app/main.py#L109), [app/main.py:110](app/main.py#L110), [app/main.py:111](app/main.py#L111)). Puede escribir fuera de uploads, sobrescribir archivos o agotar memoria y disco.

### Cambio propuesto

1. Separar validacion de nombre y extension, calculo del destino y escritura limitada en un servicio de almacenamiento. La ruta solo recibe el multipart, usa la identidad y serializa el resultado.
2. No utilizar file.filename como ruta: rechazar rutas absolutas, unidades y separadores de Windows o POSIX, componentes de traversal, nombres vacios y nombres reservados. Normalizar el nombre y verificar que el destino resuelto quede dentro del directorio configurado. Evitar enlaces simbolicos y sobrescritura mediante apertura exclusiva; no confiar solo en una comprobacion previa susceptible a carreras. Mantener uploads bajo control del proceso, no de usuarios locales no confiables.
3. Definir lista de extensiones permitidas y limite maximo de bytes mediante configuracion validada y constantes con nombre, junto con el tamano de bloque. El caso ya probado requirements.txt debe seguir permitido. El repositorio no define otros formatos ni el limite: confirmarlos antes de implementar, sin inventar numeros o una allowlist incompatible con cargas legitimas. No confiar en Content-Length ni en el MIME aportado por el cliente.
4. Leer en bloques, contar bytes realmente recibidos y detenerse antes de exceder el limite. Eliminar cualquier archivo parcial y cerrar recursos tanto al fallar como al cancelar la peticion. El limite de lectura no sustituye los limites del parser multipart y de almacenamiento temporal anteriores al handler; verificar tambien esa capa con las dependencias existentes, sin ampliar el ambito.
5. Para un nombre simple y valido no existente, conservar el nombre y la ruta observados. Resolver colisiones sin sobrescribir, mediante un nombre generado por el servidor conservando la extension permitida. Mantener fileName como nombre recibido y storedAt como ruta real, nunca rutas internas de archivos ajenos. En cargas validas seguir devolviendo 201, owner, fileName, storedAt y size.
6. Traducir fallos de validacion a detail generico. Como el contrato no define codigos para extension rechazada, exceso de tamano ni colisiones, acordarlos antes de introducirlos: no dar 400, 413 o 415 por autorizados. La comprobacion de errores nuevos y los cambios de nombre por seguridad quedan sujetos a la condicion de compatibilidad inicial.

### Archivos a tocar

- [app/main.py](app/main.py): delegar la carga y mantener el campo multipart file y la respuesta.
- Nuevo modulo propuesto app/requirement_storage.py: politica validada, normalizacion y escritura limitada, con funciones separadas y constantes con nombre.
- app/schemas.py, propuesto antes: modelo de respuesta de carga con aliases fileName y storedAt.
- [tests/test_api.py](tests/test_api.py): archivos temporales, limites, colisiones y fallos de escritura.

### Prueba de caracterizacion antes de tocar codigo

Ampliar test_uploads_requirement: enviar requirements.txt, verificar HTTP 201, exactamente owner/fileName/storedAt/size, contenido byte a byte y ruta para una primera carga valida. Caracterizar el directorio pasado a create_app y la ausencia del campo file con respuesta 422. No convertir sobrescrituras o rutas peligrosas en comportamientos que deban conservarse.

**Regresion posterior:** con los limites y errores acordados, probar extension permitida y rechazada, variantes de mayusculas, nombre vacio o inseguro en ambas plataformas y destino fuera del directorio. Probar tamano exactamente en el limite y un byte por encima, sin aceptar un Content-Length falso. Comprobar que dos cargas homonimas no pierden datos y que no quedan parciales despues de exceso de tamano, fallo de escritura o cancelacion. Verificar que la lectura usa bloques y no una lectura ilimitada. Todos los archivos y verificaciones deben permanecer en el directorio temporal de pruebas dentro del repositorio.

**Dependencias nuevas:** ninguna propuesta; pathlib, os, mecanismos de nombres unicos de la biblioteca estandar y UploadFile bastan. Una dependencia futura requeriria una justificacion separada.

## Secuencia y verificacion

1. Resolver las condiciones de compatibilidad, el mecanismo del emisor y la politica de archivos sin inspeccionar otros componentes ni editar contratos. H-03 y la caracterizacion pueden avanzar sin esperar a la emision JWT.
2. Escribir y ejecutar primero las pruebas de caracterizacion en tests/test_api.py. Reutilizar fixtures y helpers existentes; no crear archivos de pruebas redundantes ni fijar vulnerabilidades como expectativas permanentes.
3. Implementar H-03 como cambio interno acotado; despues H-01 y H-02 de forma coherente, y H-04 con su politica acordada. Integrar las extracciones compartidas una sola vez. Ejecutar las pruebas del hallazgo inmediatamente despues de cada cambio y luego la suite completa.
4. Mantener una responsabilidad por funcion, nombres de dominio, excepciones especificas, retornos anticipados y constantes con nombre. Para el calculo de highPriorityOpen usar una condicion combinada sin cambiar su significado; no aprovechar este trabajo para refactorizar backend-health u otros hallazgos.
5. Medir cobertura de ramas y lineas con pytest-cov, ya disponible en desarrollo. Exigir al menos 85% del codigo modificado y cubrir sus rutas de rechazo y limpieza; un porcentaje global no sustituye comprobar la cobertura del cambio. Guardar reportes y temporales dentro del repositorio.
6. Comparar rutas, parametros, aliases JSON, codigos acordados y esquemas con las caracterizaciones. Cualquier cambio adicional de contrato detiene el trabajo; no se actualiza docs/ENDPOINTS.md para hacer pasar pruebas.
7. Solo tras verificar cada correccion, actualizar su fila en HALLAZGOS.md con la evidencia y estado correspondiente. PLAN.md describe la propuesta, no lleva estados ni declara hallazgos resueltos.