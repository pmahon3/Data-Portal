
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v0_1.endpoints import application_router
from .startup import run_startup_tasks

from core.services.injectors import get_instance_manager, get_policy_manager, get_project_manager, get_user_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    import logging
    try:
        # Startup tasks for postgres
        await run_startup_tasks()

        # Startup singletons for the managers
        instance_manager = get_instance_manager()
        policy_manager = get_policy_manager()
        user_manager = get_user_manager()
        project_manager = get_project_manager()
    except Exception as e:
        logger = logging.getLogger("uvicorn.error")
        logger.error(f"Critical startup failure: {e}")
        sys.exit(1)

    yield

    # Cleanup and close instance connections on shutdown
    if hasattr(instance_manager, 'teardown'):
        instance_manager.teardown()


class App:
    """
    Class representing the application.

    Initializes the FastAPI app, includes routers, mounts static files, adds CORS middleware,
    and loads templates.

    Usage:
        app = App()
        my_app = app.get_app()

    Attributes:
        app: The FastAPI application.
    """

    def __init__(self):
        #self.app = FastAPI()
        self.app = FastAPI(lifespan=lifespan)

        # Include routers
        self.app.include_router(application_router)

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Adjust as needed
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # API root endpoint for React frontend
        @self.app.get("/", response_class=JSONResponse)
        async def api_root():
            """
            API root endpoint for React frontend.
            Returns basic API information.
            """
            return JSONResponse(content={
                "message": "AMS Data Portal API",
                "version": "v0.1",
                "documentation": "/docs"
            })

        @self.app.get("/test", response_class=JSONResponse)
        async def test_endpoint():
            return JSONResponse(content={"message": "The test instance_url is working."})

    def get_app(self):
        return self.app

# 1. Define the filter class
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Returns False if the log message contains health/ready endpoint paths
        msg = record.getMessage()
        return "/health" not in msg and "/ready" not in msg

# 2. Add the filter to the uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

app_instance = App()
app = app_instance.get_app()
