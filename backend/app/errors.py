import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("database integrity error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=409, content={"detail": "Resource already exists"})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
