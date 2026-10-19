# Plan de correccion - pendientes de mayor severidad

Propuesta documental del 2026-10-19 para este repositorio. Se seleccionan **H-03 y H-04**, los unicos items de [HALLAZGOS.md](HALLAZGOS.md) con severidad alta y estado Pendiente. H-01/H-02 ya estan resueltos para el perfil JWT aislado aprobado; H-05/H-06/H-07 no forman parte de esta tanda. Los estados se siguen exclusivamente en HALLAZGOS.md, no en este plan.

Esta version sustituye el plan anterior por el trabajo que falta. Se conservan como antecedentes las aprobaciones humanas del 2026-10-19 al plan anterior y a H-01/H-02 con el perfil JWT RS256 aislado. No equivalen a aprobar nuevas politicas de carga ni automaticamente esta propuesta actualizada. La configuracion JWT vigente esta documentada en [docs/ENDPOINTS.md](docs/ENDPOINTS.md) y no se modifica.

Se consultaron primero el contrato actual y [docs/GOOD_PRACTICES.md](docs/GOOD_PRACTICES.md). Tambien rigen [REGLAS.md](REGLAS.md): una responsabilidad por funcion, tipos/modelos Pydantic donde corresponda, sin duplicacion, sin anidamiento profundo ni valores magicos. Esta fase cambia solamente PLAN.md; no modifica codigo, pruebas, dependencias, contratos ni estados.

Preservar las cinco rutas, metodos, parametros, campos JSON, defaults, JWT actual, autorizacion por identidad y codigos de exito. Implementar y verificar cada item por separado: pruebas primero, cambio despues y validacion focalizada inmediata. No introducir ORM, dependencias nuevas, exclusiones de scanner, xfail/skip ni secretos reales. Temporales, bases, cargas y reportes quedaran dentro de este repositorio; configurar WORKSHOP_DB_PATH y WORKSHOP_UPLOAD_DIR antes de importar la aplicacion. No consultar otros componentes.

## Item: H-03 - Aislamiento de transacciones concurrentes

### Item y problema

H-03 conserva el titulo historico "SQL: filtros e inserts concatenados", pero la parametrizacion ya esta corregida. El pendiente actual es el aislamiento de la conexion compartida: el rollback de B puede eliminar el insert de A mientras A devuelve 201. No se propone rehacer consultas ya parametrizadas.

Evidencia: [app/main.py:35](app/main.py#L35) y [app/main.py:48](app/main.py#L48) comparten una conexion y repositorio por aplicacion. La transaccion no tiene exclusion mutua entre insert, recuperacion de fila, commit y rollback ([app/task_repository.py:29](app/task_repository.py#L29), [app/task_repository.py:34](app/task_repository.py#L34), [app/task_repository.py:37](app/task_repository.py#L37), [app/task_repository.py:40](app/task_repository.py#L40)). Existe una regresion fallida en [tests/test_api.py:730](tests/test_api.py#L730).

### Cambio propuesto y alcance propio

1. Crear e inyectar un **threading.RLock por conexion/instancia de aplicacion**, nunca uno global del modulo. Todos los accesos del repositorio a esa conexion usaran el mismo bloqueo.
2. Proteger la transaccion completa: INSERT -> recuperacion de fila -> commit, o rollback antes de liberar el bloqueo. Proteger tambien list_tasks, get_task y summary_rows para evitar leer datos sin confirmar de otra peticion. RLock permite la llamada interna create_task -> get_task sin interbloqueo.
3. Mantener esquema, datos iniciales, SQL parametrizado, owner por identidad, orden, modelos, defaults y formatos. Mantener sqlite3.Error como HTTP 500 JSON con detail generico; una operacion no debe confirmar o revertir otra. No adquirir bloqueos distintos para la misma conexion ni duplicar gestion de transacciones en las rutas.
4. Conservar el ensamblaje en create_app y la persistencia en el repositorio, con funciones pequenas y excepciones especificas. El bloqueo local protege la conexion de ese proceso; conexiones de otros procesos siguen sujetas al aislamiento de SQLite, no a una supuesta proteccion distribuida del RLock.

### Archivos que se van a tocar

- [app/main.py](app/main.py): crear e inyectar el bloqueo compartido, preservando create_app(db_path, upload_dir) y su ciclo de vida.
- [app/task_repository.py](app/task_repository.py): sincronizar lecturas y la transaccion completa.
- [tests/test_api.py](tests/test_api.py): pruebas concurrentes y caracterizacion, reutilizando fixtures existentes.
- [docs/TESTING.md](docs/TESTING.md): resultados, cantidades, comandos, codigos de salida y cobertura realmente ejecutados.
- [docs/ENDPOINTS.md](docs/ENDPOINTS.md): solo retirar/actualizar la nota del defecto concurrente cuando deje de reproducirse; sin redefinir rutas, requests, respuestas o codigos.
- [HALLAZGOS.md](HALLAZGOS.md): evidencia y estado de H-03 solo despues de verificar la correccion.

No tocar security, schemas, task_service, requirements.txt ni archivos de carga para este item. No mezclar su cambio con H-04.

### Pruebas antes de tocar codigo productivo

**Caracterizacion:** ejecutar las pruebas actuales de listado, creacion, resumen, defaults, fechas, SQL literal e IDOR. Registrar la linea base; no cambiar expectativas de negocio ni el perfil JWT.

**Regresion principal:** ejecutar primero test_known_bug_h03_concurrent_rollback_preserves_success y registrar su fallo. Revisar su coordinacion antes del cambio: hoy espera que B termine mientras A esta detenida esperando una senal que se emite despues de B. Una solucion que correctamente serialice B detras de A no puede cumplir esa secuencia; no confundir ese interbloqueo del test con un defecto de persistencia.

Escribir una prueba que lance ambas peticiones con futuros, coordine el intercalado con eventos y libere A sin exigir que B finalice mientras A retiene el recurso. Comprobar exclusion de la seccion transaccional y conservar las aserciones de resultado: A devuelve 201 y permanece listada, B devuelve 500 generico y no persiste, y las tareas previas/ajenas siguen intactas. Demostrar contra el codigo previo que la nueva coordinacion detecta la falta de aislamiento antes de sustituir la antigua. No limitarse a quitar esperas o relajar aserciones para obtener verde. Usar tiempos maximos nombrados solo para detectar interbloqueos, sin sleeps ni carreras aleatorias.

**Regresiones complementarias:** lectura/listado/resumen que no observen inserts sin confirmar; dos creaciones concurrentes validas persistidas; creacion rechazada seguida de otra valida; aplicaciones con bases diferentes sin bloqueo global compartido. Liberar las operaciones que deban esperar antes de pedir sus resultados para no introducir interbloqueos en los tests.

### Verificacion de cierre y dependencias

Tras cada cambio, ejecutar las pruebas focalizadas y despues la suite completa, incluida la regresion hoy fallida. Exigir al menos 85% en lineas y ramas modificadas, tambien rollback; comparar OpenAPI y respuestas validas con las caracterizaciones. Registrar cantidades y resultados antes/despues sin ocultar fallos. Solo cerrar H-03 si no se pierden datos ni se producen interbloqueos en el intercalado controlado.

No hacen falta dependencias nuevas: threading y sqlite3 son biblioteca estandar. Si la solucion exige otro modelo de conexiones o archivos ajenos a esta lista, revisar el alcance antes de incorporarlo.

## Item: H-04 - Carga segura de archivos

### Item y problema

H-04: "Files: uso directo de file.filename sin controles de nombre, extension o tamano". La ruta usa el nombre recibido como destino, lee todo en memoria y escribe sin confinamiento ni control de colisiones ([app/main.py:74](app/main.py#L74), [app/main.py:75](app/main.py#L75), [app/main.py:76](app/main.py#L76), [app/main.py:77](app/main.py#L77)). No incluye resolver SCA de H-05 ni errores de salud de H-06.

### Cambio propuesto y alcance propio

1. Extraer un servicio de almacenamiento con funciones separadas para politica, validacion/normalizacion del nombre, destino seguro y escritura limitada. La ruta conserva el campo multipart file, identidad JWT y exito 201 con owner/fileName/storedAt/size.
2. Rechazar nombres vacios, rutas absolutas, unidades, separadores Windows/POSIX, traversal y nombres reservados. Verificar confinamiento bajo el directorio configurado; no esconder una ruta peligrosa mediante basename silencioso. Mantener nombres simples validos y fileName recibido como metadato.
3. Abrir de forma exclusiva y evitar sobrescrituras. Propuesta de colisiones: conservar el primer nombre seguro y generar sufijo unico del servidor para los siguientes, preservando extension permitida; storedAt refleja el destino real. Comprobar enlaces simbolicos/reparse points y carreras entre comprobar y abrir segun garantias de plataforma. El directorio debe quedar bajo control del proceso; no prometer proteccion frente a un administrador local malicioso.
4. Leer en bloques contando bytes reales, sin confiar en Content-Length o MIME. Cerrar recursos y eliminar solo los parciales de esa operacion al fallar, cancelar o superar el limite. Evitar escritura sincrona bloqueante dentro del handler async utilizando las utilidades threadpool ya disponibles en Starlette.
5. Limitar tambien la recepcion **antes del parser multipart**: FastAPI resuelve UploadFile antes de ejecutar el handler. Limitar solo file.read no protege el espacio temporal ya consumido. Integrar un contador real de cuerpo limitado a POST /api/requirements y asegurar limpieza del parser. Diferenciar bytes maximos del archivo de bytes maximos del multipart, que incluye boundary y otros campos.
6. Definir politica validada y constantes con nombre para extensiones, limite de archivo, limite de cuerpo y tamano de bloque. No inventar valores como requisitos existentes. Preservar el archivo vacio y el nombre simple sin extension documentados, salvo aprobacion expresa de restricciones adicionales propias de H-04.
7. Usar un modelo Pydantic de respuesta con aliases fileName y storedAt. Mantener owner ligado a identidad. Traducir errores de almacenamiento con mensajes genericos segun el contrato de rechazo que se acuerde; no exponer rutas internas/excepciones. No cambiar SQL, resumen, autenticacion ni privilegios de roles.

### Compatibilidad y decisiones previas de este item

Politica confirmada por el usuario durante la implementacion el 2026-10-19: archivo 5 MiB, cuerpo multipart 6 MiB, bloques 64 KiB; extensiones .txt/.md/.pdf y nombres sin extension, admitiendo archivo vacio; 400 JSON detail generico para nombre/extension invalidos, 413 para ambos limites, 500 JSON generico para I/O; colisiones con sufijo unico sin sobrescritura. fileName conserva el nombre recibido y storedAt indica el destino real. Estos valores seran configurables; se autoriza actualizar exclusivamente el contrato de carga con esos cambios.

H-04 pide explicitamente controlar nombre, extension y tamano: requiere restringir entradas hoy aceptadas, no es un refactor transparente. Solo este item permite proponer esos ajustes de seguridad, no cambiar otros endpoints o formatos de exito.

Confirmar antes de implementar: extensiones permitidas y tratamiento de nombre sin extension, ambos limites de bytes, tamano de bloque, politica de colisiones y codigos/cuerpos de rechazo o fallo I/O. Propuesta a evaluar: 400 con detail string generico para nombre/extension invalidos y 413 con detail string generico por exceso de tamano. Son propuestas, no respuestas propias ya existentes. El sufijo de colision evitaria introducir un 409.

Mientras falten esas decisiones, avanzar solo en caracterizacion y preparacion compatibles. No introducir 413/415/409, prohibir el caso sin extension, alterar fileName o reemplazar 500 text/plain por JSON sin autorizacion especifica de H-04. Actualizar el contrato unicamente con los cambios de carga acordados durante su implementacion. Si se exige preservar literalmente ausencia de limites y sobrescritura, no se puede cerrar H-04: elevar la incompatibilidad en vez de ocultarla en los tests.

### Archivos que se van a tocar

- [app/main.py](app/main.py): delegar almacenamiento e integrar control de recepcion solo para esta ruta, conservando su firma y variables existentes.
- Nuevo modulo propuesto app/requirement_storage.py: politica, nombre/confinamiento, destinos exclusivos, escritura en bloques y limpieza; sin utilidades generales innecesarias.
- [app/schemas.py](app/schemas.py): respuesta de carga y configuracion validada si se comparte con el ensamblaje; no endurecer modelos de tareas ni sus conversiones actuales.
- [tests/test_api.py](tests/test_api.py): pruebas HTTP, parser y almacenamiento de H-04 con fixtures y recursos temporales existentes.
- [docs/ENDPOINTS.md](docs/ENDPOINTS.md): solo politica y errores de carga expresamente aprobados; los otros cuatro endpoints quedan intactos.
- [docs/TESTING.md](docs/TESTING.md): comandos, resultados antes/despues y pendientes propios de H-04, sin presentar resultados historicos como nuevas ejecuciones.
- [HALLAZGOS.md](HALLAZGOS.md): nota, evidencia y estado solo tras verificar esta correccion.

No tocar task_repository, task_service, security, requirements.txt ni workflows para H-04. Una dependencia/modulo adicional para recepcion o enlaces requiere justificacion y revisar el alcance antes de agregarlo.

### Pruebas antes de tocar codigo productivo

**Caracterizacion:** ejecutar test_uploads_requirement y las pruebas contract de archivo vacio/sin extension, file ausente/texto, filename vacio, boundary invalido y errores I/O. Ampliar primero el caso feliz para verificar bytes, owner, fileName, storedAt, size y directorio configurado. Registrar cuerpos/codigos actuales; modificar una expectativa de rechazo solo tras aprobar ese cambio de seguridad concreto.

**Regresiones de seguridad:** nombres de ruta POSIX/Windows, traversal, nombres reservados y enlaces fuera del directorio deben rechazarse sin escribir fuera de los temporales locales. Dos cargas benignas homonimas no deben destruir el contenido previo y cada storedAt debe describir su archivo. Ejecutar antes del cambio y registrar los fallos reales; no esperar una sobrescritura exitosa para hacer verde la suite.

**Regresiones de politica, una vez acordada y antes de tocar produccion:** extension permitida/rechazada y mayusculas; limite de archivo exacto y un byte mas; limite total multipart con overhead; Content-Length falso/ausente; cleanup tras error/cancelacion. Comprobar con mocks que la lectura solicita bloques acotados y con ASGI/multipart real que el control no empieza solamente despues del parser. No enviar archivos gigantes ni efectuar pruebas destructivas fuera del repositorio.

**Aislamiento de alcance:** verificar JWT obligatorio y owner por identidad; el control de recepcion no debe modificar POST /api/tasks ni rutas GET. Simular servicios externos sin inspeccionar otros componentes.

### Verificacion de cierre y dependencias

Validar primero H-04 y despues la suite completa, conservando visibles los bugs de otros items aun pendientes. Exigir al menos 85% de lineas y ramas modificadas, incluyendo rechazos, colision, cleanup y cancelacion. Para cargas validas, exigir mismo 201 y mismos cuatro campos; para rechazos nuevos, coincidir exactamente con la politica acordada y documentada. No cerrar H-04 con solo limpiar filename: nombre, extension, tamano y escritura segura deben estar controlados, incluida la recepcion previa al parser cuando corresponda.

Sin dependencias nuevas propuestas: pathlib/os, nombres unicos de biblioteca estandar, Pydantic y utilidades existentes de Starlette. Los valores de politica y las condiciones de plataforma siguen abiertos; no son seguridad ya implementada ni autorizacion para actualizar H-05.