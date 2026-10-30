from google import genai
from google.genai import types

from app.core.config import settings


class AIServiceUnavailable(Exception):
    """A temporary upstream AI-provider failure."""

    def __init__(self, status_code: int = 503):
        self.status_code = status_code
        super().__init__("The AI provider is temporarily unavailable.")


class AIService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.GEMINI_API_KEY

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:

        # --------------------------------------------------------
        # Demo / Mock mode
        # --------------------------------------------------------

        if not self.api_key:
            return self._mock_response(messages)

        # --------------------------------------------------------
        # Create Gemini client
        # --------------------------------------------------------

        client = genai.Client(
            api_key=self.api_key
        )
        async_client = client.aio

        model_name = model or settings.GEMINI_MODEL

        # --------------------------------------------------------
        # Separate system instruction from conversation
        # --------------------------------------------------------

        system_instruction = None
        contents = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # System messages must be sent as
            # GenerateContentConfig.system_instruction
            if role == "system":
                if system_instruction:
                    system_instruction += "\n\n" + content
                else:
                    system_instruction = content

            # User messages
            elif role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text=content
                            )
                        ],
                    )
                )

            # Gemini assistant/model messages
            elif role in ("assistant", "model"):
                contents.append(
                    types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text=content
                            )
                        ],
                    )
                )

        # --------------------------------------------------------
        # Gemini requires a conversation ending with user
        # --------------------------------------------------------

        if not contents:
            raise ValueError(
                "Conversation history is empty."
            )

        if contents[-1].role != "user":
            raise ValueError(
                "Conversation history must end with a user message."
            )

        # --------------------------------------------------------
        # Gemini generation config
        # --------------------------------------------------------

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Add system instruction only when available
        if system_instruction:
            config.system_instruction = system_instruction

        # --------------------------------------------------------
        # Send request to Gemini
        # --------------------------------------------------------

        try:
            response = await async_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )

            if not response.text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return response.text

        except Exception as e:
            provider_status = (
                getattr(e, "code", None)
                or getattr(e, "status_code", None)
            )
            try:
                provider_status = int(provider_status)
            except (TypeError, ValueError):
                provider_status = None

            if provider_status == 429:
                raise AIServiceUnavailable(status_code=429) from e

            if provider_status is not None and 500 <= provider_status <= 599:
                raise AIServiceUnavailable(status_code=503) from e

            # Do not expose provider internals in the public API response.
            raise RuntimeError("Gemini request failed.") from e

        finally:
            try:
                await async_client.aclose()
            finally:
                client.close()

    # ------------------------------------------------------------
    # Mock response
    # ------------------------------------------------------------

    def _mock_response(
        self,
        messages: list[dict],
    ) -> str:
        last_msg = (
            messages[-1]["content"]
            if messages
            else ""
        )

        return (
            "**Talaba AI Demo Mode**\n\n"
            "No Gemini API Key configured.\n\n"
            f"Your message:\n\n{last_msg}"
        )