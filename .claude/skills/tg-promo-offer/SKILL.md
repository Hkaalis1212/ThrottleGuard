---
name: tg-promo-offer
description: Construct or refine ThrottleGuard's sales offer — trial terms, pricing framing, bonuses, guarantees, urgency, and bundle framing with Fleet Optimizer. Use when the user wants to design a promo, a pricing page section, a launch offer, or wants to know how to frame the trial/paid transition without misrepresenting the product.
---

# ThrottleGuard Offer Construction

Build offers around the real commercial terms — never invent pricing, terms, or guarantees the business hasn't actually agreed to.

## Real terms (single source of truth)

- **Trial**: 14 days free, full access, no credit card required.
- **Paid**: $59.99/month, or $575.90/year (this is the 18% annual discount already baked in — don't re-derive or round differently).
- **Standalone**: works fully without Fleet Optimizer. The bundle is optional and gated by env var — treat it as an upsell, never a prerequisite.
- **Per-deployment subscription model**: one subscription per fleet (fleet_id = "admin" in the current architecture) — so the offer is fleet-wide, not seat-based. Frame pricing as "per fleet," not "per user" or "per truck," unless the user tells you the model has changed.

## Offer components to work with

1. **Risk reversal** — the trial already removes the biggest objection (no card, 14 days, full access). Lead with that before touching price.
2. **Anchor the price against the cost of one failure.** A DPF replacement or an EPA derate roadside call costs far more than a year of ThrottleGuard. Use this comparison, not fabricated "average fleet saves $X" claims unless the user supplies real numbers.
3. **Annual discount as the default recommended plan**, framed as "less than $50/month" rather than restating the raw $575.90 figure repeatedly.
4. **Urgency/scarcity** — only use real constraints (e.g., "founding fleet pricing locked before public launch," limited onboarding slots for white-glove setup) — never fake countdown timers or fake limited spots. If the user wants urgency and has no real constraint, say so and offer an honest alternative (e.g., calendar-based "before next price review" if that's real).
5. **Guarantee language** — do not draft a money-back or uptime guarantee unless the user confirms one exists; ask before inventing one, since it's a real commercial commitment.

## How to run this skill

1. Clarify the offer's purpose: cold launch offer, referral/affiliate offer, upsell to Fleet Optimizer bundle, win-back offer for churned trials, or a specific channel's landing page (email, LinkedIn, trade show).
2. Draft the offer stack: what's included, trial terms, price, any bonus (e.g., free onboarding call, free DPF/SCR audit of their first upload).
3. Write 2-3 headline variants that lead with the pain removed (derate risk, surprise DPF bill) rather than the product's mechanism.
4. Flag anywhere the offer implies a guarantee, discount, or scarcity that isn't confirmed — ask the user to confirm before finalizing copy that goes external.
