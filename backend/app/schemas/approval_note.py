"""Approval Note schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    original_filename: str
    file_size: int
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ActiveLetterheadOut(BaseModel):
    active: bool
    template: TemplateOut | None = None


class ApprovalNoteTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    display_order: int
    is_active: bool


class ApprovalNoteTypeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    display_order: int | None = None


class ApprovalNoteTypeUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class ApprovalNoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    approval_note_type_id: int
    parameters: dict[str, str] = Field(default_factory=dict)
    title: str | None = Field(default=None, max_length=400)


class ApprovalNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    approval_note_type_id: int
    department_id: int | None
    created_by: int
    title: str
    status: str
    document_version: int
    source_template_version: int | None
    created_at: datetime
    updated_at: datetime


class OnlyOfficeConfigOut(BaseModel):
    config: dict
    onlyoffice_url: str
    document_server_api_js: str


class OnlyOfficeForceSaveOut(BaseModel):
    accepted: bool
    error_code: int
    message: str


class OnlyOfficeForceSaveIn(BaseModel):
    document_key: str = Field(min_length=1, max_length=128)


class OnlyOfficeHealthOut(BaseModel):
    configured: bool
    reachable: bool
