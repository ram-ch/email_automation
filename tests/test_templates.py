from app.templates import render_email_html, _markdown_to_html


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
    assert "**" not in html.split("<strong>")[0]


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


def test_render_email_html_shows_to_from():
    """When sender_email is provided, To/From is shown."""
    html = render_email_html(
        body_text="Hello.",
        hotel_name="Hotel",
        hotel_address="Addr",
        hotel_phone="Phone",
        hotel_email="hotel@test.com",
        sender_email="guest@test.com",
    )
    assert "hotel@test.com" in html
    assert "guest@test.com" in html
    assert "From:" in html
    assert "To:" in html
