from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator

DEFAULT_TASK_STATUS = "TODO"
DEFAULT_TASK_PRIORITY = "MEDIUM"


class Identity(BaseModel):
    username: str = Field(strict=True, min_length=1)
    role: str = Field(default="", strict=True)

    @field_validator("username")
    @classmethod
    def nonblank_username(cls, username: str) -> str:
        if not username.strip():
            raise ValueError("Username must not be blank")
        return username


class JwtClaims(Identity):
    username: str = Field(validation_alias="sub", strict=True, min_length=1)
    exp: StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]


class TaskInput(BaseModel):
    title: str = ""
    description: str = ""
    status: str = DEFAULT_TASK_STATUS
    priority: str = DEFAULT_TASK_PRIORITY
    owner: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], default_owner: str) -> "TaskInput":
        return cls(
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            status=str(payload.get("status", DEFAULT_TASK_STATUS)),
            priority=str(payload.get("priority", DEFAULT_TASK_PRIORITY)),
            owner=default_owner,
        )


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    owner: str
    priority: str
    created_at: str = Field(serialization_alias="createdAt")


class SummaryResponse(BaseModel):
    owner: str
    total: int = 0
    by_status: dict[str, int] = Field(default_factory=dict, serialization_alias="byStatus")
    high_priority_open: int = Field(default=0, serialization_alias="highPriorityOpen")


KIBIBYTE = 1024
MEBIBYTE = KIBIBYTE * KIBIBYTE
DEFAULT_UPLOAD_FILE_BYTES = 5 * MEBIBYTE
DEFAULT_UPLOAD_BODY_BYTES = 6 * MEBIBYTE
DEFAULT_UPLOAD_CHUNK_BYTES = 64 * KIBIBYTE
DEFAULT_UPLOAD_EXTENSIONS = frozenset({".txt", ".md", ".pdf"})


class UploadPolicy(BaseModel):
    max_file_bytes: int = Field(default=DEFAULT_UPLOAD_FILE_BYTES, gt=0)
    max_body_bytes: int = Field(default=DEFAULT_UPLOAD_BODY_BYTES, gt=0)
    chunk_bytes: int = Field(default=DEFAULT_UPLOAD_CHUNK_BYTES, gt=0)
    allowed_extensions: frozenset[str] = DEFAULT_UPLOAD_EXTENSIONS

    @model_validator(mode="after")
    def consistent_limits(self) -> "UploadPolicy":
        if not self.chunk_bytes <= self.max_file_bytes < self.max_body_bytes:
            raise ValueError("Upload limits must satisfy chunk <= file < multipart body")
        if any(not extension.startswith(".") or any(character in extension for character in "/\\:") for extension in self.allowed_extensions):
            raise ValueError("Upload extensions must be simple suffixes starting with a dot")
        return self


class RequirementResponse(BaseModel):
    owner: str
    file_name: str = Field(serialization_alias="fileName")
    stored_at: str = Field(serialization_alias="storedAt")
    size: int