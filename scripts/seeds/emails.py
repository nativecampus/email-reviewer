"""Seed data for the emails table.

Derived from the HubSpot fixture data in tests/fixtures/hubspot.py. Only
outgoing sales emails (direction EMAIL or FORWARDED_EMAIL from a native domain)
are included - the same filter that the fetcher applies in production.
"""

from datetime import datetime

EMAILS = [
    {
        "hubspot_id": "440807712958",
        "timestamp": datetime(2026, 2, 2, 8, 18, 0, ),
        "from_name": "Kieran Berry Campbell",
        "from_email": "kieranberrycampbell@nativecampusadvertising.com",
        "to_name": "Acomb Travel",
        "to_email": "bookings@destination1.co.uk",
        "subject": "Engaging with Students on campus",
        "body_text": (
            "Hi there, \n\nJust checking back in as we continue to confirm "
            "spaces for the upcoming student fair."
        ),
        "direction": "EMAIL",
        "fetched_at": datetime(2026, 2, 2, 8, 18, 6, ),
    },
    {
        "hubspot_id": "440815170777",
        "timestamp": datetime(2026, 2, 2, 9, 18, 30, ),
        "from_name": "Sheraaz Ahmed",
        "from_email": "sheraazahmed@native.fm",
        "to_name": "Mariah-Louise & Thomas",
        "to_email": "info@thefinestfudgeco.co.uk",
        "subject": "Re: Native x The Finest Fudge Co",
        "body_text": (
            "Hi Mariah-Louise and Thomas,\r\n\r\nHope you had a great weekend."
            "\r\n\r\nJust following up on my previous email to see if you had any"
            "\r\navailability this week for an online meeting?"
            "\r\n\r\nPlease let me know and I can send over an invite."
            "\r\n\r\nKind Regards"
        ),
        "direction": "EMAIL",
        "fetched_at": datetime(2026, 2, 2, 9, 18, 33, ),
    },
    {
        "hubspot_id": "440723608775",
        "timestamp": datetime(2026, 2, 2, 9, 5, 10, ),
        "from_name": "Inderpal Gill",
        "from_email": "inderpalgill@nativecampusadvertising.com",
        "to_name": "Caitlin Small",
        "to_email": "liverpool@pixel-bar.co.uk",
        "subject": "Re: Entertainment, Leisure & Hospitality Fair - JMU - February 16th",
        "body_text": (
            "Morning, \n\n\n\nAll good, no rush from my end. I know you"
            " previously mentioned you had marketing material on-site so"
            " that gives more time for everyone in the potential lead-up"
            " to the event. \n\n\n\nBest, \n\nIndy"
        ),
        "direction": "EMAIL",
        "fetched_at": datetime(2026, 2, 2, 9, 4, 55, ),
    },
    {
        "hubspot_id": "440903735527",
        "timestamp": datetime(2026, 2, 2, 12, 0, 6, ),
        "from_name": "Inderpal Gill",
        "from_email": "inderpalgill@nativecampusadvertising.com",
        "to_name": None,
        "to_email": "thesicillianpastryshop@yahoo.co.uk",
        "subject": "Napier Uni - February Student Promo Event",
        "body_text": (
            "Hi team, \n\n\n\nI hope you don't mind me reaching out, I work"
            " within the F&B team at Native - the company who handle the"
            " campus fairs within Edinburgh Napier University."
        ),
        "direction": "EMAIL",
        "fetched_at": datetime(2026, 2, 2, 11, 1, 50, ),
    },
    {
        "hubspot_id": "441511205111",
        "timestamp": datetime(2026, 2, 2, 13, 17, 59, ),
        "from_name": "Setaita Rokodrava",
        "from_email": "setaitarokodrava@nativecampusadvertising.com",
        "to_name": None,
        "to_email": "info@theweeboulangerie.co.uk",
        "subject": "Edinburgh Napier University invites you!",
        "body_text": (
            "Good afternoon The Wee Boulangerie, \n\n\n\nHope all is well."
            " Edinburgh Napier University is hosting an event on the 5th"
            " February. If you would like more info please let me know."
            " \n\n\n\nThanks, Setaita Rokodrava\nEvents Outreach"
            " - Campus Advertising - 02039976049"
        ),
        "direction": "EMAIL",
        "fetched_at": datetime(2026, 2, 2, 13, 17, 50, ),
    },
]
