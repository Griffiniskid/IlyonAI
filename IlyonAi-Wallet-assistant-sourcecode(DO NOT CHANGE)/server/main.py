"""
Agent Platform — FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Agent Platform API",
    version="0.1.0",
    description="AI-powered crypto wallet assistant backend",
)

# Allow the Chrome extension (chrome-extension://*) and local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
