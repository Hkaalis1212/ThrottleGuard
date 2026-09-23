"""
Daily trial follow-up automation for ThrottleGuard sales.

Runs headless (no Claude session, no LLM call) via the GitHub Actions workflow
at .github/workflows/tg-trial-followup.yml. It never sends anything itself —
it creates a HubSpot Task on the contact with the drafted email ready to
copy/paste, so a human reviews and sends every message. This matches the
"draft only, review before sending" cadence defined in
.claude/skills/tg-promo-followup/SKILL.md — keep the two in sync if the
cadence copy changes there.

Setup (one-time, in HubSpot):
  1. Contacts -> a custom property `trial_start_date` (type: Date picker).
     Set this on a contact the day their ThrottleGuard trial starts.
  2. Contacts -> a custom property `tg_followup_stage` (type: Single-line
     text). Leave it blank; this script manages it to avoid re-drafting the
     same cadence step twice. Don't edit it by hand.
  3. Settings -> Integrations -> Private Apps -> create one with scopes:
     crm.objects.contacts.read, crm.objects.contacts.write,
     crm.objects.tasks.write. Copy the token into the GitHub repo secret
     HUBSPOT_PRIVATE_APP_TOKEN.

Known gap: nothing in app.py/tg_subscription.py pushes a new trial signup
into HubSpot yet, so `trial_start_date` has to be set manually per contact
for now. Wiring that up is a separate task.
"""

import os
import sys
from datetime import date, datetime

import requests

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_TOKEN = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")

# Day-offsets from trial_start_date, mirroring the 14-day trial nurture
# cadence in .claude/skills/tg-promo-followup/SKILL.md. `key` is what gets
# written to tg_followup_stage so a contact is never drafted twice for the
# same step, even if the workflow runs more than once on the same day.
CADENCE = [
    {
        "day": 0,
        "key": "day0_welcome",
        "subject": "Welcome to ThrottleGuard — let's get your first scores",
        "body": (
            "Hey {firstname},\n\n"
            "You're in — 14 days, full access, no card needed. The fastest way to "
            "see value is to get real data in today: upload a CSV of your fleet's "
            "DPF/SCR sensor readings and you'll have scores in minutes.\n\n"
            "If you don't have an export handy yet, I can walk you through the demo "
            "fleet first so you know what you're looking at.\n\n"
            "Want me to jump on a quick call to get your data loaded?"
        ),
    },
    {
        "day": 2,
        "key": "day2_checkin",
        "subject": "Quick check-in — got your fleet data in yet?",
        "body": (
            "Hey {firstname},\n\n"
            "Haven't seen your fleet's data come through yet — totally fine if you've "
            "been slammed. If getting a CSV export together is the holdup, I'm happy "
            "to hop on a 10-minute call and do it with you, or start you on the demo "
            "fleet so you can see what a CRITICAL vs. LOW score actually looks like "
            "before committing your own data."
        ),
    },
    {
        "day": 7,
        "key": "day7_midpoint",
        "subject": "Here's what a CRITICAL score actually looks like",
        "body": (
            "Hey {firstname},\n\n"
            "You're at the halfway point of your trial. Worth a quick look at one "
            "specific thing: when a truck flags CRITICAL, you see the exact rule "
            "that fired and the plain-English action — not a black-box risk score. "
            "That's the part techs usually trust fastest once they see it.\n\n"
            "Anything holding you back from digging into your own fleet's scores "
            "this week?"
        ),
    },
    {
        "day": 11,
        "key": "day11_preexpiry",
        "subject": "Your trial wraps up in 3 days",
        "body": (
            "Hey {firstname},\n\n"
            "Your 14-day trial ends in 3 days. Nothing changes automatically — your "
            "data stays put either way. Pricing's per truck: $39/truck/mo for 1-10 "
            "trucks, $29/truck/mo for 11-50, $19/truck/mo for 51-250 — so it scales "
            "down as your fleet grows. If you want another set of eyes on your "
            "fleet's scores before deciding, I'm glad to jump on a call this week."
        ),
    },
    {
        "day": 14,
        "key": "day14_expiry",
        "subject": "Your ThrottleGuard trial has ended",
        "body": (
            "Hey {firstname},\n\n"
            "Your trial's wrapped up — your data and scores are still there, nothing "
            "was lost. Ready to go to paid whenever you are, priced per truck so it "
            "scales with your fleet size. If something didn't click during the "
            "trial, tell me what and I'll see if it's fixable before you decide."
        ),
    },
    {
        "day": 19,
        "key": "day19_winback",
        "subject": "No pressure — what would've made ThrottleGuard a yes?",
        "body": (
            "Hey {firstname},\n\n"
            "You haven't come back since your trial ended, so I'll keep this short: "
            "what held you back? Price, timing, a feature gap — genuinely want to "
            "know, and happy to stop emailing if now's just not the time."
        ),
    },
]


def hubspot_headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json",
    }


def fetch_trial_contacts():
    """Contacts with a trial_start_date set — candidates for the cadence."""
    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
        headers=hubspot_headers(),
        json={
            "filterGroups": [
                {"filters": [{"propertyName": "trial_start_date", "operator": "HAS_PROPERTY"}]}
            ],
            "properties": ["firstname", "lastname", "email", "trial_start_date", "tg_followup_stage"],
            "limit": 100,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def create_followup_task(contact_id: int, subject: str, body: str):
    """Draft-only: creates a HubSpot Task for a human to review and send, never sends anything itself."""
    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/tasks",
        headers=hubspot_headers(),
        json={
            "properties": {
                "hs_task_subject": f"[ThrottleGuard follow-up] {subject}",
                "hs_task_body": body,
                "hs_task_status": "NOT_STARTED",
                "hs_task_type": "EMAIL",
                "hs_timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]

    assoc = requests.put(
        f"{HUBSPOT_BASE}/crm/v4/objects/tasks/{task_id}/associations/default/contacts/{contact_id}",
        headers=hubspot_headers(),
        timeout=30,
    )
    assoc.raise_for_status()


def mark_stage_sent(contact_id: int, stage_key: str):
    resp = requests.patch(
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
        headers=hubspot_headers(),
        json={"properties": {"tg_followup_stage": stage_key}},
        timeout=30,
    )
    resp.raise_for_status()


def main():
    if not HUBSPOT_TOKEN:
        print("HUBSPOT_PRIVATE_APP_TOKEN is not set — aborting.", file=sys.stderr)
        sys.exit(1)

    today = date.today()
    contacts = fetch_trial_contacts()
    print(f"Checked {len(contacts)} trial contact(s) for {today.isoformat()}.")

    drafted = 0
    for contact in contacts:
        props = contact["properties"]
        trial_start_raw = props.get("trial_start_date")
        if not trial_start_raw:
            continue

        trial_start = datetime.fromisoformat(trial_start_raw.replace("Z", "+00:00")).date()
        days_elapsed = (today - trial_start).days
        already_sent = props.get("tg_followup_stage") or ""

        for stage in CADENCE:
            if days_elapsed != stage["day"]:
                continue
            if stage["key"] == already_sent:
                continue  # already drafted this exact cadence step for this contact

            firstname = props.get("firstname") or "there"
            body = stage["body"].format(firstname=firstname)

            create_followup_task(int(contact["id"]), stage["subject"], body)
            mark_stage_sent(int(contact["id"]), stage["key"])
            drafted += 1
            print(f"  drafted '{stage['key']}' for contact {contact['id']} ({props.get('email')})")

    print(f"Done. Drafted {drafted} follow-up task(s).")


if __name__ == "__main__":
    main()
