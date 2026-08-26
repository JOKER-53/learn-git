import os

main_py_path = "api/main.py"
with open(main_py_path, "r") as f:
    content = f.read()

handler = """
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
"""

content = content.replace('app = FastAPI(title="learn-git API")', 'app = FastAPI(title="learn-git API")' + handler)

with open(main_py_path, "w") as f:
    f.write(content)

print("Exception handler added.")
