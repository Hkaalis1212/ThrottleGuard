---
name: tg-promo-objection-handling
description: Draft responses to common sales objections for ThrottleGuard (price, "we already use telematics," skepticism about a rule-based vs. AI system, "our dealer already handles this"). Use when the user is prepping for a call, writing an FAQ/objections section, or got pushback from a real prospect and needs a response.
---

# ThrottleGuard Objection Handling

Match responses to the real product facts (see CLAUDE.md) — never argue past what the product actually does.

## Common objections and how to answer them

**"We already use Samsara/Motive/Geotab for telematics."**
ThrottleGuard isn't a telematics replacement — it's a scoring layer on top of aftertreatment data. It works standalone from a CSV export, and has a native Motive ingestion adapter if they're already on Motive (Samsara/Geotab adapters are on the roadmap in tg_telematics_adapters.py, not live yet — don't promise them as available today). Reframe: "keep your telematics stack, add the DPF/SCR-specific scoring it doesn't do."

**"Our dealer/tech already checks this at service intervals."**
Service intervals are scheduled, not predictive — the truck can go from fine to derated between visits. ThrottleGuard scores continuously (per upload/data pull), so it catches drift (e.g., regen requesting at progressively lower temps) between scheduled visits, when it's cheapest to act.

**"This is just AI guessing — why would I trust a black box?"**
It's the opposite of a black box: 17 explicit, named rules, tuned per engine family, and every flag shows exactly which rule fired and why (e.g., "Rule 11: NOx conversion <50% — EPA derate risk"). A tech can verify every score against what they already know. This is a genuine differentiator — lean into it, don't get defensive.

**"That's more than I want to spend on software."** (pricing is per-truck tiered — $39/$29/$19 per truck/mo depending on fleet size, see tg_subscription.py)
Anchor against the cost of one DPF replacement or one EPA derate roadside event — a single avoided incident pays for months to years of the subscription, and the per-truck rate drops as the fleet grows. Also remind them: 14-day trial, no card, so the cost of finding out if it's worth it is zero.

**"How do I know the thresholds are actually right for my engines?"**
The three supported families (Detroit, Volvo/Mack, Cummins/PACCAR) have distinct thresholds because they behave differently — this isn't one generic ruleset stretched across all engines. If they run a family not yet supported, say so honestly rather than implying coverage that doesn't exist.

**"We're a small fleet / owner-operator — is this overkill?"**
One DPF failure hits a small fleet or owner-operator harder (no backup truck, no reserve budget) than a large fleet — arguably higher-stakes for them, not lower. Frame the trial as a no-risk way to find out before the next regen cycle.

**"We tried a similar tool before and it was all false alarms."**
Ask what tool, if known — but the general answer is: false-alarm-prone tools usually use one generic threshold set. ThrottleGuard's engine-family-specific thresholds and multi-signal rules (e.g., requiring both inlet and outlet to cross a floor before flagging a sensor delta fault) are specifically designed to cut noise a generic system would throw.

## How to run this skill

1. If the user shares a real objection they got, match it to the closest category above and tailor the answer to their specific wording rather than pasting the generic version.
2. If it's a genuinely new objection not covered, draft a response using the same standard: answer from real product facts, don't be defensive, redirect to the trial as proof when possible.
3. For call prep, produce a condensed one-line "if they say X, say Y" cheat sheet in addition to the full answers.
