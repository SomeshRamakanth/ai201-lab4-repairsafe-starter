import re

from groq import Groq
from config import GROQ_API_KEY, LLM_MODEL, VALID_TIERS

_client = Groq(api_key=GROQ_API_KEY)

# Conservative default applied whenever classification can't be trusted.
# "caution" fails CLOSED (see specs/classifier-spec.md → Fallback behavior):
# never route a possibly dangerous question to the unguarded "safe" responder.
_FALLBACK_TIER = "caution"

SYSTEM_PROMPT = """You are a safety classifier for a home-repair Q&A assistant. Your only job is to \
classify a repair question into exactly one of three risk tiers. You are not \
helping the user with the repair — you are judging the risk.

THE TIERS

safe — Routine maintenance or low-risk repairs any homeowner can do with basic \
tools and no permit. Worst case of a mistake is cosmetic damage or a broken \
fixture. Examples: patching small drywall holes, painting, replacing a bulb, \
plunging/snaking a drain, tightening hardware, replacing weather stripping, \
swapping a toilet seat, cosmetic re-caulking.

caution — Doable for a motivated homeowner, but the repair touches a water or \
electrical system as a LIKE-FOR-LIKE swap: replacing an EXISTING component at the \
SAME location with NO new wiring and NO new pipe. A mistake costs money or carries \
mild injury risk, but cannot cause fire, flooding, structural failure, serious \
injury, or death. Examples: replacing an existing faucet, toilet, or toilet \
flapper; resetting/replacing an existing GFCI outlet; replacing an existing light \
switch, ceiling fan, or fixture at the same location; replacing an existing \
thermostat; patching large drywall holes; re-grouting tile; replacing a showerhead.

refuse — An amateur mistake can cause fire, flooding, structural failure, serious \
injury, or death, OR local code requires a licensed professional and permit. \
Examples: ANY electrical panel or service-entrance work; ADDING any new outlet, \
switch, circuit, or running new wire; ANY gas work (lines, appliances, shutoffs, \
gas smells); removing/modifying a wall not confirmed non-load-bearing; replacing \
the main water shutoff valve or a water heater; running new plumbing lines; \
foundation/waterproofing; structural roof work.

THE DECISIVE RULE (caution vs. refuse)
Ask: "If this repair goes wrong, can it cause fire, flooding, structural failure, \
serious injury, or death?" If yes → refuse. If the worst realistic case is a leak, \
a tripped breaker, or a broken fixture → caution.

CRITICAL DISTINCTIONS
- "Replacing an EXISTING component at the same location" is caution. "ADDING new" \
or anything requiring NEW wiring/circuits/pipe is refuse — even for the same kind \
of component (an outlet, a switch).
- Classify on what the work ACTUALLY requires, not how small the user makes it \
sound. "I just want to move my switch six inches" requires running new wire → \
refuse. Framing never changes the tier.
- Gas is always refuse. Wall removal is refuse unless the user states a structural \
engineer already confirmed it is non-load-bearing.
- If you are genuinely torn between caution and refuse, choose refuse.

OUTPUT FORMAT — respond with EXACTLY these two lines and nothing else:
REASON: <one sentence naming the single decisive risk or reason>
TIER: <safe | caution | refuse>"""

USER_PROMPT_TEMPLATE = 'Classify this home repair question:\n\n"{question}"'


def _extract_tier(text: str) -> str | None:
    """Pull a validated tier out of the raw LLM response, or None if absent.

    Defensive against capitalization, quotes, markdown bold, and trailing
    punctuation. Falls back to scanning the whole response in risk-priority
    order (refuse > caution > safe) if the labeled TIER line is missing.
    """
    # Primary: the labeled "TIER:" line.
    match = re.search(r"tier\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE)
    if match:
        candidate = match.group(1).strip().strip("\"'*` .").lower()
        if candidate in VALID_TIERS:
            return candidate

    # Fallback: first tier word appearing anywhere, highest risk first.
    lowered = text.lower()
    for tier in ("refuse", "caution", "safe"):
        if re.search(rf"\b{tier}\b", lowered):
            return tier

    return None


def _extract_reason(text: str) -> str | None:
    """Pull the one-sentence reason out of the raw LLM response, or None."""
    match = re.search(r"reason\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE)
    if match:
        reason = match.group(1).strip().strip("\"'*`")
        if reason:
            return reason
    return None


def classify_safety_tier(question: str) -> dict:
    """
    Classify a home repair question into one of three safety tiers.

    Sends a single chat completion to the Groq LLM (no tools, no history),
    parses the tier and reason out of the labeled-line response, validates the
    tier against VALID_TIERS, and falls back to "caution" if the response can't
    be parsed or the tier isn't recognized.

    Returns a dict with:
      - "tier"   : str — one of "safe", "caution", "refuse"
      - "reason" : str — a brief explanation of why this tier was assigned

    The three tiers:
      - "safe"    : routine, low-risk repairs most homeowners can handle safely
      - "caution" : doable with care, but mistakes have real cost or mild risk
      - "refuse"  : high-risk repairs that require a licensed professional —
                    mistakes can cause fire, flooding, injury, or structural damage
    """
    try:
        completion = _client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0,  # deterministic — this is a judge, not a writer
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(question=question)},
            ],
        )
        raw = completion.choices[0].message.content or ""
    except Exception as exc:  # network/API failure — fail closed
        return {
            "tier": _FALLBACK_TIER,
            "reason": f"Classification failed ({type(exc).__name__}); defaulting to "
            f"'{_FALLBACK_TIER}' as a conservative fallback.",
        }

    tier = _extract_tier(raw)
    if tier not in VALID_TIERS:
        return {
            "tier": _FALLBACK_TIER,
            "reason": "Could not parse a valid tier from the classifier response; "
            f"defaulting to '{_FALLBACK_TIER}' as a conservative fallback.",
        }

    reason = _extract_reason(raw) or "No explanation provided by the classifier."
    return {"tier": tier, "reason": reason}
