"""
tg_hubspot_sync.py — pushes trial-start events into HubSpot.

Closes the gap noted in tg_trial_followup_cron.py: that script drafts
follow-up emails off a contact's `trial_start_date` property, but nothing
was setting that property when a real trial actually started. This module
is the missing write side — called once, at the moment start_trial()
succeeds in app.py.

Optional integration, same pattern as Fleet Optimizer in CLAUDE.md: HubSpot
sync is enabled only when HUBSPOT_PRIVATE_APP_TOKEN is set. ThrottleGuard
must work fully standalone, so any HubSpot failure is logged and swallowed
here — it must never block a trial from starting.
"""

import logging
import os
from datetime import date

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
