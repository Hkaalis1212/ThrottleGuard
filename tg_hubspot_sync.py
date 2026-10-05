"""
tg_hubspot_sync.py — pushes trial-start and landing-page-lead events into HubSpot.

Closes the gap noted in tg_trial_followup_cron.py: that script drafts
follow-up emails off a contact's `trial_start_date` property, but nothing
was setting that property when a real trial actually started. push_trial_start()
is the missing write side — called once, at the moment start_trial()
succeeds in app.py.

push_landing_lead() serves tg_landing.py's "Request Access" CTA: the landing
page is lead-capture only (no self-serve checkout — the app is single-tenant,
so there's no automated way to provision a new customer's account yet), so a
submission there just needs to land in HubSpot as a lead a human follows up
with manually.

Optional integration, same pattern as Fleet Optimizer in CLAUDE.md: HubSpot
sync is enabled only when HUBSPOT_PRIVATE_APP_TOKEN is set. ThrottleGuard
must work fully standalone, so any HubSpot failure is logged and swallowed
here — it must never block a trial from starting or a landing-page visitor
from seeing their score.
"""

import logging
import os
from datetime import date, datetime

import requests

logger = logging.getLogger(__name__)

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")


def push_trial_start(email: str) -> None:
    """
    Upsert a HubSpot contact by email and set trial_start_date to today.
    No-ops quietly if HubSpot isn't configured or the call fails — see
    module docstring for why this must never raise into the caller.
    """
    if not HUBSPOT_TOKEN:
        return
    if not email:
        return

    try:
        resp = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/batch/upsert",
            headers={
                "Authorization": f"Bearer {HUBSPOT_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": [
                    {
                        "idProperty": "email",
                        "id": email,
                        "properties": {
                            "email": email,
                            "trial_start_date": date.today().isoformat(),
                        },
                    }
                ]
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"[TG HubSpot] Synced trial start for {email}")
    except Exception as e:
        # Trial creation must succeed regardless of HubSpot's availability.
        logger.warning(f"[TG HubSpot] push_trial_start failed for {email}: {e}")


def push_landing_lead(email: str, note_body: str) -> None:
    """
    Upsert a HubSpot contact by email as a new Lead, with note_body (fleet
    size, worst-truck score, etc. from the landing page's CSV scoring)
    attached as a Note. No-ops quietly if HubSpot isn't configured or the
    call fails — see module docstring for why this must never raise into
    the caller.
    """
    if not HUBSPOT_TOKEN:
        return
    if not email:
        return

    try:
        headers = {
            "Authorization": f"Bearer {HUBSPOT_TOKEN}",
            "Content-Type": "application/json",
        }

        upsert_resp = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/batch/upsert",
            headers=headers,
            json={
                "inputs": [
                    {
                        "idProperty": "email",
                        "id": email,
                        "properties": {
                            "email": email,
                            "lifecyclestage": "lead",
                            "hs_lead_status": "NEW",
                        },
                    }
                ]
            },
            timeout=10,
        )
        upsert_resp.raise_for_status()
        contact_id = upsert_resp.json()["results"][0]["id"]

        note_resp = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/notes",
            headers=headers,
            json={
                "properties": {
                    "hs_timestamp": str(int(datetime.utcnow().timestamp() * 1000)),
                    "hs_note_body": note_body,
                }
            },
            timeout=10,
        )
        note_resp.raise_for_status()
        note_id = note_resp.json()["id"]

        assoc_resp = requests.put(
            f"{HUBSPOT_BASE}/crm/v4/objects/notes/{note_id}/associations/default/contacts/{contact_id}",
            headers=headers,
            timeout=10,
        )
        assoc_resp.raise_for_status()
        logger.info(f"[TG HubSpot] Logged landing-page lead for {email}")
    except Exception as e:
        # The landing page must keep working regardless of HubSpot's availability.
        logger.warning(f"[TG HubSpot] push_landing_lead failed for {email}: {e}")
