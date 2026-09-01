"""Schemas for the per-user OpenHands coding workspace integration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IdeCodeFile(BaseModel):
    path: str = Field(min_length=1, max_length=255)
    content: str = Field(default="")


class IdeCodeState(BaseModel):
    active_file: str = Field(min_length=1, max_length=255)
    files: list[IdeCodeFile] = Field(default_factory=list)


class IdeWorkspaceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    external_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class IdeCodeProjectView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    active_file: str
    files: list[IdeCodeFile]
    created_at: datetime
    updated_at: datetime


class IdeCodeProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_file: str = Field(min_length=1, max_length=255)
    files: list[IdeCodeFile] = Field(default_factory=list, max_length=20)


class IdeStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    provider: str = "openhands"
    workspace: IdeWorkspaceView | None = None
    code: IdeCodeProjectView | None = None


class IdeLaunchResponse(BaseModel):
    launch_url: str
