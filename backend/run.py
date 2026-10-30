import os
from dotenv import load_dotenv

load_dotenv()

from app.core.config import settings

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
