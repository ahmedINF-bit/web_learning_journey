from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.auth import router
from app.core.database import get_db
from app.core.rate_limit import limiter


def test_forgot_password_returns_429_after_rate_limit():
    limiter.reset()

    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None
    )

    async def override_get_db():
        yield db

    test_app = FastAPI()
    test_app.state.limiter = limiter
    test_app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,
    )
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(test_app) as client:
            for _ in range(3):
                response = client.post(
                    "/api/v1/auth/forgot-password",
                    json={"email": "unknown@example.com"},
                )
                assert response.status_code == 200

            response = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "unknown@example.com"},
            )

            assert response.status_code == 429

    finally:
        limiter.reset()