from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any, TypeVar

import urllib3
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import Identity, TaskInput
from app.requirement_storage import UploadBodyLimitMiddleware, store_requirement, upload_policy_from_environment
from app.security import verified_identity
from app.task_repository import TaskRepository
from app.task_service import TaskService

TASK_STORAGE_ERROR = "Task storage unavailable"
TaskResult = TypeVar("TaskResult")


def execute_task_operation(operation: Callable[[], TaskResult]) -> TaskResult:
    try:
        return operation()
    except sqlite3.Error as error:
        raise HTTPException(status_code=500, detail=TASK_STORAGE_ERROR) from error


def create_app(db_path: str | None = None, upload_dir: str | None = None) -> FastAPI:
    selected_db = db_path or os.getenv("WORKSHOP_DB_PATH", "./data/workshop.db")
    selected_uploads = upload_dir or os.getenv("WORKSHOP_UPLOAD_DIR", "./uploads")
    Path(selected_db).parent.mkdir(parents=True, exist_ok=True)
    Path(selected_uploads).mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(selected_db, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL, owner TEXT NOT NULL, priority TEXT NOT NULL, created_at TEXT NOT NULL)")
    count = connection.execute("SELECT COUNT(*) AS total FROM tasks").fetchone()["total"]
    if count == 0:
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Refactor login','Separar responsabilidades en frontend','TODO','student','HIGH',datetime('now'))")
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Review API','Revisar seguridad de endpoints','IN_PROGRESS','student','MEDIUM',datetime('now'))")
        connection.execute("INSERT INTO tasks(title,description,status,owner,priority,created_at) VALUES ('Trainer notes','Preparar retrospectiva','TODO','trainer','LOW',datetime('now'))")
        connection.commit()

    app = FastAPI(title="Workshop Requirements API", version="0.1.0")
    app.state.connection = connection
    app.state.upload_dir = selected_uploads
    connection_lock = RLock()
    app.state.connection_lock = connection_lock
    task_service = TaskService(TaskRepository(connection, connection_lock))
    upload_policy = upload_policy_from_environment()
    app.state.upload_policy = upload_policy
    app.add_middleware(UploadBodyLimitMiddleware, directory=selected_uploads, policy=upload_policy)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/tasks")
    def list_tasks(owner: str | None = Query(default=None), identity: Identity = Depends(verified_identity)) -> list[dict[str, Any]]:
        tasks = execute_task_operation(lambda: task_service.list_tasks(identity))
        return [task.model_dump(by_alias=True) for task in tasks]

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: dict[str, Any] = Body(...), identity: Identity = Depends(verified_identity)) -> dict[str, Any]:
        task_input = TaskInput.from_payload(payload, identity.username)
        task = execute_task_operation(lambda: task_service.create_task(task_input, identity))
        return task.model_dump(by_alias=True)

    @app.get("/api/summary")
    def summary(owner: str | None = Query(default=None), identity: Identity = Depends(verified_identity)) -> dict[str, Any]:
        response = execute_task_operation(lambda: task_service.summary(identity))
        return response.model_dump(by_alias=True)

    @app.post("/api/requirements", status_code=201)
    async def upload_requirement(file: UploadFile = File(...), identity: Identity = Depends(verified_identity)) -> dict[str, Any]:
        response = await store_requirement(file, identity.username, selected_uploads, upload_policy)
        return response.model_dump(by_alias=True)

    @app.get("/api/backend-health")
    def backend_health(identity: Identity = Depends(verified_identity)) -> dict[str, Any]:
        url = os.getenv("AUTH_HEALTH_URL", "http://localhost:8080/q/health")
        try:
            response = urllib3.PoolManager().request("GET", url, timeout=3.0)
            return {"requestedBy": identity.username, "status": response.status, "body": response.data.decode("utf-8")}
        except Exception as error:
            return {"requestedBy": identity.username, "status": 0, "body": str(error)}

    @app.on_event("shutdown")
    def close_connection() -> None:
        connection.close()

    return app


app = create_app()
