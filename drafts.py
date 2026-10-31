import json
import os
from concurrent.futures import ThreadPoolExecutor

from score import inr

MODEL = os.getenv("ALUMNI_MODEL", "claude-sonnet-5-5")
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)

SYSTEM = """You write fundraising notes for IIT Bombay to its own alumni.
Rules:
Open with their real connection to IIT Bombay, using only the facts given.
Mention their company's recent milestone lightly, as congratulations, never as the reason for asking.
Make one specific ask tied to the need, with the amount if given, and say what it pays for.
Offer a short call. Under 120 words. Warm, plain, specific. No flattery, no buzzwords.
Never guess anyone's wealth. Never invent facts, names of students, or numbers.
Never use em dashes, en dashes or double hyphens. Use commas or full stops.
Reply with JSON only: {"subject": "...", "body": "..."}"""


def clean(text):
    if not isinstance(text, str):
        return text
    text = text.replace(" " + EM_DASH + " ", ", ").replace(EM_DASH, ", ").replace(EN_DASH, "-")
    while "-" * 2 in text:
        text = text.replace("-" * 2, "-")
    return text.replace(" ,", ",")


def template(prospect, need, signer):
    first = prospect["name"].split()[0]
    amount = inr(need.get("amount_inr"))
    if amount and amount.replace("₹", "") not in need["purpose"]:
        ask = f"We are raising {amount} for this"
    else:
        ask = "We are raising funds for this"
    body = (
        f"Dear {first},\n\n"
        f"I am writing from IIT Bombay, where you did your {prospect['study']}. "
        f"Congratulations on the recent milestone at {prospect['company']}.\n\n"
        f"{need['purpose'].rstrip('.')}. {ask}, and given your path from Powai to {prospect['company']}, "
        f"you came to mind as someone who might want to be part of it.\n\n"
        f"Would you be open to a 15 minute call in the next couple of weeks?\n\n"
        f"Warm regards,\n{signer}"
    )
    return {"subject": f"An IIT Bombay request: {need['purpose'][:60]}", "body": body, "source": "template"}


def claude_draft(prospect, need, signer, client):
    facts = {
        "alum_name": prospect["name"],
        "iit_bombay_study": prospect["study"],
        "current_role": f"{prospect['title']} at {prospect['company']}",
        "company_milestone": prospect["company_event"],
        "why_they_fit": prospect["reasons"],
        "need": need["purpose"],
        "amount": inr(need.get("amount_inr")) or "not specified",
        "signed_by": signer,
    }
    reply = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(facts, indent=2)}],
    )
    raw = "".join(b.text for b in reply.content if getattr(b, "type", "") == "text")
    draft = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    return {"subject": clean(draft["subject"]), "body": clean(draft["body"]), "source": MODEL}


def write_drafts(prospects, need, signer, use_llm=True, limit=10):
    client = None
    if use_llm and os.getenv("ANTHROPIC_API_KEY"):
        try:
            from anthropic import Anthropic
            client = Anthropic()
        except Exception:
            client = None

    def one(p):
        if client is None:
            return template(p, need, signer)
        try:
            return claude_draft(p, need, signer, client)
        except Exception as err:
            draft = template(p, need, signer)
            draft["source"] = f"template (Claude failed: {type(err).__name__})"
            return draft

    targets = prospects[:limit]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for p, draft in zip(targets, pool.map(one, targets)):
            p["draft"] = draft
    return prospects
