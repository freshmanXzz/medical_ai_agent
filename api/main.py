"""FastAPI 后端应用入口。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    from martin.agent.sessions import close_default_checkpointer

    close_default_checkpointer()


app = FastAPI(
    title="Martin Medical AI Agent API",
    description="Martin 医学智能体 Web 接口",
    version="0.1.0",
    lifespan=lifespan,
)

default_origins = "http://127.0.0.1:5173,http://localhost:5173"
allowed_origins = [
    origin.strip()
    for origin in os.environ.get("MARTIN_WEB_ORIGINS", default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Martin Medical AI Agent"}


from api.routers import agent, image, report, sessions

app.include_router(agent.router, prefix="/api")
app.include_router(image.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")


class SPAStaticFiles(StaticFiles):
    """为 Vue history 路由提供 index.html 回退。"""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
