from fastapi import FastAPI

from src.judge.router import router as judge_router

app = FastAPI(
    title="ITO API",
    version="0.1.0",
)

app.include_router(judge_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "backend",
        "version": "0.1.1",
    }
