from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

setup_logging()

api = FastAPI(
    title="Customer Chat",
    version="1.0.0",
)
register_exception_handlers(api)

api.include_router(v1_router)
