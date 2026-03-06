from datetime import date
from typing import Optional

from sqlalchemy import CheckConstraint, Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base

DEFAULT_INITIAL_EMAIL_PROMPT = """You are an expert sales email evaluator. Score the following outgoing sales email on four dimensions, each from 1 (worst) to 10 (best):

1. **personalisation** - How tailored is the email to the specific recipient? Does it reference their company, role, recent activity, or pain points?
2. **clarity** - Is the message easy to read and understand? Is it concise with a clear structure?
3. **value_proposition** - Does the email clearly articulate what value the sender offers to the recipient?
4. **cta** - Is there a clear, specific call to action? Is it easy for the recipient to take the next step?

Respond with ONLY a JSON object in this exact format, no other text:
{
  "personalisation": <1-10>,
  "clarity": <1-10>,
  "value_proposition": <1-10>,
  "cta": <1-10>,
  "notes": "<brief 1-2 sentence explanation of the scores>"
}"""

DEFAULT_CHAIN_EMAIL_PROMPT = """You are an expert sales email evaluator. Score the following email within the context of its conversation chain on four dimensions, each from 1 (worst) to 10 (best):

1. **personalisation** - How tailored is the email to the specific recipient and conversation context?
2. **clarity** - Is the message easy to read and understand? Is it concise with a clear structure?
3. **value_proposition** - Does the email clearly articulate what value the sender offers?
4. **cta** - Is there a clear, specific call to action?

Respond with ONLY a JSON object in this exact format, no other text:
{
  "personalisation": <1-10>,
  "clarity": <1-10>,
  "value_proposition": <1-10>,
  "cta": <1-10>,
  "notes": "<brief 1-2 sentence explanation of the scores>"
}"""

DEFAULT_CHAIN_EVALUATION_PROMPT = """You are an expert sales conversation evaluator. Evaluate the following email conversation chain on four dimensions, each from 1 (worst) to 10 (best):

1. **progression** - How well does the conversation advance toward the sales goal across emails?
2. **responsiveness** - How timely and relevant are the follow-ups?
3. **persistence** - Does the sender maintain appropriate follow-up cadence without being pushy?
4. **conversation_quality** - Overall quality of the conversation as a multi-touch sales engagement.

Respond with ONLY a JSON object in this exact format, no other text:
{
  "progression": <1-10>,
  "responsiveness": <1-10>,
  "persistence": <1-10>,
  "conversation_quality": <1-10>,
  "notes": "<brief 1-2 sentence explanation of the scores>"
}"""


class Settings(AuditMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_row_settings"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    global_start_date: Mapped[date] = mapped_column(
        Date, default=date(2025, 9, 1)
    )
    company_domains: Mapped[str] = mapped_column(
        String, default="nativecampusadvertising.com,native.fm"
    )
    scoring_batch_size: Mapped[int] = mapped_column(Integer, default=5)
    auto_score_after_fetch: Mapped[bool] = mapped_column(default=True)

    initial_email_prompt: Mapped[Optional[str]] = mapped_column(
        Text, default=DEFAULT_INITIAL_EMAIL_PROMPT
    )
    chain_email_prompt: Mapped[Optional[str]] = mapped_column(
        Text, default=DEFAULT_CHAIN_EMAIL_PROMPT
    )
    chain_evaluation_prompt: Mapped[Optional[str]] = mapped_column(
        Text, default=DEFAULT_CHAIN_EVALUATION_PROMPT
    )
    weight_value_proposition: Mapped[float] = mapped_column(Float, default=0.35)
    weight_personalisation: Mapped[float] = mapped_column(Float, default=0.30)
    weight_cta: Mapped[float] = mapped_column(Float, default=0.20)
    weight_clarity: Mapped[float] = mapped_column(Float, default=0.15)
