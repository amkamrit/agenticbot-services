import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:

    # Handle HTTP exceptions: 404, 401, 403, etc.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": str(exc.detail),
                "data": None,
            },
            headers=exc.headers,
        )

    # Handle request validation errors
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ):
        logger.warning(
            "Request validation failed: %s %s | Errors: %s",
            request.method,
            request.url.path,
            exc.errors(),
        )

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Validation failed",
                "errors": [
                    {
                        "field": ".".join(str(item) for item in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                    for error in exc.errors()
                ],
                "data": None,
            },
        )

    # Handle all other unhandled exceptions
    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request,
        exc: Exception,
    ):
        logger.error(
            "Unhandled exception: %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "data": None,
            },
        )
