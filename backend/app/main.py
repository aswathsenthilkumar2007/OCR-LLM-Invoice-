
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routes.invoice_routes import router as invoice_router

app = FastAPI(
    title="Invoice Processing AI",
    description="OCR and LLM-based invoice processing system",
    version="1.0.0"
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register invoice routes
app.include_router(invoice_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to Invoice Processing AI"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": "invoice-processing-ai"
    }
