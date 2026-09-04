import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.v1.buyer import router as buyer_router
from app.api.v1.merchants import router as merchants_router
from app.api.v1.checkout import router as checkout_router
from app.core.config import get_settings
from app.db.session import get_db

settings = get_settings()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Commerce Platform API")

app.include_router(merchants_router)
app.include_router(buyer_router)
app.include_router(checkout_router)

# CORS
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")