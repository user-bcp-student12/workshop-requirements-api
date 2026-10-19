import asyncio
import base64
import io
import sqlite3
import tempfile
import time
from _thread import RLock as RLockType
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import cache
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import jwt
import pytest
import urllib3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from httpx import Response
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.main import create_app
from app.schemas import TaskInput
from app.security import verified_identity
from app.task_repository import TaskRepository


AUTH_NOW = int(time.time())
TOKEN_LIFETIME_SECONDS = 3600
JWT_ISSUER = "workshop-auth"
JWT_AUDIENCE = "workshop-requirements-api"
TEST_RSA_KEY_SIZE = 2048
TEST_RSA_EXPONENT = 65537
API_CASES = [
    ("GET", "/api/tasks", 200),
    ("POST", "/api/tasks", 201),
    ("GET", "/api/summary", 200),
    ("POST", "/api/requirements", 201),
    ("GET", "/api/backend-health", 200),
]


def token(username: str = "student", role: str = "STUDENT", expires_at: int | None = None) -> str:
    expiry = AUTH_NOW + TOKEN_LIFETIME_SECONDS if expires_at is None else expires_at
    return signed_token({"sub": username, "role": role, "exp": expiry})


def headers(username: str = "student", role: str = "STUDENT") -> dict[str, str]:
    return {"Authorization": f"Bearer {token(username, role)}"}


@cache
def signing_key(key_name: str) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=TEST_RSA_EXPONENT, key_size=TEST_RSA_KEY_SIZE)


def public_pem() -> str:
    return signing_key("trusted").public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def signed_token(
    overrides: dict[str, object] | None = None, omitted: tuple[str, ...] = (),
    key_name: str = "trusted", algorithm: str = "RS256",
) -> str:
    claims = {"sub": "student", "role": "STUDENT", "iss": JWT_ISSUER, "aud": JWT_AUDIENCE,
              "exp": AUTH_NOW + TOKEN_LIFETIME_SECONDS}
    claims.update(overrides or {})
    for claim in omitted:
        claims.pop(claim, None)
    key = signing_key(key_name)
    if algorithm == "none":
        key = None
    if algorithm == "HS256":
        key = b"synthetic-laboratory-hmac-key-not-for-production"
    return jwt.encode(claims, key, algorithm=algorithm)


@pytest.fixture(autouse=True)
def jwt_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSHOP_JWT_PUBLIC_KEY", public_pem())
    monkeypatch.setenv("WORKSHOP_JWT_ISSUER", JWT_ISSUER)
    monkeypatch.setenv("WORKSHOP_JWT_AUDIENCE", JWT_AUDIENCE)

    class TokenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(AUTH_NOW, tz=tz)

    monkeypatch.setattr(jwt.api_jwt, "datetime", TokenClock)


def test_lists_seeded_tasks(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers=headers())
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_creates_task_and_summary(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            headers=headers(),
            json={"title": "Add tests", "description": "Improve coverage", "status": "TODO", "priority": "HIGH"},
        )
        summary = client.get("/api/summary", headers=headers())
    assert created.status_code == 201
    assert created.json()["owner"] == "student"
    assert summary.json()["total"] == 3


def test_uploads_requirement(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    app = create_app(str(tmp_path / "workshop.db"), str(upload_dir))
    with TestClient(app) as client:
        response = client.post(
            "/api/requirements",
            headers=headers(),
            files={"file": ("requirements.txt", b"Login must be accessible", "text/plain")},
        )
    assert response.status_code == 201
    assert (upload_dir / "requirements.txt").exists()


def test_rejects_invalid_token(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app) as client:
        response = client.get("/api/tasks", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


@pytest.fixture
def task_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(str(tmp_path / "workshop.db"), str(tmp_path / "uploads"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("owner", [None, "", "student"])
def test_h03_characterization_lists_in_order(task_client: TestClient, owner: str | None) -> None:
    params = {} if owner is None else {"owner": owner}
    response = task_client.get("/api/tasks", headers=headers(), params=params)
    assert response.status_code == 200
    tasks = response.json()
    assert [task["id"] for task in tasks] == [1, 2]
    assert [task["owner"] for task in tasks] == ["student", "student"]
    assert tasks[0]["title"] == "Refactor login"
    assert tasks[1]["title"] == "Review API"
    for task in tasks:
        assert set(task) == {"id", "title", "description", "status", "owner", "priority", "createdAt"}
        assert isinstance(task["id"], int)
        assert all(isinstance(value, str) for key, value in task.items() if key != "id")
        datetime.strptime(task["createdAt"], "%Y-%m-%d %H:%M:%S")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, {"title": "", "description": "", "status": "TODO", "priority": "MEDIUM", "owner": "student"}),
        (
            {"title": 42, "description": None, "status": False, "priority": [1, 2], "unknown": "ignored"},
            {"title": "42", "description": "None", "status": "False", "priority": "[1, 2]", "owner": "student"},
        ),
        (
            {"title": "Custom", "description": "Details", "status": "CUSTOM", "priority": "LOW", "owner": "student"},
            {"title": "Custom", "description": "Details", "status": "CUSTOM", "priority": "LOW", "owner": "student"},
        ),
    ],
)
def test_h03_characterization_creates_and_persists(
    task_client: TestClient, payload: dict, expected: dict[str, str]
) -> None:
    response = task_client.post("/api/tasks", headers=headers(), json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == 4
    assert {key: created[key] for key in expected} == expected
    assert set(created) == {"id", "title", "description", "status", "owner", "priority", "createdAt"}
    datetime.strptime(created["createdAt"], "%Y-%m-%d %H:%M:%S")
    listed = task_client.get("/api/tasks", headers=headers())
    assert listed.status_code == 200
    assert listed.json()[-1] == created


def test_h03_characterization_summary_states(task_client: TestClient) -> None:
    for status, priority in [
        ("TODO", "HIGH"), ("IN_PROGRESS", "HIGH"), ("DONE", "HIGH"),
        ("ARCHIVED", "HIGH"), ("CUSTOM", "LOW"), ("DONE", "MEDIUM"),
    ]:
        response = task_client.post(
            "/api/tasks", headers=headers(), json={"title": status, "status": status, "priority": priority}
        )
        assert response.status_code == 201
    response = task_client.get("/api/summary", headers=headers())
    assert response.status_code == 200
    assert response.json() == {
        "owner": "student", "total": 8,
        "byStatus": {"TODO": 2, "IN_PROGRESS": 2, "DONE": 2, "ARCHIVED": 1, "CUSTOM": 1},
        "highPriorityOpen": 3,
    }


def test_h03_characterization_empty_owner(task_client: TestClient) -> None:
    response = task_client.get("/api/tasks", headers=headers("unseeded"))
    assert response.status_code == 200
    assert response.json() == []
    response = task_client.get("/api/summary", headers=headers("unseeded"))
    assert response.status_code == 200
    assert response.json() == {"owner": "unseeded", "total": 0, "byStatus": {}, "highPriorityOpen": 0}


@pytest.mark.parametrize("payload", [None, [], "not an object"])
def test_h03_characterization_requires_object(task_client: TestClient, payload: object) -> None:
    response = task_client.post("/api/tasks", headers=headers(), json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize(
    ("title", "description"),
    [("Trainer's notes", "Student's requirements"), ('Quoted "title"', "Revisi\u00f3n \u65e5\u672c\u8a9e")],
)
def test_h03_correction_preserves_literal_text(task_client: TestClient, title: str, description: str) -> None:
    response = task_client.post(
        "/api/tasks", headers=headers(), json={"title": title, "description": description}
    )
    assert response.status_code == 201
    assert response.json()["title"] == title
    assert response.json()["description"] == description
    listed = task_client.get("/api/tasks", headers=headers())
    assert listed.status_code == 200
    assert len(listed.json()) == 3
    assert listed.json()[-1] == response.json()


def test_h03_correction_special_owner_is_isolated(task_client: TestClient) -> None:
    owner_headers = headers("o'brien")
    listed = task_client.get("/api/tasks", headers=owner_headers)
    assert listed.status_code == 200
    assert listed.json() == []
    created = task_client.post("/api/tasks", headers=owner_headers, json={"title": "Personal task"})
    assert created.status_code == 201
    assert created.json()["owner"] == "o'brien"
    listed = task_client.get("/api/tasks", headers=owner_headers)
    assert listed.json() == [created.json()]
    summary = task_client.get("/api/summary", headers=owner_headers)
    assert summary.status_code == 200
    assert summary.json() == {"owner": "o'brien", "total": 1, "byStatus": {"TODO": 1}, "highPriorityOpen": 0}
    assert len(task_client.get("/api/tasks", headers=headers()).json()) == 2


def test_h03_correction_rolls_back_failed_insert(task_client: TestClient) -> None:
    connection = task_client.app.state.connection
    connection.execute(
        "CREATE TRIGGER reject_test_task BEFORE INSERT ON tasks "
        "WHEN NEW.title = 'Rejected' BEGIN SELECT RAISE(ABORT, 'synthetic database error'); END"
    )
    response = task_client.post("/api/tasks", headers=headers(), json={"title": "Rejected"})
    assert response.status_code == 500
    assert not connection.in_transaction
    assert response.json() == {"detail": "Task storage unavailable"}
    assert len(task_client.get("/api/tasks", headers=headers()).json()) == 2
    accepted = task_client.post("/api/tasks", headers=headers(), json={"title": "Accepted"})
    assert accepted.status_code == 201


def test_h03_repository_rolls_back_missing_created_row(task_client: TestClient) -> None:
    connection = task_client.app.state.connection
    connection.execute(
        "CREATE TRIGGER remove_test_task AFTER INSERT ON tasks "
        "BEGIN DELETE FROM tasks WHERE id = NEW.id OR id = 1; END"
    )
    response = task_client.post("/api/tasks", headers=headers(), json={"title": "Disappearing task"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Task storage unavailable"}
    assert not connection.in_transaction
    listed = task_client.get("/api/tasks", headers=headers())
    assert [task["id"] for task in listed.json()] == [1, 2]


@pytest.fixture
def backend_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        urllib3.PoolManager, "request",
        lambda *arguments, **options: SimpleNamespace(status=200, data=b'{"status":"UP"}'),
    )


def call_api(client: TestClient, case: tuple[str, str, int], request_headers: dict[str, str]):
    method, path, _expected_status = case
    if path == "/api/requirements":
        return client.post(path, headers=request_headers, files={"file": ("auth-check.txt", b"Requirement")})
    if method == "POST":
        return client.post(path, headers=request_headers, json={})
    return client.get(path, headers=request_headers)


@pytest.mark.parametrize("case", API_CASES)
def test_h01_characterization_authenticated_routes(
    task_client: TestClient, backend_stub: None, case: tuple[str, str, int]
) -> None:
    response = call_api(task_client, case, headers())
    assert response.status_code == case[2]
    body = response.json()
    path = case[1]
    if path == "/api/tasks":
        tasks = body if case[0] == "GET" else [body]
        for task in tasks:
            assert task["owner"] == "student"
            assert set(task) == {"id", "title", "description", "status", "owner", "priority", "createdAt"}
        return
    if path == "/api/summary":
        assert body == {"owner": "student", "total": 2, "byStatus": {"TODO": 1, "IN_PROGRESS": 1}, "highPriorityOpen": 1}
        return
    if path == "/api/requirements":
        assert set(body) == {"owner", "fileName", "storedAt", "size"}
        assert body["owner"] == "student"
        assert body["size"] == len(b"Requirement")
        return
    assert body == {"requestedBy": "student", "status": 200, "body": '{"status":"UP"}'}


@pytest.mark.parametrize("case", API_CASES)
@pytest.mark.parametrize("credential", ["missing", "malformed", "expired"])
def test_h01_characterization_rejects_invalid_credentials(
    task_client: TestClient, backend_stub: None, case: tuple[str, str, int], credential: str
) -> None:
    request_headers = {}
    if credential == "malformed":
        request_headers = {"Authorization": "Bearer invalid"}
    if credential == "expired":
        request_headers = {"Authorization": f"Bearer {token(expires_at=AUTH_NOW - 1)}"}
    response = call_api(task_client, case, request_headers)
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}
    assert response.json()["detail"].startswith("Invalid token:")


@pytest.mark.parametrize("username,expected_ids", [("student", [1, 2]), ("trainer", [3])])
@pytest.mark.parametrize("owner_mode", ["omitted", "empty", "self"])
def test_h02_characterization_own_queries(
    task_client: TestClient, username: str, expected_ids: list[int], owner_mode: str
) -> None:
    params = {}
    if owner_mode != "omitted":
        params["owner"] = "" if owner_mode == "empty" else username
    response = task_client.get("/api/tasks", headers=headers(username), params=params)
    assert response.status_code == 200
    assert [task["id"] for task in response.json()] == expected_ids
    summary = task_client.get("/api/summary", headers=headers(username), params=params)
    assert summary.status_code == 200
    assert summary.json()["owner"] == username
    assert summary.json()["total"] == len(expected_ids)


@pytest.mark.parametrize("username", ["student", "trainer"])
@pytest.mark.parametrize("explicit_owner", [False, True])
def test_h02_characterization_own_creation(
    task_client: TestClient, username: str, explicit_owner: bool
) -> None:
    other_username = "trainer" if username == "student" else "student"
    other_before = task_client.get("/api/tasks", headers=headers(other_username)).json()
    payload = {"title": "Own task"}
    if explicit_owner:
        payload["owner"] = username
    created = task_client.post("/api/tasks", headers=headers(username), json=payload)
    assert created.status_code == 201
    assert created.json()["owner"] == username
    assert task_client.get("/api/tasks", headers=headers(username)).json()[-1] == created.json()
    assert task_client.get("/api/tasks", headers=headers(other_username)).json() == other_before


@pytest.mark.parametrize("case", API_CASES)
def test_h01_correction_accepts_verified_jwt(
    task_client: TestClient, backend_stub: None, case: tuple[str, str, int]
) -> None:
    response = call_api(task_client, case, {"Authorization": f"Bearer {signed_token()}"})
    assert response.status_code == case[2]


@pytest.mark.parametrize("case", API_CASES)
def test_h01_correction_rejects_legacy_token(
    task_client: TestClient, backend_stub: None, case: tuple[str, str, int]
) -> None:
    raw = f"student|STUDENT|{AUTH_NOW + TOKEN_LIFETIME_SECONDS}|WORKSHOP_SECRET_2026"
    legacy = base64.b64encode(raw.encode()).decode()
    response = call_api(task_client, case, {"Authorization": f"Bearer {legacy}"})
    assert response.status_code == 401


INVALID_JWT_CLAIMS = {
    "wrong_issuer": {"iss": "untrusted-issuer"},
    "wrong_audience": {"aud": "another-api"},
    "expired": {"exp": AUTH_NOW - 1},
    "future_nbf": {"nbf": AUTH_NOW + TOKEN_LIFETIME_SECONDS},
    "empty_user": {"sub": ""},
    "blank_user": {"sub": "   "},
    "numeric_user": {"sub": 42},
    "null_role": {"role": None},
    "list_role": {"role": ["ADMIN"]},
    "null_exp": {"exp": None},
    "string_exp": {"exp": str(AUTH_NOW + TOKEN_LIFETIME_SECONDS)},
    "infinite_exp": {"exp": float("inf")},
    "null_nbf": {"nbf": None},
}


@pytest.mark.parametrize(
    "invalid_case",
    list(INVALID_JWT_CLAIMS) + ["missing_exp", "missing_iss", "missing_aud", "missing_sub", "unsigned", "wrong_signature", "hs256"],
)
def test_h01_correction_rejects_invalid_jwt(task_client: TestClient, invalid_case: str) -> None:
    overrides = INVALID_JWT_CLAIMS.get(invalid_case)
    omitted = (invalid_case.removeprefix("missing_"),) if invalid_case.startswith("missing_") else ()
    algorithm = "none" if invalid_case == "unsigned" else "RS256"
    if invalid_case == "hs256":
        algorithm = "HS256"
    key_name = "untrusted" if invalid_case == "wrong_signature" else "trusted"
    encoded = signed_token(overrides, omitted, key_name, algorithm)
    response = task_client.get("/api/tasks", headers={"Authorization": f"Bearer {encoded}"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token: authentication failed"}


@pytest.mark.parametrize("header_case", ["bare", "basic", "double", "extra"])
def test_h01_correction_checks_bearer_format(task_client: TestClient, header_case: str) -> None:
    encoded = token()
    authorization = {
        "bare": encoded, "basic": f"Basic {encoded}",
        "double": f"Bearer Bearer {encoded}", "extra": f"Bearer {encoded} extra",
    }[header_case]
    response = task_client.get("/api/tasks", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token: authentication failed"}


@pytest.mark.parametrize("config_case", ["missing", "empty", "invalid", "non_rsa", "private", "empty_issuer", "empty_audience"])
def test_h01_correction_fails_closed_on_invalid_config(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, config_case: str
) -> None:
    if config_case == "missing":
        monkeypatch.delenv("WORKSHOP_JWT_PUBLIC_KEY")
    if config_case in {"empty", "invalid"}:
        monkeypatch.setenv("WORKSHOP_JWT_PUBLIC_KEY", "" if config_case == "empty" else "not a public key")
    if config_case == "non_rsa":
        public_key = ec.generate_private_key(ec.SECP256R1()).public_key()
        monkeypatch.setenv("WORKSHOP_JWT_PUBLIC_KEY", public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii"))
    if config_case == "private":
        monkeypatch.setenv("WORKSHOP_JWT_PUBLIC_KEY", signing_key("trusted").private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode("ascii"))
    if config_case.startswith("empty_"):
        variable = "WORKSHOP_JWT_ISSUER" if config_case == "empty_issuer" else "WORKSHOP_JWT_AUDIENCE"
        monkeypatch.setenv(variable, "")
    response = task_client.get("/api/tasks", headers=headers())
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token: authentication failed"}


def test_h01_correction_role_is_optional(task_client: TestClient) -> None:
    response = task_client.get("/api/tasks", headers={"Authorization": f"Bearer {signed_token(omitted=('role',))}"})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_h01_correction_uses_configured_issuer_and_audience(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKSHOP_JWT_ISSUER", "synthetic-issuer")
    monkeypatch.setenv("WORKSHOP_JWT_AUDIENCE", "synthetic-audience")
    encoded = signed_token({"iss": "synthetic-issuer", "aud": "synthetic-audience"})
    response = task_client.get("/api/tasks", headers={"Authorization": f"Bearer {encoded}"})
    assert response.status_code == 200


@pytest.mark.parametrize("role", ["STUDENT", "TRAINER", "ADMIN"])
@pytest.mark.parametrize("username,expected_ids", [("student", [1, 2]), ("trainer", [3])])
def test_h02_correction_foreign_queries_use_identity(
    task_client: TestClient, role: str, username: str, expected_ids: list[int]
) -> None:
    foreign_owner = "trainer" if username == "student" else "student"
    request_headers = headers(username, role)
    listed = task_client.get("/api/tasks", headers=request_headers, params={"owner": foreign_owner})
    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()] == expected_ids
    summary = task_client.get("/api/summary", headers=request_headers, params={"owner": foreign_owner})
    assert summary.status_code == 200
    assert summary.json()["owner"] == username
    assert summary.json()["total"] == len(expected_ids)


@pytest.mark.parametrize("role", ["STUDENT", "TRAINER", "ADMIN"])
@pytest.mark.parametrize("username", ["student", "trainer"])
def test_h02_correction_foreign_creation_uses_identity(
    task_client: TestClient, role: str, username: str
) -> None:
    foreign_owner = "trainer" if username == "student" else "student"
    before = task_client.get("/api/tasks", headers=headers(foreign_owner)).json()
    created = task_client.post(
        "/api/tasks", headers=headers(username, role), json={"title": "Protected task", "owner": foreign_owner}
    )
    assert created.status_code == 201
    assert created.json()["owner"] == username
    assert task_client.get("/api/tasks", headers=headers(foreign_owner)).json() == before


@pytest.mark.parametrize("supplied_owner", [None, 42, ["trainer"]])
def test_h02_correction_ignores_untrusted_owner_values(task_client: TestClient, supplied_owner: object) -> None:
    response = task_client.post("/api/tasks", headers=headers(), json={"title": "Protected", "owner": supplied_owner})
    assert response.status_code == 201
    assert response.json()["owner"] == "student"


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
def test_contract_upload_io_errors_return_generic_500(
    task_client: TestClient, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    filename = "write-target"
    if failure == "write":
        monkeypatch.setattr(Path, "open", Mock(side_effect=OSError("Synthetic write failure")))
    if failure == "read":
        async def failed_read(self: StarletteUploadFile, size: int = -1) -> bytes:
            raise OSError("Synthetic read failure")
        monkeypatch.setattr(StarletteUploadFile, "read", failed_read)
    response = task_client.post(
        "/api/requirements", headers=headers(), files={"file": (filename, b"Requirement")}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Requirement storage unavailable"}
    assert list(Path(task_client.app.state.upload_dir).iterdir()) == []


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


class ObservedConnectionLock:
    def __init__(self, lock: RLockType, waiting: Event) -> None:
        self.lock = lock
        self.waiting = waiting

    def __enter__(self) -> "ObservedConnectionLock":
        if not self.lock.acquire(blocking=False):
            self.waiting.set()
            self.lock.acquire()
        return self

    def __exit__(self, *exception: object) -> None:
        self.lock.release()


@pytest.fixture
def paused_transaction(monkeypatch: pytest.MonkeyPatch) -> tuple[Event, Event, Event]:
    row_read, release_read, waiting = Event(), Event(), Event()
    original_get_task = TaskRepository.get_task
    original_create_task = TaskRepository.create_task

    def controlled_get_task(repository: TaskRepository, task_id: int) -> sqlite3.Row | None:
        row = original_get_task(repository, task_id)
        if row is not None and row["title"] == "Concurrent A":
            row_read.set()
            assert release_read.wait(CONCURRENT_TEST_TIMEOUT_SECONDS), "Concurrent read was not released"
        return row

    def observed_create_task(repository: TaskRepository, task: TaskInput) -> sqlite3.Row:
        if task.title == "Concurrent A":
            lock = getattr(repository, "connection_lock", RLock())
            monkeypatch.setattr(repository, "connection_lock", ObservedConnectionLock(lock, waiting), raising=False)
        try:
            return original_create_task(repository, task)
        finally:
            if task.title == "Rejected":
                waiting.set()

    monkeypatch.setattr(TaskRepository, "get_task", controlled_get_task)
    monkeypatch.setattr(TaskRepository, "create_task", observed_create_task)
    return row_read, release_read, waiting


def test_known_bug_h03_concurrent_rollback_preserves_success(
    task_client: TestClient, paused_transaction: tuple[Event, Event, Event]
) -> None:
    row_read, release_read, waiting = paused_transaction
    task_client.app.state.connection.execute(
        "CREATE TRIGGER reject_concurrent_task BEFORE INSERT ON tasks "
        "WHEN NEW.title = 'Rejected' BEGIN SELECT RAISE(ABORT, 'synthetic constraint failure'); END"
    )
    request_headers = headers()
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(
            task_client.post, "/api/tasks", headers=request_headers, json={"title": "Concurrent A"}
        )
        try:
            assert row_read.wait(CONCURRENT_TEST_TIMEOUT_SECONDS), "Concurrent insert did not reach its read"
            rejected_future = executor.submit(
                task_client.post, "/api/tasks", headers=request_headers, json={"title": "Rejected"}
            )
            assert waiting.wait(CONCURRENT_TEST_TIMEOUT_SECONDS), "Second transaction did not reach contention or finish"
        finally:
            release_read.set()
        created = future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS)
        rejected = rejected_future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS)
    assert rejected.status_code == 500
    assert rejected.json() == {"detail": "Task storage unavailable"}
    assert created.status_code == 201
    persisted = task_client.get("/api/tasks", headers=request_headers)
    assert persisted.status_code == 200
    assert created.json() in persisted.json(), "A successful task was lost after another request rolled back"
    assert [task["id"] for task in persisted.json()] == [1, 2, created.json()["id"]]
    assert [task["id"] for task in task_client.get("/api/tasks", headers=headers("trainer")).json()] == [3]


@pytest.mark.parametrize("path", ["/api/tasks", "/api/summary"])
def test_h03_reads_wait_for_transaction(
    task_client: TestClient, paused_transaction: tuple[Event, Event, Event], path: str
) -> None:
    row_read, release_read, waiting = paused_transaction
    request_headers = headers()
    with ThreadPoolExecutor(max_workers=2) as executor:
        created_future = executor.submit(
            task_client.post, "/api/tasks", headers=request_headers, json={"title": "Concurrent A"}
        )
        try:
            assert row_read.wait(CONCURRENT_TEST_TIMEOUT_SECONDS)
            read_future = executor.submit(task_client.get, path, headers=request_headers)
            read_future.add_done_callback(lambda completed: waiting.set())
            assert waiting.wait(CONCURRENT_TEST_TIMEOUT_SECONDS)
            completed_before_commit = read_future.done()
        finally:
            release_read.set()
        created = created_future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS)
        response = read_future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS)
    assert not completed_before_commit, "Read exposed a transaction before its commit"
    assert created.status_code == 201 and response.status_code == 200
    expected_total = 3
    if path == "/api/tasks":
        assert len(response.json()) == expected_total
        assert created.json() in response.json()
        return
    assert response.json()["total"] == expected_total


def test_h03_parallel_valid_creations_persist(task_client: TestClient) -> None:
    request_headers = headers()
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(task_client.post, "/api/tasks", headers=request_headers, json={"title": title})
            for title in ["Parallel A", "Parallel B"]
        ]
        created = [future.result(timeout=CONCURRENT_TEST_TIMEOUT_SECONDS) for future in futures]
    assert all(response.status_code == 201 for response in created)
    assert len({response.json()["id"] for response in created}) == 2
    listed = task_client.get("/api/tasks", headers=request_headers).json()
    assert len(listed) == 4
    assert all(response.json() in listed for response in created)


def test_h03_connection_lock_is_per_application(task_client: TestClient, tmp_path: Path) -> None:
    other = create_app(str(tmp_path / "other.db"), str(tmp_path / "other-uploads"))
    with TestClient(other) as other_client:
        first_lock = getattr(task_client.app.state, "connection_lock", None)
        second_lock = getattr(other.state, "connection_lock", None)
        assert first_lock is not None and second_lock is not None
        assert first_lock is not second_lock
        with first_lock:
            response = other_client.get("/api/tasks", headers=headers())
        assert response.status_code == 200 and len(response.json()) == 2


TEST_UPLOAD_FILE_BYTES = 128
TEST_UPLOAD_BODY_BYTES = 1024
TEST_UPLOAD_CHUNK_BYTES = 32


@pytest.fixture
def limited_upload_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("WORKSHOP_UPLOAD_MAX_FILE_BYTES", str(TEST_UPLOAD_FILE_BYTES))
    monkeypatch.setenv("WORKSHOP_UPLOAD_MAX_BODY_BYTES", str(TEST_UPLOAD_BODY_BYTES))
    monkeypatch.setenv("WORKSHOP_UPLOAD_CHUNK_BYTES", str(TEST_UPLOAD_CHUNK_BYTES))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    app = create_app(str(tmp_path / "upload.db"), str(tmp_path / "uploads"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


@pytest.mark.parametrize("filename", ["requirements.txt", "requirements.TXT", "requirements.md", "requirements.pdf", "requirements"])
def test_h04_characterization_valid_upload(limited_upload_client: TestClient, filename: str) -> None:
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": (filename, b"Requirement")}
    )
    assert response.status_code == 201
    target = Path(response.json()["storedAt"])
    assert response.json() == {"owner": "student", "fileName": filename, "storedAt": str(target), "size": 11}
    assert target == Path(limited_upload_client.app.state.upload_dir) / filename
    assert target.read_bytes() == b"Requirement"


@pytest.mark.parametrize("filename", ["../escape.txt", "..\\escape.txt", "nested/file.txt", "nested\\file.txt", ".", "..", "bad\x00.txt", "trailing.txt "])
def test_h04_rejects_unsafe_names(limited_upload_client: TestClient, filename: str) -> None:
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": (filename, b"benign")}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid filename"}
    assert list(Path(limited_upload_client.app.state.upload_dir).iterdir()) == []


def test_h04_rejects_absolute_name_inside_test_directory(limited_upload_client: TestClient, tmp_path: Path) -> None:
    outside_uploads = tmp_path / "absolute.txt"
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": (outside_uploads.as_posix(), b"benign")}
    )
    assert response.status_code == 400
    assert not outside_uploads.exists()


@pytest.mark.parametrize("extension", [".exe", ".zip"])
def test_h04_rejects_disallowed_extensions(limited_upload_client: TestClient, extension: str) -> None:
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("requirement" + extension, b"benign")}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "File extension not allowed"}


@pytest.mark.parametrize("link_method", ["is_symlink", "is_junction"])
def test_h04_rejects_symbolic_destination(
    limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch, link_method: str
) -> None:
    original = getattr(Path, link_method)
    monkeypatch.setattr(Path, link_method, lambda path: path.name == "link.txt" or original(path))
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("link.txt", b"benign")}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid filename"}


@pytest.mark.parametrize("size", [TEST_UPLOAD_FILE_BYTES, TEST_UPLOAD_FILE_BYTES + 1])
def test_h04_file_limit_and_cleanup(limited_upload_client: TestClient, size: int) -> None:
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("limit.txt", b"x" * size)}
    )
    if size == TEST_UPLOAD_FILE_BYTES:
        assert response.status_code == 201
        assert response.json()["size"] == size
        return
    assert response.status_code == 413
    assert response.json() == {"detail": "Upload too large"}
    assert list(Path(limited_upload_client.app.state.upload_dir).iterdir()) == []


def test_h04_collision_preserves_both_files(limited_upload_client: TestClient) -> None:
    first = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("shared.txt", b"first")}
    )
    second = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("shared.txt", b"second")}
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["fileName"] == second.json()["fileName"] == "shared.txt"
    assert first.json()["storedAt"] != second.json()["storedAt"]
    assert Path(first.json()["storedAt"]).read_bytes() == b"first"
    assert Path(second.json()["storedAt"]).read_bytes() == b"second"


def test_h04_reads_bounded_blocks(limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sizes = []
    original = StarletteUploadFile.read

    async def observed_read(file: StarletteUploadFile, size: int = -1) -> bytes:
        sizes.append(size)
        return await original(file, size)

    monkeypatch.setattr(StarletteUploadFile, "read", observed_read)
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("blocks.txt", b"x" * (TEST_UPLOAD_FILE_BYTES // 2))}
    )
    assert response.status_code == 201
    assert sizes and all(size == TEST_UPLOAD_CHUNK_BYTES for size in sizes)


@pytest.mark.parametrize("false_length", [False, True])
def test_h04_body_limit_precedes_parser(
    limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch, false_length: bool
) -> None:
    original = StarletteUploadFile.__init__
    calls = Mock()

    def observed_init(upload: StarletteUploadFile, *arguments: object, **options: object) -> None:
        calls()
        original(upload, *arguments, **options)

    monkeypatch.setattr(StarletteUploadFile, "__init__", observed_init)
    request_headers = headers()
    if false_length:
        request_headers["Content-Length"] = "1"
    response = limited_upload_client.post(
        "/api/requirements", headers=request_headers,
        files={"file": ("body.txt", b"x" * (TEST_UPLOAD_BODY_BYTES + 1))},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Upload too large"}
    calls.assert_not_called()
    assert list(Path(limited_upload_client.app.state.upload_dir).iterdir()) == []


@pytest.mark.parametrize("filename", [None, "", "CON.txt", "CON .txt", "CONIN$", "CONOUT$.txt", "LPT1.txt", "file:stream.txt", "..%2fescape.txt"])
def test_h04_rejects_reserved_or_encoded_names(filename: str | None) -> None:
    from app.requirement_storage import safe_filename
    from app.schemas import UploadPolicy

    with pytest.raises(HTTPException) as error:
        safe_filename(filename, UploadPolicy())
    assert error.value.status_code == 400
    assert error.value.detail == "Invalid filename"


def test_h04_cancellation_removes_partial_file(limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.requirement_storage import store_requirement

    upload = UploadFile(file=io.BytesIO(b"partial"), filename="cancel.txt")
    monkeypatch.setattr(upload, "read", AsyncMock(side_effect=[b"partial", asyncio.CancelledError()]))
    try:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(store_requirement(
                upload, "student", limited_upload_client.app.state.upload_dir, limited_upload_client.app.state.upload_policy
            ))
        assert list(Path(limited_upload_client.app.state.upload_dir).iterdir()) == []
    finally:
        asyncio.run(upload.close())


def test_h04_collision_exhaustion_is_generic(limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "open", Mock(side_effect=FileExistsError("Synthetic collision")))
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("collision.txt", b"Requirement")}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Requirement storage unavailable"}


def test_h04_spooling_failure_is_generic(limited_upload_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.requirement_storage.TemporaryFile", Mock(side_effect=OSError("Synthetic spool failure")))
    response = limited_upload_client.post(
        "/api/requirements", headers=headers(), files={"file": ("spool.txt", b"Requirement")}
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Requirement storage unavailable"}


@pytest.mark.parametrize("disconnect", [False, True])
def test_h04_body_limit_exact_and_disconnect(limited_upload_client: TestClient, disconnect: bool) -> None:
    from app.requirement_storage import UploadBodyLimitMiddleware

    policy = limited_upload_client.app.state.upload_policy
    messages = [
        {"type": "http.request", "body": b"x" * (policy.max_body_bytes // 2), "more_body": True},
        {"type": "http.request", "body": b"x" * (policy.max_body_bytes // 2), "more_body": False},
        {"type": "http.disconnect"},
    ]
    if disconnect:
        messages = [messages[0], {"type": "http.disconnect"}]
    receive = AsyncMock(side_effect=messages)
    send = AsyncMock()
    consumed = bytearray()

    async def application(scope, replay, output) -> None:
        while True:
            message = await replay()
            consumed.extend(message["body"])
            if not message["more_body"]:
                break
        assert (await replay())["type"] == "http.disconnect"

    middleware = UploadBodyLimitMiddleware(application, limited_upload_client.app.state.upload_dir, policy)
    asyncio.run(middleware({"type": "http", "method": "POST", "path": "/api/requirements"}, receive, send))
    assert len(consumed) == (0 if disconnect else policy.max_body_bytes)
    assert list(Path(limited_upload_client.app.state.upload_dir).iterdir()) == []


def test_h04_custom_extensions_and_invalid_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.requirement_storage import upload_policy_from_environment
    from pydantic import ValidationError

    monkeypatch.setenv("WORKSHOP_UPLOAD_ALLOWED_EXTENSIONS", " .CSV, .TXT ")
    assert upload_policy_from_environment().allowed_extensions == {".csv", ".txt"}
    monkeypatch.setenv("WORKSHOP_UPLOAD_MAX_FILE_BYTES", "0")
    with pytest.raises(ValidationError):
        upload_policy_from_environment()
    monkeypatch.setenv("WORKSHOP_UPLOAD_MAX_FILE_BYTES", "999999999")
    with pytest.raises(ValidationError):
        upload_policy_from_environment()
    monkeypatch.delenv("WORKSHOP_UPLOAD_MAX_FILE_BYTES")
    monkeypatch.setenv("WORKSHOP_UPLOAD_ALLOWED_EXTENSIONS", "txt,.bad/path")
    with pytest.raises(ValidationError):
        upload_policy_from_environment()
