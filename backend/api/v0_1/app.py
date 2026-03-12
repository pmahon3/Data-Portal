import os
from typing import List

from fastapi import Request, FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v0_1.endpoints import application_router

from contextlib import asynccontextmanager
from .startup import run_startup_tasks

@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_startup_tasks()
    yield
    from core.injection.managers import get_instance_manager
    manager = get_instance_manager()
    if hasattr(manager, 'teardown'):
        manager.teardown()



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


app_instance = App()
app = app_instance.get_app()
