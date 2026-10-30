import pytest

from app.core.database import engine


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def cleanup_engine(anyio_backend):
    yield
    await engine.dispose()