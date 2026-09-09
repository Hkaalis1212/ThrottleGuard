---
name: tg-promo-case-study
description: Turn a real ThrottleGuard prediction/outcome, customer conversation, or usage data point into a case study, testimonial draft, or social-proof snippet. Use when the user has real (even partial) results to share and wants them turned into external-facing content — never for fabricating results.
---

# ThrottleGuard Case Studies & Social Proof

This skill only works with **real input from the user** — a real prediction outcome, a real customer quote, real trial-usage data, or at minimum a real scenario the user can vouch for. If the user hasn't supplied a real data point, say so and ask for one rather than generating a plausible-sounding fake case study.

## What counts as valid source material

- An entry from tg_predictions / outcome_db.py showing a flagged score that was later confirmed correct (or incorrect — a caught false positive can also be a legitimate "here's how granular the rules are" story if framed honestly).
- A direct quote or paraphrase from a real customer/trial user conversation, with their permission to use it (ask the user to confirm permission before drafting anything with a name/company attached).
- A real before/after scenario the founder personally diagnosed or verified.
- Aggregate, real usage stats the user has actually pulled (e.g., real trial-to-paid conversion rate, real average score distribution) — never invented placeholder stats.

## Formats to produce from real material

1. **Short social proof snippet** (1-2 sentences) for a landing page or pitch deck — "Caught a [specific rule] flag on a [engine family] truck before a scheduled service, avoided [real outcome]."
2. **Full case study** — situation (what was going on with the fleet/truck) → what ThrottleGuard flagged (specific rule + score) → action taken → outcome. Use the exact rule numbers/names from CLAUDE.md's rule table so it stays technically accurate and checkable.
3. **Testimonial-style quote drafting** — if the user has rough/informal feedback from a customer, help tighten it into a clean quote, but always mark it as a draft for the customer to approve, not a final attributed quote, unless the user confirms it's already approved.
4. **Anonymized/aggregate version** — for cases where the customer can't be named, strip identifying details but keep the technical specifics (engine family, rule fired, outcome) since that's what makes it credible.

## Hard rules

- Never fabricate a customer name, company, quote, or outcome. If the user asks for "a case study" with no real input, respond by asking what real data point they want to build from, or offer to draft a hypothetical/illustrative example clearly labeled as illustrative (not attributed to a real customer).
- Get explicit confirmation before publishing anything with a real customer's name or identifiable details.
- Keep technical details (rule numbers, thresholds, engine family) accurate to CLAUDE.md and throttleguard_engine_thresholds.py rather than approximated.

## How to run this skill

1. Ask the user for the real source material if not already provided (a prediction record, a conversation summary, usage stats).
2. Confirm whether it can be attributed (named customer) or must be anonymized/aggregate.
3. Draft in the requested format(s), keeping technical specifics accurate and flagging anything that needs the customer's sign-off before publishing.
