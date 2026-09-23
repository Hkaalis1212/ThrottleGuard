---
name: tg-promo-positioning
description: Craft or refine ThrottleGuard's core positioning — elevator pitch, one-liners, ICP definition, and differentiation vs. telematics platforms and dealer service intervals. Use when the user needs to explain what ThrottleGuard is, who it's for, or why it beats the alternative in a given number of words or for a given audience (owner-operator, fleet maintenance director, shop owner, investor).
---

# ThrottleGuard Positioning

Generate positioning copy that is true to the product. Never invent capabilities.

## Ground truth (always pull from here, not from memory of prior drafts)

- **What it is**: a rule-based expert system for DPF + SCR predictive maintenance, not ML/AI in the black-box sense. 17 explicit rules across the full aftertreatment system, tuned per engine family (Detroit, Volvo/Mack, Cummins/PACCAR). Every flag names the exact rule that fired and a plain-English action.
- **Who built it**: AHC Developers, founder has ~20 years as a diesel technician (Detroit, Volvo/Mack, Cummins/PACCAR). This is the single strongest trust signal — a shop-floor system built by someone who has actually pulled DPFs, not a software team guessing at thresholds.
- **Business model**: standalone SaaS, 14-day free trial (no credit card required), then per-truck tiered pricing — $39/truck/mo (1-10 trucks), $29/truck/mo (11-50), $19/truck/mo (51-250), custom quote for 250+. Confirm current figures in `tg_subscription.py`'s `PRICING_TIERS` before quoting, since this is the fact most likely to drift. Optional bundle with Fleet Optimizer — never required.
- **Who it's for**: commercial diesel fleets running Detroit, Volvo/Mack, or Cummins/PACCAR engines — fleet maintenance managers, shop owners, and owner-operators who want to catch DPF/SCR failures before a roadside derate or a $3-8k DPF replacement.
- **The core wedge**: EPA derate risk (NOx conversion <50%) and unplanned DPF failure are expensive and disruptive. Dealer scan tools tell you it's broken after it's broken. ThrottleGuard scores every truck 0-100 daily/per-upload and tells you *before* the light comes on.

## Real differentiators (use these, don't invent others)

1. **Explainable, not a black box.** Every score shows the rule number, what tripped it, and what to do about it — a tech can verify it against what they know, an AI "confidence score" they can't.
2. **Engine-family-aware thresholds.** A Detroit 1-Box shares DPF+SCR in one housing (a thermal event hits both); Volvo/Mack and Cummins/PACCAR have different regen temp ceilings. Generic OBD tools use one threshold for everything.
3. **Built from the field, not a dataset.** Rules encode specific tech knowledge (ash vs. soot backpressure, EGT channeling, short-haul duty cycle clogging) that a generic anomaly detector wouldn't know to look for.
4. **No forced telematics lock-in.** Works from a CSV upload standalone; Motive ingestion is an added convenience, not a requirement. Fleets don't have to rip out their existing stack.
5. **Cheap relative to one avoided failure.** Even a mid-size fleet's annual bill is a fraction of a single DPF replacement ($3-8k+) or one EPA derate roadside call — do the actual math against the fleet's tier rather than citing one fixed number.

## What NOT to say

- Never call it "AI-powered," "machine learning," or "predictive AI" — it's explicitly rule-based (v2 replaced an XGBoost v1). If the user's draft says this, flag it and fix it.
- Don't claim real-time OBD streaming unless the user confirms the Motive integration is live for that fleet — default assumption is CSV upload or configured telematics adapter.
- Don't promise specific dollar savings without the user supplying real numbers — use ranges framed as industry-typical, not ThrottleGuard-verified stats, unless they give you verified figures.

## How to run this skill

1. Ask (or infer from context) the audience and format needed: one-liner, 30-second elevator pitch, website hero copy, investor blurb, LinkedIn bio line, etc. Ask the target word/character count if it matters (e.g. Twitter/X, meta description).
2. Pick 1-2 differentiators from the list above that fit that audience best — don't cram all five into one pitch. A shop owner cares about #1 and #3; a fleet director cares about #2 and #5; an owner-operator cares about #5 and simplicity.
3. Draft 2-3 variants at different levels of technical density so the user can pick a tone.
4. Keep the founder's technician credibility as a recurring anchor across variants where space allows — it's the trust unlock this category needs (buyers are skeptical of software vendors selling into a mechanical domain).
