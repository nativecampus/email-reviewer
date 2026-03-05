from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.email import Email
from app.models.rep import Rep
from app.services.fetcher import (
    _parse_timestamp,
    fetch_and_store,
    fetch_emails_from_hubspot,
    filter_outgoing_emails,
    upsert_emails_to_db,
)
from tests.fixtures.hubspot import (
    FORWARDED_EMAIL,
    INCOMING_EMAIL,
    INCOMING_REPLY,
    NATIVE_FM_EMAIL,
    NULL_METADATA_EMAIL,
    OUTGOING_SALES_EMAIL,
    make_hubspot_email,
    make_hubspot_response,
)

COMPANY_DOMAINS = ["nativecampusadvertising.com", "native.fm"]


class TestFilterOutgoingEmails:
    def test_keeps_email_direction(self):
        emails = [OUTGOING_SALES_EMAIL]
        result = filter_outgoing_emails(emails, COMPANY_DOMAINS)
        assert len(result) == 1
        assert result[0]["id"] == OUTGOING_SALES_EMAIL["id"]

    def test_keeps_forwarded_email_direction_from_company_domain(self):
        forwarded_from_company = make_hubspot_email(
            id="fwd-company",
            hs_email_direction="FORWARDED_EMAIL",
            hs_email_from_email="rep@nativecampusadvertising.com",
        )
        result = filter_outgoing_emails([forwarded_from_company], COMPANY_DOMAINS)
        assert len(result) == 1
        assert result[0]["id"] == "fwd-company"

    def test_drops_incoming_email_direction(self):
        result = filter_outgoing_emails([INCOMING_EMAIL], COMPANY_DOMAINS)
        assert result == []

    def test_drops_email_from_non_company_domain(self):
        external = make_hubspot_email(
            id="external",
            hs_email_direction="EMAIL",
            hs_email_from_email="someone@gmail.com",
        )
        result = filter_outgoing_emails([external], COMPANY_DOMAINS)
        assert result == []

    def test_keeps_email_from_nativecampusadvertising(self):
        result = filter_outgoing_emails([OUTGOING_SALES_EMAIL], COMPANY_DOMAINS)
        assert len(result) == 1

    def test_keeps_email_from_native_fm(self):
        result = filter_outgoing_emails([NATIVE_FM_EMAIL], COMPANY_DOMAINS)
        assert len(result) == 1

    def test_returns_empty_list_for_empty_input(self):
        result = filter_outgoing_emails([], COMPANY_DOMAINS)
        assert result == []

    def test_drops_null_from_email(self):
        result = filter_outgoing_emails([NULL_METADATA_EMAIL], COMPANY_DOMAINS)
        assert result == []

    def test_mixed_input_filters_correctly(self):
        emails = [
            OUTGOING_SALES_EMAIL,
            NATIVE_FM_EMAIL,
            INCOMING_EMAIL,
            INCOMING_REPLY,
            FORWARDED_EMAIL,
            NULL_METADATA_EMAIL,
        ]
        result = filter_outgoing_emails(emails, COMPANY_DOMAINS)
        result_ids = {e["id"] for e in result}
        assert OUTGOING_SALES_EMAIL["id"] in result_ids
        assert NATIVE_FM_EMAIL["id"] in result_ids
        assert INCOMING_EMAIL["id"] not in result_ids
        assert INCOMING_REPLY["id"] not in result_ids


class TestUpsertEmailsToDb:
    async def test_inserts_new_email(self, db):
        emails = [OUTGOING_SALES_EMAIL]
        count = await upsert_emails_to_db(db, emails)

        assert count == 1
        result = await db.execute(select(Email))
        row = result.scalar_one()
        assert row.hubspot_id == OUTGOING_SALES_EMAIL["id"]
        assert row.subject == "Engaging with Students on campus"

    async def test_updates_existing_email_on_same_hubspot_id(self, db):
        emails = [OUTGOING_SALES_EMAIL]
        await upsert_emails_to_db(db, emails)

        updated = make_hubspot_email(
            id=OUTGOING_SALES_EMAIL["id"],
            hs_email_subject="Updated Subject",
        )
        await upsert_emails_to_db(db, [updated])

        result = await db.execute(select(Email))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].subject == "Updated Subject"

    async def test_auto_creates_rep_for_new_from_email(self, db):
        emails = [OUTGOING_SALES_EMAIL]
        await upsert_emails_to_db(db, emails)

        from_email = OUTGOING_SALES_EMAIL["properties"]["hs_email_from_email"]
        result = await db.execute(select(Rep).where(Rep.email == from_email))
        rep = result.scalar_one()
        assert rep.display_name == "Kieran Berry Campbell"

    async def test_does_not_duplicate_rep_on_upsert(self, db):
        emails = [OUTGOING_SALES_EMAIL]
        await upsert_emails_to_db(db, emails)

        second = make_hubspot_email(
            id="different-id",
            hs_email_from_email=OUTGOING_SALES_EMAIL["properties"][
                "hs_email_from_email"
            ],
        )
        await upsert_emails_to_db(db, [second])

        result = await db.execute(select(Rep))
        reps = result.scalars().all()
        assert len(reps) == 1


class TestFetchEmailsFromHubspot:
    @patch("app.services.fetcher.requests.post")
    def test_paginates_correctly(self, mock_post):
        page1 = make_hubspot_response(
            [OUTGOING_SALES_EMAIL, NATIVE_FM_EMAIL],
            total=4,
            after="2",
        )
        page2 = make_hubspot_response(
            [INCOMING_EMAIL, FORWARDED_EMAIL],
            total=4,
        )
        resp1 = MagicMock(status_code=200)
        resp1.json.return_value = page1
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = page2
        mock_post.side_effect = [resp1, resp2]

        result = fetch_emails_from_hubspot("token")
        assert len(result) == 4
        assert mock_post.call_count == 2

    @patch("app.services.fetcher.requests.post")
    @patch("app.services.fetcher.time.sleep")
    def test_retries_on_429(self, mock_sleep, mock_post):
        rate_limited = MagicMock(status_code=429)
        rate_limited.headers = {"Retry-After": "1"}
        success = MagicMock(status_code=200)
        success.json.return_value = make_hubspot_response(
            [OUTGOING_SALES_EMAIL], total=1
        )
        mock_post.side_effect = [rate_limited, success]

        result = fetch_emails_from_hubspot("token")
        assert len(result) == 1
        assert mock_post.call_count == 2
        mock_sleep.assert_called()

    @patch("app.services.fetcher.requests.post")
    def test_applies_start_date_filter(self, mock_post):
        from datetime import datetime

        resp = MagicMock(status_code=200)
        resp.json.return_value = make_hubspot_response([], total=0)
        mock_post.return_value = resp

        start = datetime(2026, 2, 1)
        fetch_emails_from_hubspot("token", start_date=start)

        body = mock_post.call_args[1]["json"]
        filters = body["filterGroups"][0]["filters"]
        gte_filter = next(f for f in filters if f["operator"] == "GTE")
        assert gte_filter["propertyName"] == "hs_createdate"
        expected_ms = str(int(start.timestamp() * 1000))
        assert gte_filter["value"] == expected_ms

    @patch("app.services.fetcher.requests.post")
    def test_applies_end_date_filter(self, mock_post):
        from datetime import datetime

        resp = MagicMock(status_code=200)
        resp.json.return_value = make_hubspot_response([], total=0)
        mock_post.return_value = resp

        end = datetime(2026, 3, 1)
        fetch_emails_from_hubspot("token", end_date=end)

        body = mock_post.call_args[1]["json"]
        filters = body["filterGroups"][0]["filters"]
        lte_filter = next(f for f in filters if f["operator"] == "LTE")
        assert lte_filter["propertyName"] == "hs_createdate"
        expected_ms = str(int(end.timestamp() * 1000))
        assert lte_filter["value"] == expected_ms

    @patch("app.services.fetcher.requests.post")
    def test_returns_empty_list_when_no_results(self, mock_post):
        resp = MagicMock(status_code=200)
        resp.json.return_value = make_hubspot_response([], total=0)
        mock_post.return_value = resp

        result = fetch_emails_from_hubspot("token")
        assert result == []

    @patch("app.services.fetcher.requests.post")
    @patch("app.services.fetcher.time.sleep")
    def test_raises_on_retry_exhaustion(self, mock_sleep, mock_post):
        resp = MagicMock(status_code=401)
        resp.text = "Unauthorized"
        mock_post.return_value = resp

        with pytest.raises(RuntimeError, match="failed after 5 retries"):
            fetch_emails_from_hubspot("bad-token")

    @patch("app.services.fetcher.requests.post")
    def test_handles_malformed_response(self, mock_post):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"unexpected": "shape"}
        mock_post.return_value = resp

        result = fetch_emails_from_hubspot("token")
        assert result == []


class TestParseTimestamp:
    def test_parses_iso_timestamp_with_z_suffix(self):
        from datetime import datetime

        result = _parse_timestamp("2026-02-02T08:18:00.440Z")
        assert result == datetime(2026, 2, 2, 8, 18, 0, 440000)

    def test_parses_iso_timestamp_without_fractional_seconds(self):
        from datetime import datetime

        result = _parse_timestamp("2026-02-01T13:25:22Z")
        assert result == datetime(2026, 2, 1, 13, 25, 22)

    def test_returns_none_for_empty_string(self):
        assert _parse_timestamp("") is None

    def test_returns_none_for_none(self):
        assert _parse_timestamp(None) is None

    def test_returns_none_for_invalid_string(self):
        assert _parse_timestamp("not-a-date") is None


class TestUpsertTimestamp:
    async def test_stores_parsed_timestamp(self, db):
        count = await upsert_emails_to_db(db, [OUTGOING_SALES_EMAIL])
        assert count == 1

        result = await db.execute(select(Email))
        row = result.scalar_one()
        assert row.timestamp is not None
        assert row.timestamp.year == 2026
        assert row.timestamp.month == 2
        assert row.timestamp.day == 2

    async def test_updates_timestamp_on_upsert(self, db):
        await upsert_emails_to_db(db, [OUTGOING_SALES_EMAIL])

        updated = make_hubspot_email(
            id=OUTGOING_SALES_EMAIL["id"],
            hs_timestamp="2026-03-15T10:00:00Z",
        )
        await upsert_emails_to_db(db, [updated])

        result = await db.execute(select(Email))
        row = result.scalar_one()
        assert row.timestamp.month == 3
        assert row.timestamp.day == 15


class TestFetchAndStoreMaxCount:
    @patch("app.services.fetcher.requests.post")
    async def test_max_count_limits_filtered_output(self, mock_post, db):
        """max_count limits the number of filtered outgoing emails stored,
        not the number of raw results fetched from HubSpot."""
        # Return 4 outgoing + 2 incoming emails in one page
        all_emails = [
            make_hubspot_email(id="out-1", hs_email_direction="EMAIL",
                               hs_email_from_email="rep1@nativecampusadvertising.com"),
            make_hubspot_email(id="out-2", hs_email_direction="EMAIL",
                               hs_email_from_email="rep2@nativecampusadvertising.com"),
            make_hubspot_email(id="in-1", hs_email_direction="INCOMING_EMAIL",
                               hs_email_from_email="external@gmail.com"),
            make_hubspot_email(id="out-3", hs_email_direction="EMAIL",
                               hs_email_from_email="rep3@nativecampusadvertising.com"),
            make_hubspot_email(id="in-2", hs_email_direction="INCOMING_EMAIL",
                               hs_email_from_email="other@yahoo.com"),
            make_hubspot_email(id="out-4", hs_email_direction="EMAIL",
                               hs_email_from_email="rep4@nativecampusadvertising.com"),
        ]
        resp = MagicMock(status_code=200)
        resp.json.return_value = make_hubspot_response(all_emails, total=6)
        mock_post.return_value = resp

        stored = await fetch_and_store(
            db,
            access_token="token",
            company_domains=["nativecampusadvertising.com"],
            max_count=2,
        )
        assert stored == 2

        result = await db.execute(select(Email))
        rows = result.scalars().all()
        assert len(rows) == 2
