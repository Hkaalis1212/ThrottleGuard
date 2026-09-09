---
name: tg-promo-prospect-finder
description: Define ThrottleGuard's ideal customer profile (ICP) and build a research/qualification framework for finding real prospects — where to look, what to filter for, and how to prioritize outreach. Use when the user wants to identify target fleets, build a prospect list methodology, or figure out where their buyers hang out.
---

# ThrottleGuard Prospect Finder

This skill produces a *research framework and qualification criteria*, not scraped data — always work from public, legitimate sources and respect each platform's terms of use. Never suggest scraping in violation of a site's ToS or automated mass-contact tooling.

## ICP definition (start here every time)

- **Engine mix**: fleets running Detroit, Volvo/Mack, or Cummins/PACCAR engines (the three supported families). Ask the user if they're targeting all three or a specific one first — some regions/segments skew toward one OEM.
- **Fleet size sweet spot**: small-to-midsize commercial fleets are the likely early-adopter zone — big enough to feel DPF/SCR failure costs repeatedly, small enough that they don't already have an enterprise fleet-management contract locking them out. Ask the user to confirm their current sweet spot if they've learned it from actual sales conversations — don't assume.
- **Pain signals to filter for**: fleets that have posted about DPF regen issues, derates, or aftertreatment costs; fleets running older engines (more DPF/SCR wear); short-haul/local delivery/drayage operations (duty cycle most prone to clogging per CLAUDE.md's domain rules).
- **Buyer roles**: fleet maintenance manager/director, shop owner, owner-operator (self-buyer), safety/compliance manager (cares about EPA derate risk specifically).

## Legitimate sources to research

1. **Public regulatory data** — FMCSA SAFER (safer.fmcsa.dot.gov) lets you look up carrier/DOT records (fleet size, power units, operating authority) for a specific company you're already evaluating — use it to qualify a lead, not to mass-harvest contact info.
2. **Trucking associations** — OOIDA (owner-operators), ATA and state trucking associations (fleet-level), TMC (Technology & Maintenance Council) — membership directories and event attendee lists are a warm, opted-in audience.
3. **Trade shows / events** — MATS (Mid-America Trucking Show), TMC Annual Meeting — exhibitor/attendee lists and in-person conversations are high-intent.
4. **LinkedIn** — search strings like `"fleet maintenance manager" diesel`, `"director of maintenance" trucking`, filtered by company size — use LinkedIn's own search/Sales Navigator, not scraping.
5. **Community forums / groups** — TruckersReport, TheTruckersReport DPF/regen threads, relevant Facebook trucking groups — good for organic engagement and content distribution (pairs with tg-promo-content-angles), not cold-contact harvesting.
6. **Existing telematics ecosystem** — Motive/Samsara partner or marketplace listings, since ThrottleGuard already has a Motive ingestion adapter — fleets already on Motive are a lower-friction integration story.

## Qualification scoring (adapt, don't invent fake precision)

Score each prospect on: engine family match (in/out), fleet size fit, visible pain signal (yes/no/unknown), buyer role reachable (yes/no). Prioritize prospects with 3-4 positive signals; treat 1-2 as nurture-list, not immediate outreach.

## How to run this skill

1. Confirm or refine the ICP with the user first — don't assume fleet size or region without asking if it hasn't been established.
2. Pick 2-3 sources above that fit the user's current reach (e.g., if they're pre-launch with no association memberships, start with LinkedIn + forums, not trade shows).
3. Produce a concrete research checklist or search-string list the user can run themselves, plus the qualification criteria to score what they find.
4. Hand off qualified prospects to tg-promo-cold-outreach for first-touch messaging, or tg-promo-followup once they've responded.
