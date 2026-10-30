import asyncio

import pytest

from app.services.ai_service import AIService, AIServiceUnavailable


class FakeProviderError(Exception):
    def __init__(self, status_code):
        super().__init__(f"simulated provider failure {status_code}")
        self.code = status_code


class FakeModels:
    def __init__(self, error):
        self.error = error

    async def generate_content(self, **kwargs):
        raise self.error


class FakeAsyncClient:
    def __init__(self, error):
        self.models = FakeModels(error)
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self, error):
        self.aio = FakeAsyncClient(error)
        self.closed = False

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    ("provider_status", "expected_status"),
    [
        (429, 429),
        (500, 503),
        (503, 503),
        (504, 503),
    ],
)
def test_transient_provider_errors_are_classified(
    monkeypatch, provider_status, expected_status
):
    fake_client = FakeClient(FakeProviderError(provider_status))
    monkeypatch.setattr(
        "app.services.ai_service.genai.Client",
        lambda **kwargs: fake_client,
    )

    service = AIService(api_key="test-key")

    with pytest.raises(AIServiceUnavailable) as caught:
        asyncio.run(
            service.chat(
                messages=[{"role": "user", "content": "Hello"}],
                model="test-model",
            )
        )

    assert caught.value.status_code == expected_status
    assert fake_client.aio.closed
    assert fake_client.closed


def test_non_transient_provider_error_hides_provider_details(monkeypatch):
    fake_client = FakeClient(FakeProviderError(400))
    monkeypatch.setattr(
        "app.services.ai_service.genai.Client",
        lambda **kwargs: fake_client,
    )

    service = AIService(api_key="test-key")

    with pytest.raises(RuntimeError, match="^Gemini request failed\\.$") as caught:
        asyncio.run(
            service.chat(
                messages=[{"role": "user", "content": "Hello"}],
                model="test-model",
            )
        )

    assert "simulated provider failure" not in str(caught.value)
    assert fake_client.aio.closed
    assert fake_client.closed
