"""AI assistance routes (event description, email drafts) using emergentintegrations Claude."""
import os
import logging
from fastapi import Depends, HTTPException

from models import AIEventReq, AIEmailReq


logger = logging.getLogger("clubhaven")


async def run_claude(system_message: str, user_prompt: str, session_id: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id,
        system_message=system_message,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    msg = UserMessage(text=user_prompt)
    return await chat.send_message(msg)


def register(api, *, require_admin):
    """Wire the /ai routes onto api using supplied deps."""

    @api.post("/ai/event-description")
    async def ai_event_description(body: AIEventReq, admin: dict = Depends(require_admin)):
        system = ("You are a friendly community manager who writes warm, vivid event descriptions "
                  "(120-180 words) for a members club. Avoid hype. Keep it inclusive, concrete, and inviting.")
        prompt = (f"Write a compelling event description.\nEvent title: {body.title}\n"
                  f"Topic/details: {body.topic}\nAudience: {body.audience}\nTone: {body.tone}\n"
                  "Include a short opening hook, what attendees will do, and a closing CTA line.")
        try:
            text = await run_claude(system, prompt, f"event-desc-{admin['id']}")
            return {"text": text}
        except Exception as e:
            logger.exception("AI event description failed")
            raise HTTPException(status_code=502, detail=f"AI error: {e}")

    @api.post("/ai/draft-email")
    async def ai_draft_email(body: AIEmailReq, admin: dict = Depends(require_admin)):
        system = ("You draft warm, concise emails to club members. 150-220 words. Plain-text friendly. "
                  "Use a short greeting, two body paragraphs, and a clear CTA.")
        prompt = (f"Subject: {body.subject}\nGoal of the email: {body.goal}\nTone: {body.tone}\n"
                  "Start with 'Hi friends,' and sign off as 'The Club Team'.")
        try:
            text = await run_claude(system, prompt, f"email-{admin['id']}")
            return {"text": text}
        except Exception as e:
            logger.exception("AI email draft failed")
            raise HTTPException(status_code=502, detail=f"AI error: {e}")
