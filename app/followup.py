"""Suggests the next sales action, and an email opener for Hot leads.

Hot leads get a short LLM-written suggestion when ANTHROPIC_API_KEY is set.
Without a key (or if the call fails) a simple template is used instead,
so the API always works.
"""
import json
import os

LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5-5")

ACTIONS = {
    "Hot": "Call within 1 hour and offer a counselling session.",
    "Warm": "Send a course brochure email and follow up in 2 days.",
    "Cold": "Add to the monthly newsletter; no call needed.",
}


def template_follow_up(band: str, lead: dict) -> dict:
    opener = None
    if band == "Hot":
        source = lead.get("lead_source", "our website")
        opener = (f"Hi! Thanks for your interest in our courses via {source}. "
                  "I'd love to help you pick the right program. Do you have 10 minutes today?")
    return {"next_action": ACTIONS[band], "email_opener": opener, "source": "template"}


def llm_follow_up(lead: dict, probability: float, reasons: list[dict]) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    why = "; ".join(f"{r['feature']}={r['value']} ({r['effect']} chance)" for r in reasons)
    prompt = (
        "You help sales reps at an online education company.\n"
        f"Lead details: {json.dumps(lead)}\n"
        f"Conversion probability: {probability:.0%}. Main reasons: {why}.\n"
        'Reply with JSON only: {"next_action": "<one sentence>", '
        '"email_opener": "<two friendly sentences addressed to the lead>"}'
    )
    response = client.beta.messages.create(
        model=LLM_MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    return {"next_action": data["next_action"], "email_opener": data["email_opener"], "source": "llm"}


def suggest(band: str, lead: dict, probability: float, reasons: list[dict]) -> dict:
    if band == "Hot" and os.getenv("ANTHROPIC_API_KEY"):
        try:
            return llm_follow_up(lead, probability, reasons)
        except Exception as e:  # network error, bad JSON, refusal...
            print(f"LLM follow-up failed, using template: {e}")
    return template_follow_up(band, lead)
