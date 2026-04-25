"""
Agent Platform — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import router as agent_router
from app.api import auth as auth_module, chats as chats_module
from app.api.portfolio import router as portfolio_router
from app.db.database import engine
from app.db.models import Base

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Agent Platform API",
    version="0.1.0",
    description="AI-powered crypto wallet assistant backend",
)

# Exact origins allowed in addition to the chrome-extension wildcard below.
_EXTRA_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_EXTRA_ORIGINS,
    # Matches any chrome-extension:// origin (wildcard not supported in allow_origins)
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router, prefix="/api/v1")
app.include_router(auth_module.router, prefix="/api/v1")
app.include_router(chats_module.router, prefix="/api/v1")
app.include_router(portfolio_router, prefix="/api")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
