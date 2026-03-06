"""Fetch emails from HubSpot and upsert into the database."""

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
MAX_SEARCH_RESULTS = 10000
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
    "hs_email_open_count",
    "hs_email_click_count",
    "hs_email_reply_count",
    "hs_email_headers_message_id",
    "hs_email_headers_in_reply_to",
    "hs_email_thread_id",
]


def filter_relevant_emails(
    emails: list[dict], company_domains: list[str]
) -> list[dict]:
    """Keep outgoing emails from a company domain and incoming emails to a company domain.

    - EMAIL: kept when from_email domain is in company_domains (outgoing from our rep).
    - INCOMING_EMAIL: kept when to_email domain is in company_domains (reply to our rep).
    - FORWARDED_EMAIL and anything else: dropped. FORWARDED_EMAIL means an email
      was forwarded to the CRM for logging, not a sales interaction.
    """
    lower_domains = [d.lower() for d in company_domains]
    result = []
    for email in emails:
        props = email.get("properties", {})
        direction = props.get("hs_email_direction", "")

        if direction == "EMAIL":
            from_email = props.get("hs_email_from_email") or ""
            if "@" not in from_email:
                continue
            domain = from_email.rsplit("@", 1)[1].lower()
            if domain not in lower_domains:
                continue
            result.append(email)

        elif direction == "INCOMING_EMAIL":
            to_email = props.get("hs_email_to_email") or ""
            if "@" not in to_email:
                continue
            domain = to_email.rsplit("@", 1)[1].lower()
            if domain not in lower_domains:
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


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse a HubSpot timestamp string (ISO 8601) into a datetime."""
    if not value:
        return None
    try:
        # HubSpot returns ISO 8601 timestamps like "2026-02-02T08:18:00.440Z"
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _coerce_int(value: str | None) -> int | None:
    """Coerce a string to int, returning None for missing or non-numeric values."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_email(result: dict) -> dict:
    """Extract a flat email dict from a HubSpot search result object."""
    props = result.get("properties", {})
    first = props.get("hs_email_from_firstname") or ""
    last = props.get("hs_email_from_lastname") or ""
    to_first = props.get("hs_email_to_firstname") or ""
    to_last = props.get("hs_email_to_lastname") or ""
    return {
        "id": result["id"],
        "timestamp": _parse_timestamp(props.get("hs_timestamp")),
        "subject": props.get("hs_email_subject", ""),
        "from_email": props.get("hs_email_from_email", ""),
        "from_name": f"{first} {last}".strip(),
        "to_email": props.get("hs_email_to_email", ""),
        "to_name": f"{to_first} {to_last}".strip(),
        "direction": props.get("hs_email_direction", ""),
        "body_text": props.get("hs_email_text", ""),
        "open_count": _coerce_int(props.get("hs_email_open_count")),
        "click_count": _coerce_int(props.get("hs_email_click_count")),
        "reply_count": _coerce_int(props.get("hs_email_reply_count")),
        "message_id": props.get("hs_email_headers_message_id"),
        "in_reply_to": props.get("hs_email_headers_in_reply_to"),
        "thread_id": props.get("hs_email_thread_id"),
    }


def _fetch_single_page(headers: dict, body: dict) -> dict:
    """Make a single HubSpot search request with retry logic. Returns parsed JSON."""
    retries = 0
    resp = None

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
        elif resp.status_code >= 500:
            retries += 1
            time.sleep(2**retries)
            continue
        elif resp.status_code != 200:
            # 4xx client errors (except 429) are permanent — fail immediately
            import json as _json

            raise RuntimeError(
                f"HubSpot API request failed with HTTP {resp.status_code}\n"
                f"Response: {resp.text[:500]}\n"
                f"Request body: {_json.dumps(body)}"
            )

        break
    else:
        import json as _json

        raise RuntimeError(
            f"HubSpot API request failed after {MAX_RETRIES} retries "
            f"(HTTP {resp.status_code})\n"
            f"Response: {resp.text[:500]}\n"
            f"Request body: {_json.dumps(body)}"
        )

    return resp.json()


def _fetch_range(
    headers: dict,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_results: Optional[int] = None,
) -> list[dict]:
    """Fetch emails in a date range, paginating up to max_results or the 10K limit.

    When pagination hits the 10,000 ceiling, subdivides the time range into halves
    and fetches each recursively. Requires both start_date and end_date for subdivision.
    """
    all_emails: list[dict] = []
    after: Optional[str] = None

    while True:
        body = _build_search_body(
            start_date=start_date, end_date=end_date, after=after
        )
        data = _fetch_single_page(headers, body)

        for result in data.get("results", []):
            all_emails.append(result)

        if max_results and len(all_emails) >= max_results:
            return all_emails[:max_results]

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")

        if not after:
            return all_emails

        if int(after) >= MAX_SEARCH_RESULTS:
            break

        time.sleep(REQUEST_DELAY)

    # Hit 10K limit — subdivide the time range and fetch each half
    if not start_date or not end_date:
        return all_emails

    midpoint = start_date + (end_date - start_date) / 2
    if midpoint <= start_date or midpoint >= end_date:
        return all_emails

    remaining = max_results - len(all_emails) if max_results else None
    first_half = _fetch_range(
        headers, start_date=start_date, end_date=midpoint, max_results=remaining
    )

    remaining = max_results - len(all_emails) - len(first_half) if max_results else None
    if max_results and remaining is not None and remaining <= 0:
        return (all_emails + first_half)[:max_results]

    second_half = _fetch_range(
        headers, start_date=midpoint, end_date=end_date, max_results=remaining
    )

    # Deduplicate by HubSpot ID since the midpoint boundary may overlap
    seen: set[str] = set()
    combined: list[dict] = []
    for email in all_emails + first_half + second_half:
        eid = email.get("id")
        if eid not in seen:
            seen.add(eid)
            combined.append(email)

    if max_results:
        return combined[:max_results]
    return combined


def fetch_emails_from_hubspot(
    access_token: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    max_results: Optional[int] = None,
) -> list[dict]:
    """Fetch emails from HubSpot CRM v3 search API with pagination and retry.

    When a date range contains more than 10,000 results (HubSpot's paging limit),
    the range is automatically subdivided into smaller windows.

    max_results stops pagination early once enough raw results are collected.
    This is applied to raw HubSpot results before any outgoing/domain filtering.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    return _fetch_range(
        headers, start_date=start_date, end_date=end_date, max_results=max_results
    )


async def upsert_emails_to_db(
    session: AsyncSession, emails: list[dict]
) -> int:
    """Upsert HubSpot email records and auto-create rep records.

    Rep records are only created for outgoing emails (direction=EMAIL),
    since the from_email on those is a company rep.

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

        field_values = {
            "timestamp": parsed["timestamp"],
            "subject": parsed["subject"],
            "from_email": parsed["from_email"],
            "from_name": parsed["from_name"],
            "to_email": parsed["to_email"],
            "to_name": parsed["to_name"],
            "direction": parsed["direction"],
            "body_text": parsed["body_text"],
            "open_count": parsed["open_count"],
            "click_count": parsed["click_count"],
            "reply_count": parsed["reply_count"],
            "message_id": parsed["message_id"],
            "in_reply_to": parsed["in_reply_to"],
            "thread_id": parsed["thread_id"],
        }

        if existing:
            for key, value in field_values.items():
                setattr(existing, key, value)
        else:
            email = Email(
                hubspot_id=hubspot_id,
                fetched_at=datetime.utcnow(),
                **field_values,
            )
            session.add(email)

        # Auto-create rep only for outgoing emails
        if parsed["direction"] == "EMAIL":
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
    """Fetch emails from HubSpot, filter relevant, and upsert to DB.

    max_count limits the number of filtered emails stored, not the
    number of raw results fetched from HubSpot. Returns the number of emails
    stored.
    """
    # Fetch 1.5x max_count to account for irrelevant emails being filtered out
    raw_limit = int(max_count * 1.5) if max_count is not None else None
    raw_emails = fetch_emails_from_hubspot(
        access_token,
        start_date=start_date,
        end_date=end_date,
        max_results=raw_limit,
    )
    relevant = filter_relevant_emails(raw_emails, company_domains)
    if max_count is not None:
        relevant = relevant[:max_count]
    return await upsert_emails_to_db(session, relevant)
