from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.chat import Chat, Message
from app.models.file import File
from app.schemas.file import AIRequest, AIResponse
from app.services.ai_service import AIService
from app.core.config import settings
from app.services.subscription_service import enforce_ai_quota

router = APIRouter(prefix="/ai", tags=["AI Tools"])


@router.post("/chat", response_model=AIResponse)
async def ai_chat(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = []
    if data.system_prompt:
        messages.append({"role": "system", "content": data.system_prompt})
    messages.append({"role": "user", "content": data.prompt})
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL, temperature=data.temperature, max_tokens=data.max_tokens)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/summarize", response_model=AIResponse)
async def summarize_text(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "Format all section headings using valid Markdown headings, "
                                        "such as ## and ###. "
                                        "Under revision questions, put each question and its answer "
                                        "in separate Markdown paragraphs with a blank line between them. "
                                        "Never place a question and its answer on the same line. "
                                        "Use question and answer labels in the response language. "
                                        "Keep the content faithful to the supplied study material."},
        {"role": "user", "content": f"Summarize the following:\n\n{data.prompt}"},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/quiz", response_model=AIResponse)
async def generate_quiz(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "You are a quiz generator. Generate multiple-choice quizzes based on the provided content. Include 4 options per question with the correct answer marked."},
        {"role": "user", "content": f"Generate a quiz from the following content:\n\n{data.prompt}"},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/translate", response_model=AIResponse)
async def translate_text(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "You are a professional translator. Translate the text accurately while preserving meaning and tone."},
        {"role": "user", "content": data.prompt},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/rewrite", response_model=AIResponse)
async def rewrite_text(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "You are an expert writer. Rewrite the text to improve clarity, grammar, and style while keeping the original meaning."},
        {"role": "user", "content": f"Rewrite the following:\n\n{data.prompt}"},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/explain-code", response_model=AIResponse)
async def explain_code(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "You are an expert programmer. Explain the provided code in detail, covering what it does, how it works, and any important concepts."},
        {"role": "user", "content": f"Explain this code:\n\n{data.prompt}"},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)


@router.post("/solve-math", response_model=AIResponse)
async def solve_math(
    data: AIRequest,
    user: User = Depends(get_current_user),
    _quota: None = Depends(enforce_ai_quota),
):
    ai = AIService(api_key=settings.GEMINI_API_KEY)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a precise and patient mathematics tutor. "
                "Solve the problem step by step and explain each step clearly.\n\n"

                "MANDATORY MATHEMATICAL FORMATTING RULES:\n"
                "1. Use $...$ for inline mathematical expressions.\n"
                "2. Use $$...$$ for displayed equations, with the equation "
                "on its own line and blank lines around it.\n"
                "3. Never wrap mathematical expressions in backticks or "
                "Markdown code blocks.\n"
                "4. Use proper mathematical notation and LaTeX syntax. "
                "Write x^2, not x2, for a squared variable. "
                "Use proper notation for fractions, roots, and subscripts.\n"
                "5. Put each equation on its own line when presenting "
                "a sequence of equations. Never merge separate equations "
                "into unreadable text.\n"
                "6. Use Markdown headings and numbered steps to organize "
                "the solution.\n"
                "7. Keep all calculations mathematically correct. "
                "Do not invent missing information.\n"
                "8. End with a clearly labeled final answer.\n\n"

                "Before responding, check that the mathematical notation "
                "is correct and that the equations are properly formatted."
            ),
        },
        {
            "role": "user",
            "content": f"Solve this math problem:\n\n{data.prompt}",
        },
    ]

    response = await ai.chat(
        messages=messages,
        model=settings.GEMINI_MODEL,
        temperature=0.2,
        max_tokens=data.max_tokens,
    )

    return AIResponse(
        content=response,
        model=settings.GEMINI_MODEL,
        tokens_used=len(response.split()) * 2,
    )


@router.post("/flashcards", response_model=AIResponse)
async def generate_flashcards(data: AIRequest, user: User = Depends(get_current_user), _quota: None = Depends(enforce_ai_quota)):
    ai = AIService(api_key=settings.GEMINI_API_KEY)
    messages = [
        {"role": "system", "content": "Generate flashcards in the format:\n**Card 1**\n**Front:** [question/concept]\n**Back:** [answer/explanation]\n\nGenerate 5-10 flashcards."},
        {"role": "user", "content": f"Generate flashcards from:\n\n{data.prompt}"},
    ]
    response = await ai.chat(messages=messages, model=settings.GEMINI_MODEL)
    return AIResponse(content=response, model=settings.GEMINI_MODEL, tokens_used=len(response.split()) * 2)
