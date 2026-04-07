from app.templates import render_email_html, render_preview_html, _markdown_to_html


def test_render_email_html_contains_body():
    """The rendered HTML includes the email body text."""
    html = render_email_html(
        body_text="Dear Erik, your room is booked.",
        hotel_name="Grand Oslo Hotel",
        hotel_address="Karl Johans gate 31, 0159 Oslo, Norway",
        hotel_phone="+47 22 00 00 00",
        hotel_email="reservations@grandoslohotel.com",
    )
    assert "Dear Erik, your room is booked." in html
    assert "Grand Oslo Hotel" in html
    assert "Karl Johans gate 31" in html
    assert "+47 22 00 00 00" in html
    assert "reservations@grandoslohotel.com" in html


def test_render_email_html_is_valid_html():
    """The rendered output starts with html tag and contains required structure."""
    html = render_email_html(
        body_text="Test body.",
        hotel_name="Test Hotel",
        hotel_address="123 Street",
        hotel_phone="+1 000",
        hotel_email="test@hotel.com",
    )
    assert html.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "<body" in html


def test_render_email_html_handles_newlines():
    """Newlines in body text are converted to <br> tags."""
    html = render_email_html(
        body_text="Line one.\nLine two.\nLine three.",
        hotel_name="Hotel",
        hotel_address="Addr",
        hotel_phone="Phone",
        hotel_email="e@h.com",
    )
    assert "Line one.<br>" in html
    assert "Line one." in html
    assert "Line two." in html


def test_render_rejection_email():
    """The rejection template uses the same layout."""
    html = render_email_html(
        body_text="Thank you for contacting Grand Oslo Hotel. Your request is being reviewed by our reservations team, and we will follow up with you shortly.",
        hotel_name="Grand Oslo Hotel",
        hotel_address="Karl Johans gate 31, 0159 Oslo, Norway",
        hotel_phone="+47 22 00 00 00",
        hotel_email="reservations@grandoslohotel.com",
    )
    assert "being reviewed" in html
    assert "Grand Oslo Hotel" in html


def test_markdown_bold_converted():
    """Markdown **bold** is converted to <strong> tags."""
    html = render_email_html(
        body_text="Room: **Standard Double** - 1,800 NOK",
        hotel_name="Hotel",
        hotel_address="Addr",
        hotel_phone="Phone",
        hotel_email="e@h.com",
    )
    assert "<strong>Standard Double</strong>" in html
    assert "**" not in html.split("<strong>")[0]  # no raw markdown


def test_markdown_separator_converted():
    """Markdown --- separator is converted to <hr> tag."""
    html = render_email_html(
        body_text="First section\n---\nSecond section",
        hotel_name="Hotel",
        hotel_address="Addr",
        hotel_phone="Phone",
        hotel_email="e@h.com",
    )
    assert "<hr" in html
    assert "---" not in html.replace("<!-", "")  # no raw --- (ignoring HTML comments)


def test_render_preview_html_contains_metadata():
    """Preview page includes metadata panel and email."""
    email_html = "<div>Test email content</div>"
    html = render_preview_html(
        email_html=email_html,
        action_plan=[{"step": 1, "description": "Create reservation"}],
        mode="autonomous",
        status="completed",
        risk_flag=None,
    )
    assert "Agent Response" in html
    assert "Guest Email Preview" in html
    assert "Create reservation" in html
    assert "autonomous" in html
    assert "Test email content" in html


def test_render_preview_html_shows_risk_flag():
    """Preview page shows risk flag when present."""
    html = render_preview_html(
        email_html="<div>Escalation email</div>",
        action_plan=[],
        mode="human_approval",
        status="escalated",
        risk_flag="non-refundable cancellation",
    )
    assert "non-refundable cancellation" in html
    assert "Risk Flag" in html
