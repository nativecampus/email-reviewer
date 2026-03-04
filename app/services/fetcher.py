"""Fetch outgoing emails from HubSpot and upsert into the database."""

import time
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email import Email
from app.models.rep import Rep

BASE_URL = "https://api.hubapi.com"
REQUEST_DELAY = 0.15
MAX_RETRIES = 5
PAGE_SIZE = 100

PROPERTIES = [
    "hs_timestamp",
    "hs_email_subject",
    "hs_email_text",
    "hs_email_html",
    "hs_email_from_email",
    "hs_email_from_firstname",
    "hs_email_from_lastname",
    "hs_email_to_email",
    "hs_email_to_firstname",
    "hs_email_to_lastname",
    "hs_email_cc_email",
    "hs_email_bcc_email",
    "hs_email_direction",
    "hs_email_status",
    "hs_email_tracker_key",
    "hubspot_owner_id",
    "hs_createdate",
]


def filter_outgoing_emails(
    emails: list[dict], company_domains: list[str]
) -> list[dict]:
    """Keep only outgoing emails sent from a company domain.

    Filters on two criteria:
    1. Direction must be EMAIL or FORWARDED_EMAIL (drops INCOMING_EMAIL).
    2. The from_email domain must be in the company_domains list.
    """
    allowed_directions = {"EMAIL", "FORWARDED_EMAIL"}
    result = []
    for email in emails:
        props = email.get("properties", {})
        direction = props.get("hs_email_direction", "")
        if direction not in allowed_directions:
            continue
        from_email = props.get("hs_email_from_email") or ""
        if "@" not in from_email:
            continue
        domain = from_email.rsplit("@", 1)[1].lower()
        if domain not in [d.lower() for d in company_domains]:
            continue
        result.append(email)
    return result


def _build_search_body(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    after: Optional[str] = None,
) -> dict:
    """Build the HubSpot CRM v3 search request body."""
    body: dict = {
        "limit": PAGE_SIZE,
        "properties": PROPERTIES,
        "sorts": [
            {"propertyName": "hs_createdate", "direction": "ASCENDING"}
        ],
    }

    filters = []
    if start_date:
        filters.append({
            "propertyName": "hs_createdate",
            "operator": "GTE",
            "value": str(int(start_date.timestamp() * 1000)),
        })
    if end_date:
        filters.append({
            "propertyName": "hs_createdate",
            "operator": "LTE",
            "value": str(int(end_date.timestamp() * 1000)),
        })
    if filters:
        body["filterGroups"] = [{"filters": filters}]

    if after:
        body["after"] = after

    return body


def _parse_email(result: dict) -> dict:
    """Extract a flat email dict from a HubSpot search result object."""
    props = result.get("properties", {})
    first = props.get("hs_email_from_firstname") or ""
    last = props.get("hs_email_from_lastname") or ""
    to_first = props.get("hs_email_to_firstname") or ""
    to_last = props.get("hs_email_to_lastname") or ""
    return {
        "id": result["id"],
        "timestamp": props.get("hs_timestamp", ""),
        "subject": props.get("hs_email_subject", ""),
        "from_email": props.get("hs_email_from_email", ""),
        "from_name": f"{first} {last}".strip(),
        "to_email": props.get("hs_email_to_email", ""),
        "to_name": f"{to_first} {to_last}".strip(),
        "direction": props.get("hs_email_direction", ""),
        "body_text": props.get("hs_email_text", ""),
    }


def fetch_emails_from_hubspot(
    access_token: str,
    max_count: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[dict]:
    """Fetch emails from HubSpot CRM v3 search API with pagination and retry."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    all_emails: list[dict] = []
    after: Optional[str] = None

    while True:
        if max_count and len(all_emails) >= max_count:
            break

        body = _build_search_body(
            start_date=start_date, end_date=end_date, after=after
        )
        retries = 0

        while retries < MAX_RETRIES:
            resp = requests.post(
                f"{BASE_URL}/crm/v3/objects/emails/search",
                headers=headers,
                json=body,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                time.sleep(retry_after)
                retries += 1
                continue
            elif resp.status_code != 200:
                retries += 1
                time.sleep(2**retries)
                continue

            break
        else:
            break

        data = resp.json()

        for result in data.get("results", []):
            all_emails.append(result)
            if max_count and len(all_emails) >= max_count:
                break

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")

        if not after:
            break

        time.sleep(REQUEST_DELAY)

    return all_emails


async def upsert_emails_to_db(
    session: AsyncSession, emails: list[dict]
) -> int:
    """Upsert HubSpot email records and auto-create rep records.

    Returns the number of emails upserted.
    """
    count = 0
    for raw in emails:
        parsed = _parse_email(raw)
        hubspot_id = parsed["id"]

        # Upsert email
        result = await session.execute(
            select(Email).where(Email.hubspot_id == hubspot_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.subject = parsed["subject"]
            existing.from_email = parsed["from_email"]
            existing.from_name = parsed["from_name"]
            existing.to_email = parsed["to_email"]
            existing.to_name = parsed["to_name"]
            existing.direction = parsed["direction"]
            existing.body_text = parsed["body_text"]
        else:
            email = Email(
                hubspot_id=hubspot_id,
                subject=parsed["subject"],
                from_email=parsed["from_email"],
                from_name=parsed["from_name"],
                to_email=parsed["to_email"],
                to_name=parsed["to_name"],
                direction=parsed["direction"],
                body_text=parsed["body_text"],
                fetched_at=datetime.utcnow(),
            )
            session.add(email)

        # Auto-create rep if from_email is present
        from_email = parsed["from_email"]
        if from_email:
            rep_result = await session.execute(
                select(Rep).where(Rep.email == from_email)
            )
            if not rep_result.scalar_one_or_none():
                rep = Rep(
                    email=from_email,
                    display_name=parsed["from_name"] or from_email,
                )
                session.add(rep)

        count += 1

    await session.flush()
    return count


async def fetch_and_store(
    session: AsyncSession,
    access_token: str,
    company_domains: list[str],
    max_count: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> int:
    """Fetch emails from HubSpot, filter outgoing, and upsert to DB.

    Returns the number of emails stored.
    """
    raw_emails = fetch_emails_from_hubspot(
        access_token,
        max_count=max_count,
        start_date=start_date,
        end_date=end_date,
    )
    outgoing = filter_outgoing_emails(raw_emails, company_domains)
    return await upsert_emails_to_db(session, outgoing)
