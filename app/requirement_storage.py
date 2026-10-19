import os
import unicodedata
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryFile
from typing import BinaryIO
from urllib.parse import unquote
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas import RequirementResponse, UploadPolicy

INVALID_FILENAME = "Invalid filename"
INVALID_EXTENSION = "File extension not allowed"
UPLOAD_TOO_LARGE = "Upload too large"
STORAGE_ERROR = "Requirement storage unavailable"
MAX_COLLISION_ATTEMPTS = 16
INVALID_NAME_CHARACTERS = frozenset('<>:"/\\|?*')
RESERVED_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}) | frozenset(
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
)


def upload_policy_from_environment() -> UploadPolicy:
    values = {
        field: os.environ[variable]
        for field, variable in {
            "max_file_bytes": "WORKSHOP_UPLOAD_MAX_FILE_BYTES",
            "max_body_bytes": "WORKSHOP_UPLOAD_MAX_BODY_BYTES",
            "chunk_bytes": "WORKSHOP_UPLOAD_CHUNK_BYTES",
        }.items()
        if variable in os.environ
    }
    if "WORKSHOP_UPLOAD_ALLOWED_EXTENSIONS" in os.environ:
        values["allowed_extensions"] = frozenset(
            extension.strip().casefold()
            for extension in os.environ["WORKSHOP_UPLOAD_ALLOWED_EXTENSIONS"].split(",")
            if extension.strip()
        )
    return UploadPolicy.model_validate(values)


def safe_filename(filename: str | None, policy: UploadPolicy) -> str:
    name = unicodedata.normalize("NFKC", unquote(filename or ""))
    if (
        not name or name in {".", ".."} or name.endswith((".", " "))
        or any(character in INVALID_NAME_CHARACTERS or ord(character) < 32 or ord(character) == 127 for character in name)
        or name.split(".", 1)[0].rstrip(" ").upper() in RESERVED_NAMES
    ):
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=INVALID_FILENAME)
    extension = Path(name).suffix.casefold()
    if extension and extension not in policy.allowed_extensions:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=INVALID_EXTENSION)
    return name


def exclusive_destination(directory: Path, name: str) -> tuple[Path, BinaryIO]:
    root = directory.resolve(strict=True)
    for attempt in range(MAX_COLLISION_ATTEMPTS):
        candidate_name = name if attempt == 0 else f"{Path(name).stem}-{uuid4().hex}{Path(name).suffix}"
        target = directory / candidate_name
        if target.is_symlink() or target.is_junction() or target.resolve().parent != root:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=INVALID_FILENAME)
        try:
            return target, target.open("xb")
        except FileExistsError:
            continue
    raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=STORAGE_ERROR)


async def copy_limited(file: UploadFile, destination: BinaryIO, policy: UploadPolicy) -> int:
    size = 0
    while content := await file.read(policy.chunk_bytes):
        size += len(content)
        if size > policy.max_file_bytes:
            raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail=UPLOAD_TOO_LARGE)
        await run_in_threadpool(destination.write, content)
    return size


async def store_requirement(file: UploadFile, owner: str, directory: str, policy: UploadPolicy) -> RequirementResponse:
    name = safe_filename(file.filename, policy)
    target: Path | None = None
    complete = False
    try:
        target, destination = exclusive_destination(Path(directory), name)
        with destination:
            size = await copy_limited(file, destination, policy)
        response = RequirementResponse(owner=owner, file_name=file.filename or name, stored_at=str(target), size=size)
        complete = True
        return response
    except OSError as error:
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=STORAGE_ERROR) from error
    finally:
        if target is not None and not complete:
            try:
                target.unlink(missing_ok=True)
            except OSError as error:
                raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=STORAGE_ERROR) from error


class UploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, directory: str, policy: UploadPolicy) -> None:
        self.app = app
        self.directory = directory
        self.policy = policy

    async def receive_body(self, receive: Receive, buffer: BinaryIO) -> int | None:
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return None
            content = message.get("body", b"")
            size += len(content)
            if size > self.policy.max_body_bytes:
                raise HTTPException(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail=UPLOAD_TOO_LARGE)
            await run_in_threadpool(buffer.write, content)
            if not message.get("more_body", False):
                return size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != "/api/requirements" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        try:
            with TemporaryFile(mode="w+b", dir=self.directory) as buffer:
                size = await self.receive_body(receive, buffer)
                if size is None:
                    return
                await run_in_threadpool(buffer.seek, 0)
                remaining = size
                replayed = False

                async def replay() -> Message:
                    nonlocal remaining, replayed
                    if replayed and remaining == 0:
                        return await receive()
                    content = await run_in_threadpool(buffer.read, self.policy.chunk_bytes)
                    remaining -= len(content)
                    replayed = True
                    return {"type": "http.request", "body": content, "more_body": remaining > 0}

                await self.app(scope, replay, send)
        except HTTPException as error:
            await JSONResponse({"detail": error.detail}, status_code=error.status_code)(scope, receive, send)
        except OSError:
            await JSONResponse({"detail": STORAGE_ERROR}, status_code=HTTPStatus.INTERNAL_SERVER_ERROR)(scope, receive, send)