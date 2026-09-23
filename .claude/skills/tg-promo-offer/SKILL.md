---
name: tg-promo-offer
description: Construct or refine ThrottleGuard's sales offer — trial terms, pricing framing, bonuses, guarantees, urgency, and bundle framing with Fleet Optimizer. Use when the user wants to design a promo, a pricing page section, a launch offer, or wants to know how to frame the trial/paid transition without misrepresenting the product.
---

# ThrottleGuard Offer Construction

Build offers around the real commercial terms — never invent pricing, terms, or guarantees the business hasn't actually agreed to.

## Real terms (single source of truth)

- **Trial**: 14 days free, full access, no credit card required.
- **Paid**: per-truck tiered pricing (from tg_subscription.py / PRICING_TIERS, the actual billing logic — this supersedes any flat monthly/yearly figure written elsewhere, including older CLAUDE.md drafts): **Starter** $39/truck/mo (1-10 trucks), **Growth** $29/truck/mo (11-50 trucks), **Fleet** $19/truck/mo (51-250 trucks), **Enterprise** 250+ trucks = custom quote, no automated checkout. There is currently no annual/prepay discount plan in the code — don't invent one.
- **Standalone**: works fully without Fleet Optimizer. The bundle is optional and gated by env var — treat it as an upsell, never a prerequisite.
- **Per-deployment subscription model**: one subscription per fleet (fleet_id = "admin" in the current architecture) — so the offer is fleet-wide, not seat-based, but the *price* itself scales with truck count per the tiers above.
- Before drafting anything with a specific dollar figure, quickly check `tg_subscription.py`'s `PRICING_TIERS` / `monthly_price()` again if it's been a while — pricing is the one fact most likely to drift out from under this skill file.

## Offer components to work with

1. **Risk reversal** — the trial already removes the biggest objection (no card, 14 days, full access). Lead with that before touching price.
2. **Anchor the price against the cost of one failure.** A DPF replacement or an EPA derate roadside call costs far more than a year of ThrottleGuard. Use this comparison, not fabricated "average fleet saves $X" claims unless the user supplies real numbers.
3. **Lead with the per-truck rate scaling down as fleets grow** ($39 → $29 → $19/truck/mo) — it's a real, favorable dynamic for larger fleets and worth calling out explicitly rather than just stating the tier they land in.
4. **Urgency/scarcity** — only use real constraints (e.g., "founding fleet pricing locked before public launch," limited onboarding slots for white-glove setup) — never fake countdown timers or fake limited spots. If the user wants urgency and has no real constraint, say so and offer an honest alternative (e.g., calendar-based "before next price review" if that's real).
5. **Guarantee language** — do not draft a money-back or uptime guarantee unless the user confirms one exists; ask before inventing one, since it's a real commercial commitment.

## How to run this skill

1. Clarify the offer's purpose: cold launch offer, referral/affiliate offer, upsell to Fleet Optimizer bundle, win-back offer for churned trials, or a specific channel's landing page (email, LinkedIn, trade show).
2. Draft the offer stack: what's included, trial terms, price, any bonus (e.g., free onboarding call, free DPF/SCR audit of their first upload).
3. Write 2-3 headline variants that lead with the pain removed (derate risk, surprise DPF bill) rather than the product's mechanism.
4. Flag anywhere the offer implies a guarantee, discount, or scarcity that isn't confirmed — ask the user to confirm before finalizing copy that goes external.
