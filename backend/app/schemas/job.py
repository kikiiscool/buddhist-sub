import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    name: str
    audio_key: str
    config: dict = Field(default_factory=dict)


class StepRunOut(BaseModel):
    id: uuid.UUID
    name: str
    order_idx: int
    status: str
    progress: float
    log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    metrics: dict

    model_config = {"from_attributes": True}


class SegmentOut(BaseModel):
    id: uuid.UUID
    idx: int
    start_s: float
    end_s: float
    text_raw: str
    text_dict: str | None
    text_ai: str | None
    text_final: str | None
    confidence: float | None
    rag_refs: list
    edited_by_human: bool

    model_config = {"from_attributes": True}


class SegmentUpdate(BaseModel):
    text_final: str


class JobOut(BaseModel):
    id: uuid.UUID
    name: str
    audio_key: str
    audio_duration_s: float | None
    status: str
    config: dict
    error: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[StepRunOut] = []

    model_config = {"from_attributes": True}


class UploadInit(BaseModel):
    filename: str
    content_type: str = "audio/mpeg"


class UploadInitOut(BaseModel):
    audio_key: str
    upload_url: str


class StepActionIn(BaseModel):
    action: str  # pause | resume | retry | skip
