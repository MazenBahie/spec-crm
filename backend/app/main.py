from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    ai,
    channels,
    customers,
    dashboard,
    health,
    knowledge_base,
    portal,
    portal_chat,
    portal_kb,
    quick_replies,
    tasks,
    tickets,
)
from app.core.config import settings
from app.services.ai.errors import AIProviderError
from app.services.errors import Conflict, Forbidden, NotFound, PayloadTooLarge


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(customers.router, prefix=settings.api_prefix)
    app.include_router(tickets.router, prefix=settings.api_prefix)
    app.include_router(channels.router, prefix=settings.api_prefix)
    # Real, credential-based auth -- distinct from the X-Agent-Id placeholder
    # below. Auth is enforced inside app.api.deps_portal, not at router level,
    # so /portal/auth/signup and /portal/auth/login can stay open.
    app.include_router(portal.router, prefix=settings.api_prefix)
    # Public/portal knowledge-base browsing -- no auth, published articles only
    # (enforced in the service layer, not here).
    app.include_router(portal_kb.router, prefix=settings.api_prefix)
    # AI chatbot -- requires a valid portal session on every route (unlike
    # portal_kb, which is fully public). Degrades to a clean in-thread
    # message, never a 500, when the AI provider is disabled or fails --
    # see app.services.ai.chatbot.send_message.
    app.include_router(portal_chat.router, prefix=settings.api_prefix)
    # Agent-scoped routers. Each declares Depends(get_current_agent) at router
    # level, so every route below is 401 without a valid X-Agent-Id. /health and
    # the pre-existing routers stay open — real auth is a follow-up story that
    # will gate them all at once.
    app.include_router(dashboard.router, prefix=settings.api_prefix)
    app.include_router(tasks.router, prefix=settings.api_prefix)
    app.include_router(quick_replies.router, prefix=settings.api_prefix)
    app.include_router(knowledge_base.router, prefix=settings.api_prefix)
    app.include_router(ai.router, prefix=settings.api_prefix)
    register_exception_handlers(app)
    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Map service-layer errors onto HTTP status codes in one place."""

    def _error(status_code: int):
        async def handler(_: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(exc)})

        return handler

    app.add_exception_handler(NotFound, _error(404))
    app.add_exception_handler(Forbidden, _error(403))
    app.add_exception_handler(Conflict, _error(409))
    app.add_exception_handler(PayloadTooLarge, _error(413))
    # AIProviderError is not a ServiceError -- Story 08 ships no central
    # mapping for it and leaves the decision to whichever story first lets
    # it propagate to a route. Story 09's "Regenerate summary" is that story:
    # an agent who clicked "Regenerate" needs to be told the AI call failed,
    # rather than swallowed into a stub fallback. Mapped once here; every
    # later story (11's recompute route) reuses this same registration.
    app.add_exception_handler(AIProviderError, _error(502))


app = create_app()
