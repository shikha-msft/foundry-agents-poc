from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from azure.core.exceptions import ClientAuthenticationError
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from openai import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from .configuration import Settings
from .service import (
    AudioFormat,
    AudioResponseError,
    AudioService,
    Voice,
    build_credential,
    create_service,
    has_audio_header,
)

logger = logging.getLogger(__name__)


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4096)
    voice: Voice = "alloy"
    response_format: AudioFormat = "wav"

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank.")
        return value


class TranscriptionResponse(BaseModel):
    text: str
    request_id: str


async def read_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as error:
            raise HTTPException(400, "Content-Length must be an integer.") from error
        if declared_size < 0:
            raise HTTPException(400, "Content-Length must not be negative.")
        if declared_size > limit:
            raise HTTPException(413, "Request exceeds the configured upload limit.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(413, "Request exceeds the configured upload limit.")
        body.extend(chunk)
    return bytes(body)


def create_app(
    service_factory: Callable[[Settings], AudioService] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_environment()
        connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
        if connection_string:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=connection_string)
        app.state.settings = settings
        credential = None
        try:
            if service_factory:
                service = service_factory(settings)
            else:
                credential = build_credential(settings)
                service = create_service(settings, credential)
            app.state.service = service
            try:
                yield
            finally:
                service.close()
        finally:
            if credential:
                credential.close()

    app = FastAPI(title="Governed Foundry Audio API", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        if (
            request.url.path.startswith("/api/")
            and request.app.state.settings.require_app_service_auth
            and not request.headers.get("X-MS-CLIENT-PRINCIPAL-ID")
        ):
            response = JSONResponse({"detail": "Microsoft Entra authentication is required."}, 401)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            "Audio API request completed",
            extra={
                "request_id": request.state.request_id,
                "operation": (
                    request.url.path
                    if request.url.path
                    in {"/api/speech", "/api/transcriptions", "/healthz", "/readyz"}
                    else "unmatched"
                ),
                "status_code": response.status_code,
            },
        )
        return response

    @app.exception_handler(APIStatusError)
    async def provider_status(request: Request, error: APIStatusError) -> JSONResponse:
        code = 429 if error.status_code == 429 else 502
        logger.warning(
            "Audio provider rejected request",
            extra={"request_id": request.state.request_id, "provider_status": error.status_code},
        )
        return JSONResponse(
            {"detail": "Audio provider rejected the request; check deployment access and limits."},
            code,
        )

    @app.exception_handler(ClientAuthenticationError)
    async def credential_failure(
        request: Request, error: ClientAuthenticationError
    ) -> JSONResponse:
        logger.warning(
            "Audio workload authentication failed",
            extra={"request_id": request.state.request_id, "error_type": type(error).__name__},
        )
        return JSONResponse({"detail": "Audio workload authentication failed."}, 503)

    @app.exception_handler(APIConnectionError)
    async def provider_connection(request: Request, error: APIConnectionError) -> JSONResponse:
        code = 504 if isinstance(error, APITimeoutError) else 502
        logger.warning(
            "Audio provider connection failed",
            extra={"request_id": request.state.request_id, "error_type": type(error).__name__},
        )
        return JSONResponse({"detail": "Audio provider connection failed."}, code)

    @app.exception_handler(AudioResponseError)
    async def invalid_response(request: Request, error: AudioResponseError) -> JSONResponse:
        logger.warning(
            "Audio provider returned unusable content",
            extra={"request_id": request.state.request_id, "error_type": type(error).__name__},
        )
        return JSONResponse({"detail": str(error)}, 502)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/readyz")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/api/speech",
        response_class=Response,
        responses={
            200: {
                "content": {
                    "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                    "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                }
            }
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": SynthesisRequest.model_json_schema()}},
            }
        },
    )
    async def speech(request: Request) -> Response:
        if (
            request.headers.get("Content-Type", "").split(";")[0].strip().lower()
            != "application/json"
        ):
            raise HTTPException(415, "Send a JSON synthesis request.")
        body = await read_body(request, 32_768)
        try:
            payload = SynthesisRequest.model_validate_json(body)
        except ValidationError as error:
            raise HTTPException(
                422,
                "Use nonblank text of at most 4096 characters, "
                "a supported voice and WAV/MP3 format.",
            ) from error
        audio = await run_in_threadpool(
            request.app.state.service.synthesize,
            payload.text,
            payload.voice,
            payload.response_format,
        )
        content_type = "audio/wav" if payload.response_format == "wav" else "audio/mpeg"
        return Response(
            audio,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="speech.{payload.response_format}"'
            },
        )

    @app.post(
        "/api/transcriptions",
        response_model=TranscriptionResponse,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                    "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                },
            }
        },
    )
    async def transcriptions(
        request: Request,
        language: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
    ) -> TranscriptionResponse:
        content_type = request.headers.get("Content-Type", "").split(";")[0].strip().lower()
        formats: dict[str, AudioFormat] = {
            "audio/wav": "wav",
            "audio/x-wav": "wav",
            "audio/mpeg": "mp3",
        }
        if content_type not in formats:
            raise HTTPException(415, "Send raw WAV or MP3 audio with its correct Content-Type.")
        audio = await read_body(request, request.app.state.settings.max_upload_bytes)
        if not audio:
            raise HTTPException(400, "Audio must not be empty.")
        audio_format = formats[content_type]
        if not has_audio_header(audio, audio_format):
            raise HTTPException(415, "The body does not contain the declared WAV/MP3 header.")
        text = await run_in_threadpool(
            request.app.state.service.transcribe, bytes(audio), audio_format, language
        )
        return TranscriptionResponse(text=text, request_id=request.state.request_id)

    return app


app = create_app()
