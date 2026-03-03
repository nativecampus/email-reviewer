"""HubSpot CRM v3 email search API response fixtures.

Derived from real data in feb_emails.json. Each fixture mirrors the structure
returned by POST /crm/v3/objects/emails/search with the properties requested
in fetch_emails.py.
"""


def make_hubspot_email(
    *,
    id="440807712958",
    hs_createdate="2026-02-02T08:18:06.692Z",
    hs_timestamp="2026-02-02T08:18:00.440Z",
    hs_email_subject="Engaging with Students on campus",
    hs_email_from_email="kieranberrycampbell@nativecampusadvertising.com",
    hs_email_from_firstname="Kieran Berry",
    hs_email_from_lastname="Campbell",
    hs_email_to_email="bookings@destination1.co.uk",
    hs_email_to_firstname="Acomb Travel",
    hs_email_to_lastname=None,
    hs_email_cc_email=None,
    hs_email_bcc_email=None,
    hs_email_direction="EMAIL",
    hs_email_status="SENT",
    hs_email_tracker_key=None,
    hubspot_owner_id="30387470",
    hs_email_text=(
        "Hi there, \n\nJust checking back in as we continue to confirm "
        "spaces for the upcoming student fair."
    ),
    hs_email_html=None,
):
    """Build a single HubSpot email result object.

    Defaults represent a typical outgoing sales email from a Native Campus rep.
    Override any field via keyword arguments.
    """
    return {
        "id": id,
        "properties": {
            "hs_createdate": hs_createdate,
            "hs_timestamp": hs_timestamp,
            "hs_email_subject": hs_email_subject,
            "hs_email_from_email": hs_email_from_email,
            "hs_email_from_firstname": hs_email_from_firstname,
            "hs_email_from_lastname": hs_email_from_lastname,
            "hs_email_to_email": hs_email_to_email,
            "hs_email_to_firstname": hs_email_to_firstname,
            "hs_email_to_lastname": hs_email_to_lastname,
            "hs_email_cc_email": hs_email_cc_email,
            "hs_email_bcc_email": hs_email_bcc_email,
            "hs_email_direction": hs_email_direction,
            "hs_email_status": hs_email_status,
            "hs_email_tracker_key": hs_email_tracker_key,
            "hubspot_owner_id": hubspot_owner_id,
            "hs_email_text": hs_email_text,
            "hs_email_html": hs_email_html,
        },
        "createdAt": hs_createdate,
        "updatedAt": hs_createdate,
        "archived": False,
    }


def make_hubspot_response(results, *, total=None, after=None):
    """Wrap email results in the HubSpot search API response envelope.

    Set ``after`` to a cursor string to simulate a paginated response with
    more pages available.
    """
    body = {
        "total": total if total is not None else len(results),
        "results": results,
    }
    if after:
        body["paging"] = {
            "next": {
                "after": after,
                "link": (
                    "https://api.hubapi.com/crm/v3/objects/emails/search"
                    f"?after={after}"
                ),
            }
        }
    return body


# ---------------------------------------------------------------------------
# Pre-built email fixtures based on feb_emails.json
# ---------------------------------------------------------------------------

# Outgoing sales email from nativecampusadvertising.com - the primary case.
OUTGOING_SALES_EMAIL = make_hubspot_email()

# Outgoing email from the native.fm domain - alternate rep domain.
NATIVE_FM_EMAIL = make_hubspot_email(
    id="440815170777",
    hs_createdate="2026-02-02T09:18:33.459Z",
    hs_timestamp="2026-02-02T09:18:30.516Z",
    hs_email_subject="Re: Native x The Finest Fudge Co",
    hs_email_from_email="sheraazahmed@native.fm",
    hs_email_from_firstname="Sheraaz",
    hs_email_from_lastname="Ahmed",
    hs_email_to_email="info@thefinestfudgeco.co.uk",
    hs_email_to_firstname="Mariah-Louise & Thomas",
    hs_email_to_lastname=None,
    hs_email_direction="EMAIL",
    hs_email_status="SENT",
    hubspot_owner_id="2115057758",
    hs_email_text=(
        "Hi Mariah-Louise and Thomas,\r\n\r\nHope you had a great weekend."
        "\r\n\r\nJust following up on my previous email to see if you had any"
        "\r\navailability this week for an online meeting?"
        "\r\n\r\nPlease let me know and I can send over an invite."
        "\r\n\r\nKind Regards"
    ),
)

# Forwarded email - direction metadata says FORWARDED_EMAIL but it is
# addressed TO a native rep, not FROM one. Should be kept by direction
# filter but excluded by the domain filter.
FORWARDED_EMAIL = make_hubspot_email(
    id="440841059529",
    hs_createdate="2026-02-02T09:10:55.783Z",
    hs_timestamp="2026-02-02T09:10:52.823Z",
    hs_email_subject="Campus Fairs (February to June) - LJMU & Hope",
    hs_email_from_email="info@voxkaraokebar.co.uk",
    hs_email_from_firstname=None,
    hs_email_from_lastname=None,
    hs_email_to_email="Inderpalgill@nativecampusadvertising.com",
    hs_email_to_firstname="Inderpal",
    hs_email_to_lastname="gill",
    hs_email_direction="FORWARDED_EMAIL",
    hs_email_status="SENT",
    hubspot_owner_id="30387473",
    hs_email_text=(
        "Inderpal Gill\r\n\r\nLocal Bookings Manager"
        " - Campus Advertising - 0161 768 8153"
    ),
)

# Incoming email from an external contact - should be excluded by the
# direction filter (INCOMING_EMAIL).
INCOMING_EMAIL = make_hubspot_email(
    id="439472945346",
    hs_createdate="2026-02-01T13:25:29.404Z",
    hs_timestamp="2026-02-01T13:25:22Z",
    hs_email_subject="Fw: University of Leeds - Health & Wellbeing Events",
    hs_email_from_email="emily.cotter@leedsmind.org.uk",
    hs_email_from_firstname="Emily",
    hs_email_from_lastname="Cotter",
    hs_email_to_email="Matthewbillington@nativecampusadvertising.com",
    hs_email_to_firstname="Matthew",
    hs_email_to_lastname="Billington",
    hs_email_direction="INCOMING_EMAIL",
    hs_email_status=None,
    hubspot_owner_id="29131851",
    hs_email_text=(
        "Hi Matthew,\r\n\r\nThank you for getting in touch with this"
        " opportunity.\r\n\r\nCould you let me know the cost associated"
        " with event involvement, please?"
    ),
)

# Outgoing email with CC recipients.
EMAIL_WITH_CC = make_hubspot_email(
    id="440723608775",
    hs_createdate="2026-02-02T09:04:55.745Z",
    hs_timestamp="2026-02-02T09:05:10.687Z",
    hs_email_subject=(
        "Re: Entertainment, Leisure & Hospitality Fair"
        " - JMU - February 16th"
    ),
    hs_email_from_email="inderpalgill@nativecampusadvertising.com",
    hs_email_from_firstname="Inderpal",
    hs_email_from_lastname="Gill",
    hs_email_to_email="liverpool@pixel-bar.co.uk",
    hs_email_to_firstname="Caitlin",
    hs_email_to_lastname="Small",
    hs_email_cc_email="Edward@pixel-bar.co.uk;Lee@pixel-bar.co.uk",
    hs_email_direction="EMAIL",
    hs_email_status="SENT",
    hubspot_owner_id="30387473",
    hs_email_text=(
        "Morning, \n\n\n\nAll good, no rush from my end. I know you"
        " previously mentioned you had marketing material on-site so"
        " that gives more time for everyone in the potential lead-up"
        " to the event. \n\n\n\nBest, \n\nIndy"
    ),
)

# Bounced email - valid outgoing email that failed delivery.
BOUNCED_EMAIL = make_hubspot_email(
    id="440903735527",
    hs_createdate="2026-02-02T11:01:50.010Z",
    hs_timestamp="2026-02-02T12:00:06.274Z",
    hs_email_subject="Napier Uni - February Student Promo Event",
    hs_email_from_email="inderpalgill@nativecampusadvertising.com",
    hs_email_from_firstname="Inderpal",
    hs_email_from_lastname="Gill",
    hs_email_to_email="thesicillianpastryshop@yahoo.co.uk",
    hs_email_to_firstname=None,
    hs_email_to_lastname=None,
    hs_email_direction="EMAIL",
    hs_email_status="BOUNCED",
    hubspot_owner_id="30387473",
    hs_email_text=(
        "Hi team, \n\n\n\nI hope you don't mind me reaching out, I work"
        " within the F&B team at Native - the company who handle the"
        " campus fairs within Edinburgh Napier University."
    ),
)

# Email with null from_email and null metadata - direction says EMAIL but
# all identifying fields are missing. Should be excluded by the domain filter.
NULL_METADATA_EMAIL = make_hubspot_email(
    id="441384290542",
    hs_createdate="2026-02-02T11:17:08.150Z",
    hs_timestamp="2026-02-02T11:17:08.150Z",
    hs_email_subject=None,
    hs_email_from_email=None,
    hs_email_from_firstname=None,
    hs_email_from_lastname=None,
    hs_email_to_email=None,
    hs_email_to_firstname=None,
    hs_email_to_lastname=None,
    hs_email_direction="EMAIL",
    hs_email_status=None,
    hubspot_owner_id="31115440",
    hs_email_text=(
        "Hi Murrayfield Bar & Kitchen team\n I work with Napier"
        " Edinburgh University Students\u2019 Union and help businesses"
        " connect directly with students on campus through fairs and"
        " events."
    ),
)

# Short outgoing email - minimal body content.
SHORT_BODY_EMAIL = make_hubspot_email(
    id="441511205111",
    hs_createdate="2026-02-02T13:17:50.976Z",
    hs_timestamp="2026-02-02T13:17:59.738Z",
    hs_email_subject="Edinburgh Napier University invites you!",
    hs_email_from_email="setaitarokodrava@nativecampusadvertising.com",
    hs_email_from_firstname="Setaita",
    hs_email_from_lastname="Rokodrava",
    hs_email_to_email="info@theweeboulangerie.co.uk",
    hs_email_to_firstname=None,
    hs_email_to_lastname=None,
    hs_email_direction="EMAIL",
    hs_email_status="SENT",
    hubspot_owner_id="78033054",
    hs_email_text=(
        "Good afternoon The Wee Boulangerie, \n\n\n\nHope all is well."
        " Edinburgh Napier University is hosting an event on the 5th"
        " February. If you would like more info please let me know."
        " \n\n\n\nThanks, Setaita Rokodrava\nEvents Outreach"
        " - Campus Advertising - 02039976049"
    ),
)

# Second incoming email - external contact replying to a rep.
INCOMING_REPLY = make_hubspot_email(
    id="439578758363",
    hs_createdate="2026-02-01T14:37:09.506Z",
    hs_timestamp="2026-02-01T14:37:05.000Z",
    hs_email_subject="Re: Pen to Paper - Refreshers Fair",
    hs_email_from_email="graeme@pentopaperonline.com",
    hs_email_from_firstname="Graeme",
    hs_email_from_lastname="Ross",
    hs_email_to_email="aaronsalins@nativecampusadvertising.com",
    hs_email_to_firstname="Aaron",
    hs_email_to_lastname="Salins",
    hs_email_direction="INCOMING_EMAIL",
    hs_email_status=None,
    hubspot_owner_id="29646986",
    hs_email_text=(
        "Hi Aaron,\r\n\r\nThanks for the follow-up. We're definitely"
        " interested in the refreshers fair. Can you send over the"
        " pricing details?\r\n\r\nCheers,\r\nGraeme"
    ),
)


# ---------------------------------------------------------------------------
# Pre-built API response fixtures
# ---------------------------------------------------------------------------

def single_page_response():
    """Response containing one page of mixed email types - no further pages."""
    return make_hubspot_response(
        [
            OUTGOING_SALES_EMAIL,
            NATIVE_FM_EMAIL,
            FORWARDED_EMAIL,
            INCOMING_EMAIL,
            EMAIL_WITH_CC,
            BOUNCED_EMAIL,
            NULL_METADATA_EMAIL,
            SHORT_BODY_EMAIL,
            INCOMING_REPLY,
        ],
        total=9,
    )


def paginated_response_page_1():
    """First page of a two-page result set. Includes the pagination cursor."""
    return make_hubspot_response(
        [
            OUTGOING_SALES_EMAIL,
            NATIVE_FM_EMAIL,
            INCOMING_EMAIL,
            EMAIL_WITH_CC,
        ],
        total=9,
        after="4",
    )


def paginated_response_page_2():
    """Second (final) page of a two-page result set. No pagination cursor."""
    return make_hubspot_response(
        [
            FORWARDED_EMAIL,
            BOUNCED_EMAIL,
            NULL_METADATA_EMAIL,
            SHORT_BODY_EMAIL,
            INCOMING_REPLY,
        ],
        total=9,
    )


def empty_response():
    """Response with no results - for testing end-of-data or empty date range."""
    return make_hubspot_response([], total=0)


def rate_limited_response():
    """HTTP 429 response body and headers for testing rate-limit handling."""
    return {
        "status": "error",
        "message": "You have reached your secondly limit.",
        "correlationId": "abc-123-def-456",
        "category": "RATE_LIMITS",
    }
