---
name: tg-promo-demo-script
description: Build the live demo / onboarding call script and talk track for walking a prospect through ThrottleGuard — what to show, in what order, and how to handle the trial-to-paid conversation at the end. Use when the user is prepping for a sales call, demo, or trial onboarding session.
---

# ThrottleGuard Demo Script

Structure the demo around the product's actual flow and real strengths — don't script around features that don't exist yet (e.g., don't demo Samsara/Geotab live ingestion, which isn't built).

## Recommended demo structure

**1. Open with their pain, not the product (2 min)**
Ask what's actually costing them right now — surprise DPF bills, a recent derate, dealer visits that don't catch problems early. Let their answer set which parts of the demo to emphasize.

**2. Show the scoring, not the settings (5-7 min)**
Use tg_demo_data.py's 30-truck demo fleet (5 CRITICAL/8 HIGH/9 MEDIUM/8 LOW) to show real score spread immediately rather than an empty dashboard. Walk one CRITICAL truck end to end: score → which rule(s) fired → the plain-English action. This is the "aha" moment — a prospect who's skeptical of AI black boxes sees an actual named rule and a specific number, not a vague risk label.

**3. Show engine-family awareness (2-3 min)**
If they run more than one engine family, pull up examples from each and show the threshold differs — reinforces it's not one generic ruleset.

**4. Show how easy data gets in (2-3 min)**
CSV upload path first (works for everyone, no integration needed) — then mention Motive ingestion if relevant to them. Be explicit that Samsara/Geotab adapters aren't live yet if they ask.

**5. Role-appropriate view (1-2 min, only if relevant)**
If multiple stakeholders are on the call, briefly note the role model (Admin/Technician/Viewer) so it's clear techs and viewers get appropriately scoped access, not a sales pitch on permissions.

**6. Trial CTA close (2-3 min)**
14 days, full access, no card. Ask directly: "want me to get your fleet's data in today so you have real numbers by [specific date]?" — anchor to a concrete near-term date, not a vague "let me know."

## Objection moments to be ready for mid-demo

Route any pushback that comes up live to tg-promo-objection-handling's answers (price, "we already use telematics," "is this just AI guessing," dealer-already-checks-this) rather than improvising off-script.

## Trial onboarding call variant (post-signup, not a sales demo)

Shorter, action-oriented: get their real data uploaded live on the call if possible, walk through their actual first scores (not demo data), set a concrete follow-up date before trial expiry (see tg-promo-followup's day-7 checkpoint), and identify one internal champion who'll check the dashboard regularly.

## How to run this skill

1. Ask whether this is a cold prospect demo or a post-signup onboarding call — the structure differs (demo data vs. their real data, sales close vs. activation focus).
2. Ask what's known about the prospect (engine family, pain point, fleet size) to tailor which sections to spend more time on.
3. Produce a script with rough timing per section, plus a short "if this comes up" cheat sheet for likely objections during the call.
4. If the demo needs real numbers/screenshots, note that as a prep step rather than fabricating what the dashboard would show.
