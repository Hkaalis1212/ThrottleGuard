---
name: tg-promo-cold-outreach
description: Draft first-touch cold outreach messages for ThrottleGuard — cold email, LinkedIn DM, and phone/voicemail scripts to prospects identified via tg-promo-prospect-finder. Use when the user needs the actual opening message to a specific prospect or prospect segment, as distinct from a multi-touch nurture sequence.
---

# ThrottleGuard Cold Outreach

First-touch messages only — for full multi-step sequences with timing, hand off to tg-promo-followup instead.

## Principles for first touch

- Lead with the prospect's likely pain, not the product's feature list. A fleet maintenance manager doesn't care about "17 rules" on first contact — they care about "catch DPF failure before it derates a truck on the highway."
- One specific, credible detail beats generic claims — reference the founder's 20 years as a diesel tech, or a duty-cycle detail relevant to their operation (short-haul, engine family) if known.
- One CTA, low commitment: "worth a 15-minute look?" or "want the 17-point checklist first?" (tg-promo-lead-magnet) rather than "buy now."
- Keep it short. Cold trucking-industry audiences respond to plain, direct, no-fluff language — match the technician tone from tg-promo-positioning, not corporate SaaS voice.

## Templates to produce

**Cold email** — subject line + 3-5 sentence body + CTA. Reference something specific about their fleet if the user has it (engine family, region, fleet size from prospect research); otherwise keep it general but still specific to trucking/DPF pain, not generic SaaS.

**LinkedIn connection note + follow-up DM** — connection note ≤300 chars, no pitch; follow-up DM after they accept, slightly warmer than cold email, can reference their profile/company directly.

**Phone opener / voicemail script** — 20-30 second version for a live answer, and a separate ~15 second voicemail script that ends with a clear callback reason, not just "give me a call back."

**Trade show / in-person opener** — a few conversational openers for booth or floor conversations, since this audience often responds better in person than by email — short enough to say naturally, not read off a card.

## What NOT to do

- Don't claim to have already analyzed their specific fleet data unless that's true (e.g., don't fake "we ran your trucks through ThrottleGuard and found...").
- Don't imply urgency/scarcity that isn't real (see tg-promo-offer).
- Don't send more than one cold touch without spacing — that's what tg-promo-followup's cadence is for.
- Respect opt-out language on SMS/email per CAN-SPAM/TCPA basics — include an unsubscribe/opt-out line on any bulk email, and don't suggest cold SMS to numbers without consent.

## How to run this skill

1. Confirm the channel (email, LinkedIn, phone, in-person) and whether this is to a named prospect or a segment template.
2. Pull any specific detail available from prospect research (tg-promo-prospect-finder output) to personalize — genuinely specific outreach converts far better than templated blasts.
3. Draft 2-3 variants so the user can A/B test tone (more technical/credibility-led vs. more pain/urgency-led).
4. Remind the user this is first-touch only — offer to build the follow-up cadence via tg-promo-followup if they want the full sequence.
