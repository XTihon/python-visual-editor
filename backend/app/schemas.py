"""Pydantic-модели запросов и файла проекта."""
import json
import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import MAX_CODE_CHARS, MAX_RUN_BYTES

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RunRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    timeoutSec: int = Field(default=30, ge=1, le=300)


class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schemaVersion: Literal[2] = 2
    id: str
    name: str = Field(default="Без названия", min_length=1, max_length=200)
    code: str = Field(default="", max_length=MAX_CODE_CHARS)
    run: Optional[dict[str, Any]] = None  # результат последнего запуска: граф значений, вывод, ошибка
    createdAt: str = ""
    updatedAt: str = ""
    migratedFrom: Optional[int] = None
    original: Optional[dict[str, Any]] = None  # исходный проект старого формата, если он был преобразован

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value):
        if not ID_PATTERN.fullmatch(value):
            raise ValueError("идентификатор проекта: только латиница, цифры, «-» и «_», до 64 символов")
        return value

    @field_validator("run")
    @classmethod
    def _limit_run_size(cls, value):
        if value is not None and len(json.dumps(value, ensure_ascii=False)) > MAX_RUN_BYTES:
            raise ValueError("результат запуска слишком большой")
        return value
