from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.ai_service as ai_service_module
from app.services.ai_service import AIService


@pytest.mark.anyio
async def test_ai_service_uses_async_gemini_client(monkeypatch):
    generate_content = AsyncMock(
        return_value=SimpleNamespace(text="Generated answer")
    )
    close_async = AsyncMock()
    close_sync = Mock()

    async_client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=generate_content,
        ),
        aclose=close_async,
    )

    client = SimpleNamespace(
        aio=async_client,
        close=close_sync,
    )

    client_factory = Mock(return_value=client)
    monkeypatch.setattr(
        ai_service_module.genai,
        "Client",
        client_factory,
    )

    service = AIService(api_key="test-api-key")

    result = await service.chat(
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ],
        model="test-model",
        temperature=0.2,
        max_tokens=100,
    )

    assert result == "Generated answer"
    generate_content.assert_awaited_once()
    assert generate_content.await_args.kwargs["model"] == "test-model"
    assert generate_content.await_args.kwargs["config"].temperature == 0.2
    close_async.assert_awaited_once()
    close_sync.assert_called_once()