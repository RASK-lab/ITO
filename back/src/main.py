from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.drawings import router as drawings_router

app = FastAPI(
    title="ITO API",
    version="0.1.0",
)

app.include_router(drawings_router)

# 検証エラーの応答に入れる理由の数の上限。点の 1 個ごとに誤りがあると 20 万件を超え、
# 応答が数十 MB になるので、先頭のこの数だけを返す。
MAX_VALIDATION_ERRORS = 20


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # 送られてきた値そのものは返さない。画像のように大きい値や、NaN のように
    # JSON にできない値が入っていると、応答を作れなくなるため。
    errors = [
        {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()[:MAX_VALIDATION_ERRORS]
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "backend",
        "version": "0.1.1",
    }
