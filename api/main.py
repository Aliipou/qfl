"""QFL Platform — FastAPI entrypoint."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import (
    AccessLogMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from api.routes import audit, status, train
from api.schemas import HealthResponse

app = FastAPI(
    title="QFL Platform",
    description=(
        "Quantum Federated Learning middleware — "
        "EU AI Act + GDPR compliant, production-ready."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Security middleware stack (order matters: first added = outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(train.router)
app.include_router(status.router)
app.include_router(audit.router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """Liveness probe — returns platform health and active quantum backend."""
    return HealthResponse()


def run() -> None:
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
