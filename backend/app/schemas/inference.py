from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ── Message ─────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str = Field(..., min_length=1)


# ── Request ─────────────────────────────────────────────────────────────────

class ChatCompletionRequest(BaseModel):
    model: str = Field(..., min_length=1)
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=1, le=32768)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)

    @field_validator("messages")
    @classmethod
    def last_message_must_be_user(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if v and v[-1].role not in ("user", "system"):
            raise ValueError("Last message must have role 'user' or 'system'")
        return v


# ── Non-streaming response ───────────────────────────────────────────────────

class UsageStats(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageStats


# ── Streaming response ───────────────────────────────────────────────────────

class DeltaMessage(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]


# ── Model list (GET /v1/models) ───────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    display_name: str
    status: str
    context_window: int
    quantization: str | None = None
    created: int


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


# ── Standard API envelope (non-inference endpoints) ───────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


class SuccessResponse(BaseModel):
    success: bool = True
    data: dict | list | None = None
