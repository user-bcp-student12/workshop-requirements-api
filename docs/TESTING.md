# Pruebas de la API

Ejecucion real del 2026-10-19 contra [ENDPOINTS.md](ENDPOINTS.md). Solo se ampliaron pruebas y documentacion: no se modifico el codigo productivo ni el contrato. Se reutilizaron fixtures y helpers de [tests/test_api.py](../tests/test_api.py), sin agregar dependencias.

**Resultado mas reciente, tras H-03 y H-04: 186 aprobados, codigo de salida 0.** Los resultados previos de 147 aprobados y de 142 aprobados/1 fallido se conservan como evidencia historica abajo. No se oculto la regresion con xfail/skip. Los estados se mantienen exclusivamente en [HALLAZGOS.md](../HALLAZGOS.md).

## Matriz de casos ejecutados

Los nombres test_ identifican funciones reales del modulo. Los casos parametrizados cuentan por separado; los errores provocados mediante SQLite, mocks o override de dependencia comprueban el manejo HTTP, no suponen un endpoint de administracion nuevo.

| endpoint | caso | tipo | resultado esperado |
|---|---|---|---|
| GET /api/tasks | test_lists_seeded_tasks y test_h03_characterization_lists_in_order | Camino feliz | 200, tareas propias ordenadas, siete campos y createdAt valido. |
| GET /api/tasks | test_h03_characterization_empty_owner | Borde | Identidad sin tareas: 200 y []. |
| GET /api/tasks | test_h02_correction_foreign_queries_use_identity, distintos usuarios/roles | Seguridad / error de autorizacion prevenido | owner ajeno no concede acceso; 200 solo con ids propios. No se inventa 403. |
| GET /api/tasks | test_h01_characterization_rejects_invalid_credentials y test_contract_unauthorized_requests_have_no_business_side_effects | Error 401 | JSON detail generico; sin escritura ni llamadas externas. |
| GET /api/tasks | test_contract_sqlite_errors_are_generic | Error 500 JSON | detail = Task storage unavailable. |
| GET /api/tasks | test_contract_invalid_stored_values_return_plain_500 | Error 500 no controlado | Datos SQLite incompatibles: text/plain, Internal Server Error. |
| POST /api/tasks | test_creates_task_and_summary y test_h03_characterization_creates_and_persists | Camino feliz | 201, propietario autenticado, campos persistidos y fecha valida. |
| POST /api/tasks | test_h03_characterization_creates_and_persists con {} | Borde | Defaults title/description vacios, TODO y MEDIUM; 201. |
| POST /api/tasks | test_h02_correction_foreign_creation_uses_identity y test_h02_correction_ignores_untrusted_owner_values | Seguridad | owner ajeno/null/numerico/lista no controla el propietario; 201 con identidad. |
| POST /api/tasks | test_contract_create_task_invalid_bodies, bytes no decodificables | Error 400 | detail = There was an error parsing the body. |
| POST /api/tasks | test_h01_characterization_rejects_invalid_credentials y test_contract_unauthorized_requests_have_no_business_side_effects | Error 401 | Rechazo de credenciales sin crear tareas. |
| POST /api/tasks | test_contract_create_task_invalid_bodies, ausente/null/array/string | Error 422 | detail con missing o dict_type, loc e input del cuerpo. |
| POST /api/tasks | test_contract_create_task_invalid_bodies, JSON malformado | Error 422 | json_invalid, loc [body, 1] y contexto de parsing. |
| POST /api/tasks | test_contract_body_parsing_can_precede_authentication | Borde / error 422 | JSON malformado sin token puede dar 422 antes de 401. |
| POST /api/tasks | test_contract_sqlite_errors_are_generic y test_h03_correction_rolls_back_failed_insert | Error 500 JSON | Excepcion SQLite traducida a detail generico. |
| POST /api/tasks | test_contract_create_task_encoding_error_returns_plain_500 | Error 500 no controlado | String no codificable en SQLite: text/plain, Internal Server Error. |
| POST /api/tasks | test_known_bug_h03_concurrent_rollback_preserves_success | Regresion de bug | Una tarea devuelta con 201 debe seguir persistida despues del rollback de otra peticion. Pasa tras el aislamiento H-03; conserva su nombre historico. |
| GET /api/summary | test_h03_characterization_summary_states | Camino feliz | total/byStatus correctos; HIGH excluye DONE y ARCHIVED. |
| GET /api/summary | test_h03_characterization_empty_owner | Borde | 200, total/highPriorityOpen=0 y byStatus={}. |
| GET /api/summary | test_h02_correction_foreign_queries_use_identity | Seguridad | owner ajeno no expone agregados ajenos; 200 con identidad propia. |
| GET /api/summary | test_h01_characterization_rejects_invalid_credentials y test_contract_unauthorized_requests_have_no_business_side_effects | Error 401 | detail generico y sin efectos de negocio. |
| GET /api/summary | test_contract_sqlite_errors_are_generic | Error 500 JSON | detail = Task storage unavailable. |
| GET /api/summary | test_contract_invalid_stored_values_return_plain_500 | Error 500 no controlado | Status SQLite incompatible: text/plain, Internal Server Error. |
| POST /api/requirements | test_uploads_requirement y test_h01_characterization_authenticated_routes | Camino feliz | 201, archivo persistido y owner/fileName/storedAt/size. |
| POST /api/requirements | test_contract_upload_valid_edge_cases, empty-file | Borde | Archivo de cero bytes: 201, size=0 y contenido vacio en disco. |
| POST /api/requirements | test_contract_upload_valid_edge_cases, no-extension | Borde | Nombre simple sin extension: 201 y bytes/metadatos correctos, sin afirmar que exista politica de extensiones. |
| POST /api/requirements | test_contract_upload_invalid_input, missing-boundary | Error 400 | detail = Missing boundary in multipart. |
| POST /api/requirements | test_h01_characterization_rejects_invalid_credentials y test_contract_unauthorized_requests_have_no_business_side_effects | Error 401 | Rechazo sin escribir en el directorio de cargas. |
| POST /api/requirements | test_contract_upload_invalid_input, missing/wrong-field | Error 422 | file requerido, loc [body, file]. |
| POST /api/requirements | test_contract_upload_invalid_input, text/empty-filename | Error 422 | Expected UploadFile, no un campo string. |
| POST /api/requirements | test_contract_upload_io_errors_return_generic_500, read/write | Error 500 JSON | OSError sintetico de lectura/escritura: detail generico Requirement storage unavailable, sin parciales. Cambio de error aprobado para H-04. |
| GET /api/backend-health | test_contract_backend_health_success_and_request | Camino feliz | 200, status remoto 200 y body string. GET a AUTH_HEALTH_URL con timeout=3.0, sin reenviar Authorization. |
| GET /api/backend-health | test_contract_backend_health_response_edges, empty-body | Borde | Remoto 204 con cuerpo vacio: API HTTP 200, status=204 y body="". |
| GET /api/backend-health | test_h01_characterization_rejects_invalid_credentials y test_contract_unauthorized_requests_have_no_business_side_effects | Error 401 | No se llama al backend. |
| GET /api/backend-health | test_contract_backend_health_remote_exceptions, network/timeout | Error logico, HTTP 200 | status=0 y body string del fallo sintetico. No se inventa HTTP 502/504. |
| GET /api/backend-health | test_contract_backend_health_response_edges, invalid-utf8 | Error logico, HTTP 200 | Fallo de decodificacion: status=0 y body string no vacio. |
| GET /api/backend-health | test_contract_backend_health_response_edges, remote-503 | Error remoto, HTTP 200 | status=503 y body remoto; el HTTP local sigue siendo 200. |
| GET /api/backend-health | test_contract_backend_health_unhandled_dependency_returns_plain_500 | Error 500 no controlado | Fallo sintetico fuera del try remoto: text/plain, Internal Server Error. |

## Codigo historico de los tests agregados

El bloque siguiente corresponde a la ejecucion original de 143 casos. La coordinacion del ultimo test concurrente fue sustituida antes de implementar H-03: se comprobo roja con el codigo anterior y verde con el bloqueo, sin quitar aserciones de persistencia. La fuente vigente es tests/test_api.py; los resultados actuales figuran al final en "Aislamiento H-03".

La fuente ejecutable completa es [tests/test_api.py](../tests/test_api.py). Este bloque es la seccion nueva de ese modulo, no un modulo independiente: reutiliza task_client, headers, call_api y API_CASES ya existentes. Las importaciones complementarias son sqlite3, ThreadPoolExecutor, Event, Mock, Response de httpx, StarletteUploadFile, verified_identity y TaskRepository; todas estan presentes en el mismo archivo. Las 27 funciones anteriores se conservaron sin cambiar cuerpos ni aserciones.

```python
def assert_plain_server_error(response: Response) -> None:
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Internal Server Error"


@pytest.mark.parametrize("case", API_CASES[:3])
def test_contract_sqlite_errors_are_generic(task_client: TestClient, case: tuple[str, str, int]) -> None:
    task_client.app.state.connection.close()
    response = call_api(task_client, case, headers())
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Task storage unavailable"}


@pytest.mark.parametrize("path,column", [("/api/tasks", "title"), ("/api/summary", "status")])
def test_contract_invalid_stored_values_return_plain_500(
    task_client: TestClient, path: str, column: str
) -> None:
    statements = {
        "title": "UPDATE tasks SET title = ? WHERE id = 1",
        "status": "UPDATE tasks SET status = ? WHERE id = 1",
    }
    connection = task_client.app.state.connection
    connection.execute(statements[column], (b"\xff",))
    connection.commit()
    assert_plain_server_error(task_client.get(path, headers=headers()))


def test_contract_create_task_encoding_error_returns_plain_500(task_client: TestClient) -> None:
    response = task_client.post(
        "/api/tasks", headers={**headers(), "Content-Type": "application/json"}, content=b'{"title":"\\ud800"}'
    )
    assert_plain_server_error(response)


@pytest.mark.parametrize(
    "content,status,error_type,error_input",
    [
        pytest.param(b"", 422, "missing", None, id="missing"),
        pytest.param(b"null", 422, "missing", None, id="null"),
        pytest.param(b"[]", 422, "dict_type", [], id="array"),
        pytest.param(b'"text"', 422, "dict_type", "text", id="string"),
        pytest.param(b"{", 422, "json_invalid", {}, id="malformed-json"),
        pytest.param(b"\xff", 400, "", None, id="undecodable-body"),
    ],
)
def test_contract_create_task_invalid_bodies(
    task_client: TestClient, content: bytes, status: int, error_type: str, error_input: object
) -> None:
    response = task_client.post(
        "/api/tasks", headers={**headers(), "Content-Type": "application/json"}, content=content
    )
    assert response.status_code == status
    if status == 400:
        assert response.json() == {"detail": "There was an error parsing the body"}
        return
    error = response.json()["detail"][0]
    assert error["type"] == error_type
    assert error["input"] == error_input
    assert error["loc"] == (["body", 1] if error_type == "json_invalid" else ["body"])
    if error_type == "json_invalid":
        assert error["msg"] == "JSON decode error"
        assert error["ctx"]["error"] == "Expecting property name enclosed in double quotes"


def test_contract_body_parsing_can_precede_authentication(task_client: TestClient) -> None:
    response = task_client.post("/api/tasks", headers={"Content-Type": "application/json"}, content="{")
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "json_invalid"


@pytest.mark.parametrize(
    "filename,content", [("requirements.txt", b""), ("requirements", b"Requirement")], ids=["empty-file", "no-extension"]
)
def test_contract_upload_valid_edge_cases(task_client: TestClient, filename: str, content: bytes) -> None:
    response = task_client.post(
        "/api/requirements", headers=headers(), files={"file": (filename, content, "text/plain")}
    )
    assert response.status_code == 201
    destination = Path(task_client.app.state.upload_dir) / filename
    assert response.json() == {
        "owner": "student", "fileName": filename, "storedAt": str(destination), "size": len(content)
    }
    assert destination.read_bytes() == content


@pytest.mark.parametrize("input_case", ["missing", "wrong-field", "text", "empty-filename", "missing-boundary"])
def test_contract_upload_invalid_input(task_client: TestClient, input_case: str) -> None:
    request_headers = headers()
    options = {}
    if input_case == "wrong-field":
        options = {"files": {"other": ("requirements.txt", b"content")}}
    if input_case == "text":
        options = {"data": {"file": "content"}}
    if input_case == "empty-filename":
        options = {"files": {"file": ("", b"content", "text/plain")}}
    if input_case == "missing-boundary":
        request_headers["Content-Type"] = "multipart/form-data"
        options = {"content": b"body"}
    response = task_client.post("/api/requirements", headers=request_headers, **options)
    if input_case == "missing-boundary":
        assert response.status_code == 400
        assert response.json() == {"detail": "Missing boundary in multipart."}
        return
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "file"]
    if input_case in {"missing", "wrong-field"}:
        assert error == {"type": "missing", "loc": ["body", "file"], "msg": "Field required", "input": None}
        return
    assert error["type"] == "value_error"
    assert error["input"] == "content"
    assert error["msg"] == "Value error, Expected UploadFile, received: <class 'str'>"


@pytest.mark.parametrize("failure", ["read", "write"])
def test_contract_upload_io_errors_return_plain_500(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    filename = "write-target"
    if failure == "write":
        (Path(task_client.app.state.upload_dir) / filename).mkdir()
    if failure == "read":
        async def failed_read(self: StarletteUploadFile, size: int = -1) -> bytes:
            raise OSError("Synthetic read failure")
        monkeypatch.setattr(StarletteUploadFile, "read", failed_read)
    response = task_client.post(
        "/api/requirements", headers=headers(), files={"file": (filename, b"Requirement")}
    )
    assert_plain_server_error(response)


def test_contract_backend_health_success_and_request(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = Mock(return_value=SimpleNamespace(status=200, data=b'{"status":"UP"}'))
    monkeypatch.setattr(urllib3.PoolManager, "request", request)
    monkeypatch.setenv("AUTH_HEALTH_URL", "http://backend.test/health")
    response = task_client.get("/api/backend-health", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"requestedBy": "student", "status": 200, "body": '{"status":"UP"}'}
    request.assert_called_once_with("GET", "http://backend.test/health", timeout=3.0)


@pytest.mark.parametrize(
    "remote_status,content,expected_status,expected_body",
    [(204, b"", 204, ""), (503, b'{"status":"DOWN"}', 503, '{"status":"DOWN"}'), (200, b"\xff", 0, None)],
    ids=["empty-body", "remote-503", "invalid-utf8"],
)
def test_contract_backend_health_response_edges(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, remote_status: int,
    content: bytes, expected_status: int, expected_body: str | None,
) -> None:
    monkeypatch.setattr(
        urllib3.PoolManager, "request", Mock(return_value=SimpleNamespace(status=remote_status, data=content))
    )
    response = task_client.get("/api/backend-health", headers=headers())
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"requestedBy", "status", "body"}
    assert body["requestedBy"] == "student"
    assert body["status"] == expected_status
    if expected_body is None:
        assert isinstance(body["body"], str) and body["body"]
        return
    assert body["body"] == expected_body


@pytest.mark.parametrize("failure", ["network", "timeout"])
def test_contract_backend_health_remote_exceptions(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    errors = {
        "network": urllib3.exceptions.HTTPError("Backend unavailable"),
        "timeout": urllib3.exceptions.TimeoutError("Backend timeout"),
    }
    monkeypatch.setattr(urllib3.PoolManager, "request", Mock(side_effect=errors[failure]))
    response = task_client.get("/api/backend-health", headers=headers())
    assert response.status_code == 200
    assert response.json() == {"requestedBy": "student", "status": 0, "body": str(errors[failure])}


def test_contract_backend_health_unhandled_dependency_returns_plain_500(task_client: TestClient) -> None:
    def failed_dependency() -> None:
        raise RuntimeError("Synthetic dependency failure")
    task_client.app.dependency_overrides[verified_identity] = failed_dependency
    try:
        assert_plain_server_error(task_client.get("/api/backend-health", headers=headers()))
    finally:
        task_client.app.dependency_overrides.clear()


@pytest.mark.parametrize("case", API_CASES)
def test_contract_unauthorized_requests_have_no_business_side_effects(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, case: tuple[str, str, int]
) -> None:
    remote_request = Mock(side_effect=AssertionError("Unexpected backend call"))
    monkeypatch.setattr(urllib3.PoolManager, "request", remote_request)
    before = task_client.app.state.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    response = call_api(task_client, case, {})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token: authentication failed"}
    assert task_client.app.state.connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == before
    assert list(Path(task_client.app.state.upload_dir).iterdir()) == []
    remote_request.assert_not_called()


CONCURRENT_TEST_TIMEOUT_SECONDS = 5


def test_known_bug_h03_concurrent_rollback_preserves_success(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row_read = Event()
    release_read = Event()
    original_get_task = TaskRepository.get_task

    def controlled_get_task(repository: TaskRepository, task_id: int) -> sqlite3.Row | None:
        row = original_get_task(repository, task_id)
        if row is not None and row["title"] == "Concurrent A":
            row_read.set()
            assert release_read.wait(CONCURRENT_TEST_TIMEOUT_SECONDS), "Concurrent read was not released"
        return row

    monkeypatch.setattr(TaskRepository, "get_task", controlled_get_task)
    task_client.app.state.connection.execute(
        "CREATE TRIGGER reject_concurrent_task BEFORE INSERT ON tasks "
        "WHEN NEW.title = 'Rejected' BEGIN SELECT RAISE(ABORT, 'synthetic constraint failure'); END"
    )
    request_headers = headers()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            task_client.post, "/api/tasks", headers=request_headers, json={"title": "Concurrent A"}
        )
        try:
            assert row_read.wait(CONCURRENT_TEST_TIMEOUT_SECONDS), "Concurrent insert did not reach its read"
            rejected = task_client.post("/api/tasks", headers=request_headers, json={"title": "Rejected"})
            assert rejected.status_code == 500
            assert rejected.json() == {"detail": "Task storage unavailable"}
        finally:
            release_read.set()
        created = future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS)
    assert created.status_code == 201
    persisted = task_client.get("/api/tasks", headers=request_headers)
    assert persisted.status_code == 200
    assert created.json() in persisted.json(), "A successful task was lost after another request rolled back"
```

## Ejecuciones reales anteriores al aislamiento

Directorio de trabajo: **raiz de workshop-requirements-api/**, es decir `.` dentro de este repositorio independiente. Entorno: Windows, PowerShell, Python 3.13 de `.venv/Scripts/python.exe`; pytest y pytest-cov ya estaban instalados.

Antes de importar app.main, cada invocacion establecio WORKSHOP_DB_PATH y WORKSHOP_UPLOAD_DIR dentro de .pytest_cache/testing-runtime; --basetemp fijo los temporales de pytest tambien dentro del repositorio. Las variables anteriores se restauraron con finally. Los tokens se firman con claves sinteticas efimeras; el backend se simula sin acceder a otro componente.

Las invocaciones y argumentos siguientes son los realmente ejecutados. Esta secuencia reproduce su preparacion y conserva cada codigo de salida, incluso cuando pytest devuelve 1:

```powershell
$previousDbPath = $env:WORKSHOP_DB_PATH
$previousUploadDir = $env:WORKSHOP_UPLOAD_DIR
$previousCoverageFile = $env:COVERAGE_FILE
try {
    $env:WORKSHOP_DB_PATH = Join-Path (Get-Location) '.pytest_cache/testing-runtime/workshop.db'
    $env:WORKSHOP_UPLOAD_DIR = Join-Path (Get-Location) '.pytest_cache/testing-runtime/uploads'

    & ./.venv/Scripts/python.exe -B -m pytest -k contract --tb=short --basetemp=.pytest_cache/testing-tmp --junitxml=.pytest_cache/testing-contract.xml
    $contractExit = $LASTEXITCODE

    & ./.venv/Scripts/python.exe -B -m pytest -k known_bug --tb=short --basetemp=.pytest_cache/testing-tmp --junitxml=.pytest_cache/testing-known-bug.xml
    $bugExit = $LASTEXITCODE

    $env:COVERAGE_FILE = Join-Path (Get-Location) '.pytest_cache/testing.coverage'
    & ./.venv/Scripts/python.exe -B -m pytest --tb=short --basetemp=.pytest_cache/testing-tmp --junitxml=.pytest_cache/testing-suite.xml --cov=app --cov=tests --cov-branch --cov-fail-under=85 --cov-report=term-missing --cov-report=json:.pytest_cache/testing-coverage.json --cov-report=html:.pytest_cache/testing-coverage-html
    $suiteExit = $LASTEXITCODE

    Write-Output "Contrato=$contractExit; H03=$bugExit; Suite=$suiteExit"
} finally {
    $env:WORKSHOP_DB_PATH = $previousDbPath
    $env:WORKSHOP_UPLOAD_DIR = $previousUploadDir
    $env:COVERAGE_FILE = $previousCoverageFile
}
```

| Ejecucion | Directorio | Codigo de salida pytest | Resultado observado | Artefacto |
|---|---|---|---|---|
| Casos nuevos de contrato, -k contract | . | 0 | 34 aprobados; 109 deseleccionados; 2.03 s. | [XML contrato](evidence/day1/testing-contract.xml) |
| Regresion H-03, -k known_bug | . | 1 | 1 fallido; 142 deseleccionados; 0.80 s. | [XML bug](evidence/day1/testing-known-bug.xml) |
| Suite completa, sin -k ni exclusiones | . | 1 | 142 aprobados, 1 fallido; 6.79 s. Cobertura supera 85%. | [XML completo](evidence/day1/testing-suite.xml) |

Los grupos -k solo separan diagnosticos; no se usa un comando filtrado para declarar aprobada la suite completa. No hubo skips, xfails ni errores de coleccion. La salida completa contiene 290 advertencias: deprecaciones ya existentes de FastAPI/AnyIO y una advertencia de serializacion al inyectar un status SQLite incompatible para probar su 500. No se silenciaron advertencias ni se modificaron gates.

### Cantidad de pruebas y cobertura

| Momento | Funciones test_ | Casos parametrizados ejecutables |
|---|---|---|
| Antes de esta tarea | 27 | 108 |
| Ahora | 41 | 143 |
| Agregados | 14 | 35 (34 de contrato y 1 regresion de bug) |

Se compararon por AST las 27 funciones previas con la referencia local del estado anterior: cuerpos, aserciones y decoradores permanecen iguales. La mayor cantidad de casos no reemplaza comprobar sus aserciones ni hace desaparecer el fallo conocido.

- Gate combinado aplicado en la ejecucion completa: **99.74%**, superior al 85% exigido en REGLAS.md. Su salida sigue siendo 1 por el test fallido, no por cobertura.
- Codigo modificado en esta tarea (tests): **165/165 lineas ejecutables, 100%**, y **23/24 ramas, 95.83%**. La rama faltante es una alternativa del helper de intercalado, no una exclusion.
- Aplicacion sin modificar: **209/210 lineas**, **14/14 ramas**. No se atribuye este porcentaje a una correccion de H-03.
- Informe real: [JSON cobertura](evidence/day1/testing-coverage.json). Las copias revisadas de XML y JSON se publican en evidence/day1; los originales, caches y HTML quedan locales e ignorados por Git. Los resultados resumidos quedan en este documento.

## Fallos encontrados

**H-03, persistencia concurrente, resultado historico:** el test esperaba que una tarea devuelta con 201 siguiera apareciendo en GET /api/tasks. El rollback de B eliminaba A y fallaba la asercion `A successful task was lost after another request rolled back`. No se cambio la expectativa a ausencia de la tarea ni se marco xfail. La correccion posterior aprobada se verifica en la seccion siguiente; aquel fallo ya no describe el estado actual.

Los 500 por datos corruptos y las respuestas status=0 de salud son caracterizaciones de errores documentados. No se presentan como correcciones ni como aprobacion de filtrar excepciones. Los riesgos de archivos (H-04) y texto de errores (H-06) siguen registrados aparte en HALLAZGOS.md. El caso benigno sin extension verifica el contrato actual, no justifica aceptar nombres peligrosos ni fija una politica de extensiones.

## Pendientes de contrato o entorno del informe original

Las filas Q-2/Q-3 de carga fueron tratadas posteriormente en H-04; sus nuevas pruebas y limites aparecen al final. No representan falta actual de limite local.

| endpoint | caso | tipo | resultado esperado |
|---|---|---|---|
| GET /api/tasks | Q-1: 422 anunciado por OpenAPI sin request HTTP reproducido | Pendiente | Falta definir escenario/cuerpo; no se fabrica una dependencia 422 para fingir cobertura del request. |
| GET /api/summary | Q-1: mismo anuncio automatico | Pendiente | Falta escenario HTTP reproducible y cuerpo. |
| GET /api/backend-health | Q-1: mismo anuncio automatico | Pendiente | Falta escenario HTTP reproducible y cuerpo. |
| POST /api/requirements | Q-2: fileName null desde HTTP | Pendiente | Solo se verificaron nombres multipart string y el rechazo de nombre vacio; no se inventa un exito con null. |
| POST /api/requirements | Q-3: limite maximo de bytes | Pendiente | No existe limite acordado/implementado; no se inventa un tamano ni un HTTP 413. El archivo vacio si esta probado. |
| Cinco rutas | Q-4: token del emisor externo | Pendiente de integracion | El perfil local RS256 esta probado; no se inspecciona ni se llama a otro componente. |

Por tanto, las respuestas de error con escenarios concretos documentados estan cubiertas; el 422 de las rutas GET sigue siendo una limitacion explicita de los criterios de aceptacion, no una prueba aprobada ni omitida artificialmente.

## Pruebas propuestas en el informe original

Las de limite de archivo/cuerpo, limpieza y colisiones ya se ejecutaron en H-04; la regresion de H-03 ya pasa. Permanecen sin ejecucion solo los escenarios externos o sin request HTTP reproducible indicados expresamente abajo.

- Limite exacto de carga y un byte por encima: solo despues de acordar e implementar su politica y respuesta de error (Q-3/H-04).
- fileName null y 422 de GET: solo si se identifica una peticion HTTP real que alcance esos escenarios; no duplicar el schema OpenAPI como si fuera una prueba funcional.
- Integracion real de JWT y salud con el emisor/backend externo: requiere coordinacion y autorizacion; los mocks actuales verifican el contrato local, no disponibilidad externa.
- Robustecer el aislamiento transaccional: una vez corregido H-03, ejecutar la misma regresion fallida sin cambiar su expectativa de persistencia. No hay otra prueba hipotetica contada como ejecutada.

## Aislamiento H-03 - ejecucion posterior aprobada

Se aplico un RLock por conexion y aplicacion, compartido por lecturas y por INSERT/SELECT/commit/rollback completos. No cambiaron endpoints ni tipos/codigos de respuesta. Se mantuvieron las pruebas previas de negocio, autenticacion e IDOR.

La prueba concurrente original se ejecuto antes de editarla: 31 casos aprobados y 1 fallo de persistencia, salida 1. La coordinacion nueva usa eventos y dos futuros: detecta que B espera el bloqueo o que termina, y libera A antes de pedir los resultados. Antes de corregir produccion detecto cuatro fallos (persistencia, dos lecturas sin confirmar y ausencia de lock por aplicacion); despues todos pasan. No se quitaron las aserciones de tarea persistida ni de rollback.

Directorio de todas las ejecuciones: raiz de este repositorio. Preparacion identica a las ejecuciones anteriores, con WORKSHOP_DB_PATH=.pytest_cache/implementation-runtime/workshop.db, WORKSHOP_UPLOAD_DIR=.pytest_cache/implementation-runtime/uploads y temporales dentro del componente.

| Comando pytest (prefijo ./.venv/Scripts/python.exe -B -m) | Antes | Despues | Evidencia |
|---|---|---|---|
| pytest -k 'h03 or h02_correction' --tb=short --basetemp=.pytest_cache/implementation-tmp | Original: 31 aprobados/1 fallido; revisado: 32 aprobados/4 fallidos. Ambos salida 1. | Mismos casos revisados: 36 aprobados, salida 0. | [Original](evidence/day1/h03-original-before.xml), [revisado antes](evidence/day1/h03-revised-before.xml), [despues](evidence/day1/h03-isolation-after.xml) |
| pytest --tb=short --basetemp=.pytest_cache/implementation-tmp --junitxml=.pytest_cache/h03-isolation-suite.xml --cov=app --cov=tests --cov-branch --cov-fail-under=85 --cov-report=term-missing --cov-report=json:.pytest_cache/h03-isolation-coverage.json | El informe historico previo tenia 143 casos y 1 fallo. | 147 aprobados, salida 0, 8.90 s; cobertura combinada 99.77%. | [Suite](evidence/day1/h03-isolation-suite.xml), [cobertura](evidence/day1/h03-isolation-coverage.json) |

En la primera fila se anadio --junitxml con el archivo XML enlazado correspondiente a cada invocacion. COVERAGE_FILE se fijo en .pytest_cache/h03-isolation.coverage y se restauraron las variables despues de cada comando. Persisten advertencias anteriores; no se silenciaron ni se redujo el gate 85%.

Se agregaron cuatro casos: dos lecturas durante escritura, dos creaciones validas y aislamiento entre aplicaciones. La regresion existente se recoordino sin eliminar su expectativa. [Diff propio de H-03](evidence/day1/h03-isolation.patch). Las preguntas de carga/JWT externo siguen pendientes de sus acuerdos; no forman parte de H-03.

## Carga segura H-04 - ejecucion posterior aprobada

El usuario confirmo 5 MiB por archivo, 6 MiB por multipart y bloques de 64 KiB, configurables; .txt/.md/.pdf y nombres sin extension, con vacios permitidos. Autorizo 400 para nombre/extension, 413 para limites, 500 JSON generico para I/O y sufijos de colision sin sobrescritura. El contrato se actualizo solo en esa politica; no se agregaron endpoints ni dependencias.

**Antes:** con la API aun sin corregir, `pytest -k 'h04 or upload'` ejecuto 33 casos: 16 aprobados y 17 fallidos, salida 1. [XML antes](evidence/day1/h04-before.xml). **Despues:** la misma cobertura funcional pasa y se agregaron verificaciones de cancelacion, nombres reservados/enlaces, configuracion, cuerpo exacto/desconexion y errores de temporal/colision: 49 casos aprobados, salida 0. [XML despues](evidence/day1/h04-after.xml). Las expectativas de los dos errores I/O se actualizaron a JSON exclusivamente por el cambio de contrato aprobado, no para ocultar un bug.

En el cierre se agregaron tres variantes reservadas Windows (CON .txt, CONIN$ y CONOUT$.txt): fallaban antes del ajuste del validador y ahora pasan. [XML antes de ese ajuste](evidence/day1/h04-reserved-before.xml): seis aprobados y tres fallidos, salida 1; los nueve casos estan incluidos en el focalizado verde de 49. No se abrieron dispositivos del sistema.

El espia de constructor del parser se corrigio antes de registrar la linea base. El parser elimina prefijos Windows tipo C:\ruta\archivo antes de que la aplicacion vea filename; la prueba absoluta utiliza la variante C:/ruta/archivo que el parser preserva. Se comprobo tambien contra el codigo previo: antes 201 y escritura fuera de uploads dentro del temporal controlado; despues 400 y ninguna escritura. No se redujo la asercion de seguridad para aceptar traversal.

Los tests nuevos estan en la seccion test_h04_ de [tests/test_api.py](../tests/test_api.py). Usan limites pequenos configurables (128 bytes archivo, 1024 cuerpo, 32 bloque) para probar exactamente el limite y un byte mas sin archivos gigantes. La recepcion se comprueba antes de construir UploadFile, con Content-Length falso y real; pruebas ASGI verifican cuerpo exacto y desconexion. Los enlaces se simulan sin pedir privilegios de Windows. La prueba de cancelacion exige eliminar el parcial; la de colision exige conservar ambos contenidos. Los nombres reservados se prueban en el validador sin abrir dispositivos del sistema.

| Verificacion | Comando ejecutado desde la raiz, prefijo ./.venv/Scripts/python.exe -B -m | Codigo | Resultado |
|---|---|---|---|
| Antes H-04 | pytest -k 'h04 or upload' --tb=no --basetemp=.pytest_cache/implementation-tmp --junitxml=.pytest_cache/h04-before.xml | 1 | 16 aprobados, 17 fallidos. |
| Focalizado con cobertura | pytest -k 'h04 or upload' --tb=short --basetemp=.pytest_cache/implementation-tmp --junitxml=.pytest_cache/h04-after.xml --cov=app.requirement_storage --cov=app.schemas --cov-branch --cov-report=term-missing --cov-report=json:.pytest_cache/h04-focused-coverage.json | 0 | Ejecucion intermedia: 46 aprobados; almacenamiento 99% redondeado. |
| Focalizado final | pytest -k 'h04 or upload' --tb=short --basetemp=.pytest_cache/implementation-tmp --junitxml=.pytest_cache/h04-after.xml | 0 | 49 aprobados, incluidos los tres nombres reservados adicionales; reemplaza el XML focalizado anterior. |
| Suite final sin exclusiones | pytest --tb=short --basetemp=.pytest_cache/implementation-tmp --junitxml=.pytest_cache/implementation-final-suite.xml --cov=app --cov=tests --cov-branch --cov-fail-under=85 --cov-report=term-missing --cov-report=json:.pytest_cache/implementation-final-coverage.json | 0 | 186 aprobados, 8.43 s; gate 85% satisfecho, cobertura combinada 99.50%. |

Se uso la misma preparacion/restauracion de WORKSHOP_DB_PATH y WORKSHOP_UPLOAD_DIR de H-03. COVERAGE_FILE se fijo a .pytest_cache/h04-focused.coverage y .pytest_cache/implementation-final.coverage respectivamente. Temporales y reportes permanecen en este repositorio. La suite final conserva H-03 verde y no reduce quality gates; los avisos heredados no se silenciaron.

Cobertura especifica del cambio H-04: main 6/6 lineas, almacenamiento 111/113 lineas y 26/26 ramas, schemas 24/24 lineas y 4/4 ramas, tests 158/160 lineas y 8/8 ramas. Todo supera 85%. [Diff propio H-04](evidence/day1/h04-storage.patch), [XML suite final](evidence/day1/implementation-final-suite.xml), [JSON cobertura final](evidence/day1/implementation-final-coverage.json). Cantidad de casos: 143 antes de esta tanda -> 147 tras H-03 -> 186 tras H-04; 43 casos agregados en total, ninguno omitido.

Las decisiones de politica fueron confirmadas antes de implementarlas; no son desviaciones silenciosas del plan. Los cambios de coordinacion/espias de pruebas se registran arriba y mantuvieron las expectativas de integridad. Las preguntas de integracion externa y el 422 GET no reproducible siguen fuera del alcance. Los resultados y estados historicos anteriores no sustituyen las filas actuales de HALLAZGOS.md.

## Documentos consultados

[ENDPOINTS.md](ENDPOINTS.md), [REGLAS.md](../REGLAS.md), [HALLAZGOS.md](../HALLAZGOS.md) y [pyproject.toml](../pyproject.toml). Tambien se contrastaron las rutas y el repositorio actuales y la suite anterior; no se leyeron otros componentes del workspace.