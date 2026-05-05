"""/api/auth/* — identity routes (none / apikey / jwt verify)."""

from fastapi import APIRouter

from .me import router as me_router


def install_auth_routes(app) -> None:  # type: ignore[no-untyped-def]
    root = APIRouter(prefix="/api/auth")
    root.include_router(me_router)
    app.include_router(root)
