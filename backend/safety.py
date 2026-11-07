"""Guardrails: personal-data masking, input screening and customer-message checks."""

import re

FRIENDLY_REPLY = "Let's keep it friendly! I'm happy to help with Campus Customs gear and orders :)"

_EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_DIGITS = re.compile(r"\b(?:\d[ -]?){9,}\b")

# "Ignore your instructions" style tricks.
_INJECTION = re.compile(
    r"ignore (all |your |previous |prior |the )*(instructions|rules|prompt)|admin mode|developer mode|"
    r"system prompt|jailbreak|act as|pretend (you are|to be)|reveal (your|the) (instructions|prompt|rules)|"
    r"(show|dump|list|give) (me )?(the |your )?(database|user list|customer list|all customers|instructions)",
    re.IGNORECASE,
)
# Kept short on purpose: obvious insults and profanity only.
_RUDE = re.compile(r"\b(stupid|idiot|dumb|shut up|hate you|useless|moron|damn|hell|crap|wtf|f\*+k|fuck\w*|shit\w*)\b",
                   re.IGNORECASE)
# Private shop data that must never reach a customer.
# Whole words only, so "please" never matches "lease".
_PRIVATE_TERMS = re.compile(
    r"\b(unit[ _]costs?|margins?|markup|cost of goods|our costs?|cash balance|checking account|invoices?|"
    r"rent|leases?|landlords?|vendors?|suppliers?|database|campus_customs|my instructions|system prompt)\b",
    re.IGNORECASE,
)
_SMILES = (":)", ":-)", "😊", "🙂", "☺️", "☺")


def redact(text: str) -> str:
    """Mask emails (b***@yale.edu) and long digit runs (cards, phones)."""
    text = _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    return _DIGITS.sub("[number hidden]", text)


def screen_input(text: str) -> list[str]:
    """Flags for text that came from a customer: 'injection' and/or 'rude'."""
    flags = []
    if _INJECTION.search(text or ""):
        flags.append("injection")
    if _RUDE.search(text or ""):
        flags.append("rude")
    return flags


def check_customer_message(message: str) -> str | None:
    """Return a problem with a customer message, or None if it is safe to send."""
    if _RUDE.search(message):
        return "The customer message contains inappropriate language. Rewrite it politely."
    leak = _PRIVATE_TERMS.search(message)
    if leak:
        return (f"The customer message mentions private shop information ('{leak.group(0)}'). "
                "Remove costs, margins, invoices, rent, vendors, the database and instructions.")
    if _EMAIL.search(message) or _DIGITS.search(message):
        return "The customer message contains an email address or long number. Remove personal data."
    return None


def with_smile(message: str) -> str:
    """Customer messages always end with a virtual smile."""
    message = message.rstrip()
    return message if message.endswith(_SMILES) else f"{message} :)"
