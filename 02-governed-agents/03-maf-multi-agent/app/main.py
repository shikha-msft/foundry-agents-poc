from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from .authentication import build_credential
from .configuration import Settings
from .orchestration import MultiAgentRuntime

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class ChatResponse(BaseModel):
    answer: str
    participants: list[str]
    request_id: str


RuntimeFactory = Callable[[Settings], MultiAgentRuntime]


def _default_runtime_factory(settings: Settings) -> MultiAgentRuntime:
    return MultiAgentRuntime(settings, build_credential(settings))


def create_app(runtime_factory: RuntimeFactory = _default_runtime_factory) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = Settings.from_environment()
        if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
            configure_azure_monitor()
        app.state.settings = settings
        app.state.runtime = runtime_factory(settings)
        try:
            yield
        finally:
            app.state.runtime.close()

    application = FastAPI(
        title="Governed MAF Multi-Agent",
        version="1.0.0",
        lifespan=lifespan,
    )

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "healthy"}

    @application.get("/readyz")
    async def readiness(request: Request) -> dict[str, str]:
        if not getattr(request.app.state, "runtime", None):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Multi-agent runtime is not initialized.",
            )
        return {"status": "ready"}

    @application.post("/api/chat", response_model=ChatResponse)
    async def chat(
        payload: ChatRequest,
        request: Request,
        x_ms_client_principal_id: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ) -> ChatResponse:
        settings: Settings = request.app.state.settings
        if settings.require_app_service_auth and not x_ms_client_principal_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Microsoft Entra authentication is required.",
            )

        request_id = x_request_id or str(uuid4())
        logger.info("Starting governed MAF workflow", extra={"request_id": request_id})
        try:
            result = await request.app.state.runtime.run(payload.message)
        except TimeoutError as error:
            logger.warning(
                "Governed MAF workflow timed out",
                extra={"request_id": request_id},
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="The multi-agent workflow exceeded its execution time limit.",
            ) from error

        logger.info("Completed governed MAF workflow", extra={"request_id": request_id})
        return ChatResponse(
            answer=result.answer,
            participants=list(result.participants),
            request_id=request_id,
        )

    return application


app = create_app()
