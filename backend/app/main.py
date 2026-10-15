from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import get_settings
from app.voice.ws import router as voice_router

app = FastAPI(title="OmniAssist AI", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins),
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(voice_router)


@app.get("/health")
def health():
    return {"status": "ok"}
