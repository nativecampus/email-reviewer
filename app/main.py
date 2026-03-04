from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import api, dashboard, operations, settings

app = FastAPI()

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(api.router)
app.include_router(settings.router)
app.include_router(operations.router)
app.include_router(dashboard.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
