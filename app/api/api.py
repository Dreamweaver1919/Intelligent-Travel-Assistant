from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.trip import router as trip_router
from app.config import get_settings


settings = get_settings()

app = FastAPI(title="HelloAgents Trip Planner", debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(trip_router, prefix="/api/trip", tags=["trip"])
