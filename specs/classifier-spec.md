# Spec: `classify_safety_tier()`

**File:** `safety.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Determine whether a home repair question is safe to answer directly, requires a cautionary response, or should be refused with a referral to a licensed professional.

---

## Input / Output Contract

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The user's home repair question |

**Output:** `dict`

| Key | Type | Description |
|-----|------|-------------|
| `"tier"` | `str` | One of: `"safe"`, `"caution"`, `"refuse"` |
| `"reason"` | `str` | One sentence explaining why this tier was assigned |

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Tier definitions

*Write a one-sentence definition for each tier that is precise enough to use as part of your classification prompt. Vague definitions produce inconsistent classifications.*

**safe:**
```
Routine maintenance or a low-risk repair any homeowner can do with basic tools and no permit, where the worst outcome of a mistake is cosmetic damage or a broken fixture — never injury, fire, or flooding.
```

**caution:**
```
A repair a motivated homeowner can complete but that touches a water or electrical system in a like-for-like way (swapping an existing component at the same location, no new wiring or new pipe), where a mistake costs money or carries mild injury risk but cannot cause fire, flooding, structural failure, serious injury, or death.
```

**refuse:**
```
A repair where an amateur mistake can cause fire, flooding, structural failure, serious injury, or death — or that legally requires a licensed professional/permit — including all gas work, all electrical panel/service work, adding any new circuit/outlet/switch or running new wire or pipe, wall removal, water-heater and main-shutoff-valve replacement, and any structural/foundation/roof-framing work.
```

---

### Classification approach

*How will the LLM classify the question? Will you give it just the tier definitions, or also examples (few-shot)? Will you ask it to reason step-by-step before naming the tier, or output the tier directly?*

*Consider: what happens when a question is genuinely ambiguous — e.g., "can I replace my own outlets?" Which tier should that land in, and how does your approach handle questions at the boundary?*

```
Definitions + few-shot examples + brief reasoning, in that order.

- Definitions alone leave "risky" up to the model's interpretation, which drifts
  question-to-question. The caution/refuse boundary is exactly where that drift
  causes harm, so definitions are necessary but not sufficient.
- I add few-shot examples drawn straight from the Tier Guide, with the
  "replace existing outlet" (caution) vs. "add new outlet" (refuse) contrast as
  the anchor pair, plus a gas example and a "small fix" framing example. Examples
  teach the boundary mechanically in a way prose can't.
- I ask the model to give a one-sentence reason BEFORE it isn't reasoning at length
  — it states the decisive risk, then the tier. This nudges it to apply the
  "what's the worst case?" rule rather than pattern-match on keywords, without
  producing long chains of thought that are hard to parse.

Ambiguity rule: when a question doesn't specify whether work is "replace existing"
vs. "add new" (e.g. "can I replace my own outlets?"), classify on the most
plausible literal reading. "Replace" of an existing component at the same location
is caution; anything that implies new wiring/circuits/pipe or that is inherently
high-risk (gas, panel, structural) is refuse. When genuinely torn between caution
and refuse, the prompt instructs the model to pick the HIGHER-risk tier (refuse) —
failing closed at the boundary is the safe direction.
```

---

### Output format

*How will the LLM communicate the tier and reason back to you? Describe the exact text format you'll ask it to use, so you can parse it reliably.*

*The format you used in Lab 3 (`Label: X / Reasoning: Y`) is a reasonable starting point, but you're not required to use it. Whatever you choose, you'll need to parse it in code — so consider how much variation the LLM might introduce and how you'll handle that.*

```
Two labeled lines, REASON first so the model commits to its rationale before naming
the tier:

REASON: <one sentence naming the decisive risk>
TIER: <safe | caution | refuse>

Parsing plan (defensive — assume the model may vary capitalization, add quotes,
markdown bold, or a trailing period):
  1. Scan lines for the one starting with "TIER" (case-insensitive); take the text
     after the colon.
  2. Lowercase it, strip surrounding whitespace, quotes, asterisks, and punctuation.
  3. If the cleaned value isn't an exact member of VALID_TIERS, scan the whole
     response for the first occurrence of "refuse"/"caution"/"safe" (in that
     risk-priority order) as a fallback extraction.
  4. Extract REASON similarly; if absent, fall back to a generic reason string.
  5. Only after the tier is validated against VALID_TIERS does it enter the pipeline.
```

---

### Prompt structure

*Write the actual prompt you'll use — both the system message and the user message. Don't describe it — write it. Vague prompt descriptions produce vague prompts, which produce inconsistent classifications.*

**System message:**
```
You are a safety classifier for a home-repair Q&A assistant. Your only job is to
classify a repair question into exactly one of three risk tiers. You are not
helping the user with the repair — you are judging the risk.

THE TIERS

safe — Routine maintenance or low-risk repairs any homeowner can do with basic
tools and no permit. Worst case of a mistake is cosmetic damage or a broken
fixture. Examples: patching small drywall holes, painting, replacing a bulb,
plunging/snaking a drain, tightening hardware, replacing weather stripping,
swapping a toilet seat, cosmetic re-caulking.

caution — Doable for a motivated homeowner, but the repair touches a water or
electrical system as a LIKE-FOR-LIKE swap: replacing an EXISTING component at the
SAME location with NO new wiring and NO new pipe. A mistake costs money or carries
mild injury risk, but cannot cause fire, flooding, structural failure, serious
injury, or death. Examples: replacing an existing faucet, toilet, or toilet
flapper; resetting/replacing an existing GFCI outlet; replacing an existing light
switch, ceiling fan, or fixture at the same location; replacing an existing
thermostat; patching large drywall holes; re-grouting tile; replacing a showerhead.

refuse — An amateur mistake can cause fire, flooding, structural failure, serious
injury, or death, OR local code requires a licensed professional and permit.
Examples: ANY electrical panel or service-entrance work; ADDING any new outlet,
switch, circuit, or running new wire; ANY gas work (lines, appliances, shutoffs,
gas smells); removing/modifying a wall not confirmed non-load-bearing; replacing
the main water shutoff valve or a water heater; running new plumbing lines;
foundation/waterproofing; structural roof work.

THE DECISIVE RULE (caution vs. refuse)
Ask: "If this repair goes wrong, can it cause fire, flooding, structural failure,
serious injury, or death?" If yes → refuse. If the worst realistic case is a leak,
a tripped breaker, or a broken fixture → caution.

CRITICAL DISTINCTIONS
- "Replacing an EXISTING component at the same location" is caution. "ADDING new"
  or anything requiring NEW wiring/circuits/pipe is refuse — even for the same kind
  of component (an outlet, a switch).
- Classify on what the work ACTUALLY requires, not how small the user makes it
  sound. "I just want to move my switch six inches" requires running new wire →
  refuse. Framing never changes the tier.
- Gas is always refuse. Wall removal is refuse unless the user states a structural
  engineer already confirmed it is non-load-bearing.
- If you are genuinely torn between caution and refuse, choose refuse.

OUTPUT FORMAT — respond with EXACTLY these two lines and nothing else:
REASON: <one sentence naming the single decisive risk or reason>
TIER: <safe | caution | refuse>
```

**User message:**
```
Classify this home repair question:

"{question}"
```

---

### Caution/refuse boundary

*The most consequential classification decision is whether a question lands in "caution" or "refuse." Write down your rule for this boundary — one sentence. Then give two examples of questions that sit close to the line and explain which side they fall on and why.*

```
Rule: If a mistake in this repair can cause fire, flooding, structural failure,
serious injury, or death — or the work creates NEW electrical/plumbing
infrastructure (new wire, circuit, or pipe) — it is refuse; if the worst realistic
outcome is a leak, a tripped breaker, or a broken fixture from a like-for-like swap,
it is caution.

Example A — "Can I replace an electrical outlet that stopped working?" → CAUTION.
The outlet sits on an existing circuit; this is a component swap at the same
location with no new wiring. The worst case of a wiring error is a tripped breaker,
which is recoverable. No new infrastructure → caution.

Example B — "Can I add a new electrical outlet to my garage?" → REFUSE.
"Adding new" means running a new circuit from the panel to a new location: opening
the panel, pulling wire through walls, and a permit. An amateur mistake creates a
latent fire hazard that may go undiscovered for years. New infrastructure + fire
risk → refuse. Same component as Example A, opposite tier — the verb ("replace" vs.
"add") is the boundary.
```

---

### Fallback behavior

*What does your function return if the LLM response can't be parsed — e.g., if it produces free-form prose instead of your expected format? What happens when tier validation against `VALID_TIERS` fails?*

*Note: failing open (returning "safe" as a fallback) is more dangerous than failing closed (returning "caution"). Which makes more sense here, and why?*

```
Fallback tier: "caution". This applies in two cases — (1) the LLM call raises an
exception or returns text with no extractable tier, and (2) the extracted string
is not a member of VALID_TIERS after normalization.

Why caution and not safe: returning "safe" fails OPEN — it would route a possibly
dangerous question to the safe-tier responder, which gives full DIY instructions
with no warnings. That is the single worst outcome the safety layer exists to
prevent. Returning "caution" fails CLOSED: the worst that happens to a genuinely
safe question is that it gets unnecessary warnings (mildly annoying), while a
genuinely dangerous question still gets the caution responder's strong "consider a
professional" framing rather than uncritical step-by-step help.

Why not "refuse" as the fallback: refuse blocks ALL instructions, so defaulting
there would make every parse failure look like a refusal and would over-refuse safe
questions to the point of breaking the product. Caution is the right middle:
conservative on safety without making the assistant useless when parsing hiccups.
The reason field on a fallback states plainly that classification failed and a
conservative default was applied, so it shows up clearly in the audit log.
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 2.*

**One classification that surprised you — question, tier you expected, tier it returned, and why:**

```
"How do I unclog a slow bathroom drain?" — I expected this could drift to caution
because it touches a water/drain system, and the caution definition mentions "water
systems." Instead the model correctly returned SAFE, with the reason: "the worst
realistic case of a mistake is a broken fixture or cosmetic damage." That was the
right call (plunging/snaking is in the safe examples), but it surprised me how
cleanly the "what's the worst case?" rule overrode the surface-level "it's plumbing"
signal — exactly the mechanical-rule behavior the prompt was designed to produce.
```

**One prompt change you made after seeing the first few outputs, and what it fixed:**

```
I put REASON before TIER in the output format (rather than TIER first). Asking the
model to commit to the decisive risk in one sentence BEFORE naming the tier made the
borderline electrical cases more consistent — it forces the model to actually apply
the "what can go wrong?" rule instead of pattern-matching the component word
("outlet") and guessing. With TIER first, "replace an outlet" vs. "add an outlet"
were occasionally collapsed to the same tier; with REASON first, all 9 test cases —
including the full replace/add pair and the "move switch six inches" framing trap —
landed correctly.
```
