---
name: tg-promo-lead-magnet
description: Design and draft lead magnets for ThrottleGuard (checklists, calculators, guides) that capture fleet manager/owner-operator emails and naturally lead into the trial signup. Use when the user wants a downloadable asset, opt-in freebie, or gated content idea for their funnel.
---

# ThrottleGuard Lead Magnets

The best lead magnets here are direct byproducts of the product's real IP — they demonstrate expertise and set up the "run this automatically" CTA naturally, instead of generic industry fluff.

## High-fit lead magnet ideas (in priority order)

1. **"17-Point DPF & SCR Failure Checklist"** — a printable/PDF version of the rule categories in plain language (clogging signs, thermal shock signs, sensor fault signs, DEF quality checks, etc.), grouped by system (DPF vs. SCR) with a plain-English "what to check" per item. This is the single strongest lead magnet: it's literally the product's rule library made manual, so the pitch to automate it is a one-line CTA at the end ("or let ThrottleGuard run all 17 checks on every truck automatically — free 14-day trial").
2. **DPF Failure Cost Calculator** — simple interactive or static calculator: inputs (fleet size, average DPF replacement cost, average derate/downtime cost per incident, estimated incidents/year) → output (estimated annual cost of unplanned aftertreatment failures). Positions ThrottleGuard's price as trivial by comparison.
3. **Engine-Family Threshold Cheat Sheet** — a one-page reference of regen temp ceilings and key thresholds per engine family (Detroit / Volvo-Mack / Cummins-PACCAR), pulled from throttleguard_engine_thresholds.py values, framed as "know your truck's real limits" — useful standalone, and shows the product's engine-family awareness is real.
4. **"5 Signs Your DPF Is About to Derate You" guide** — short educational PDF/email-course covering: outlet temp behavior during regen, backpressure vs ash buildup, uneven EGT distribution, regen frequency creeping up, short-haul duty cycle risk.
5. **Free DPF/SCR Data Audit** — user uploads one CSV of their fleet's sensor data (or a sample), gets a one-time scored report back manually or via the trial — this doubles as a lead magnet and a trial-activation nudge.

## Rules for building these

- Pull numeric thresholds ONLY from throttleguard_engine_thresholds.py (read the file, don't approximate from memory) so the lead magnet stays internally consistent with the product.
- Every lead magnet ends with one clear CTA: start the 14-day free trial, no credit card.
- Keep tone practical/shop-floor, matching CLAUDE.md's "explainable to someone who knows trucks but not ML" standard — no jargon, no AI buzzwords.
- Lead magnets are top-of-funnel — don't oversell the product inside them; let the checklist/calculator itself be genuinely useful even to someone who never signs up.

## How to run this skill

1. Ask which lead magnet the user wants (or recommend #1 or #2 as the highest-conversion starting points if they're undecided).
2. If it needs real threshold values, read throttleguard_engine_thresholds.py first rather than guessing.
3. Draft the full asset content (not just an outline) — checklist items, calculator formula/logic, or guide copy — plus a short landing-page blurb and CTA line to pair with it.
4. Note where design/formatting work (PDF layout, calculator UI) would need to happen outside this skill, and offer to build a simple HTML/artifact version if the user wants something shareable immediately.
