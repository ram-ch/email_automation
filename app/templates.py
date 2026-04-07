from __future__ import annotations

import re
from html import escape


def _markdown_to_html(text: str) -> str:
    """Convert basic markdown formatting to HTML."""
    # Bold: **text** → <strong>text</strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text* → <em>text</em>
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Horizontal rules: --- on their own line → <hr>
    text = re.sub(r'\n---+\n', '\n<hr style="border:none; border-top:1px solid #ddd; margin:12px 0;">\n', text)
    text = re.sub(r'^---+\n', '<hr style="border:none; border-top:1px solid #ddd; margin:12px 0;">\n', text)
    return text


def render_email_html(
    body_text: str,
    hotel_name: str,
    hotel_address: str,
    hotel_phone: str,
    hotel_email: str,
    sender_email: str = "",
) -> str:
    """Render a guest email as plain, clean HTML."""
    body_html = _markdown_to_html(body_text)
    body_html = body_html.replace("\n", "<br>\n")

    # To/From line
    to_from_html = ""
    if sender_email:
        to_from_html = (
            f'<div style="margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid #ddd; '
            f'font-size:13px; color:#666; line-height:1.6;">'
            f'<strong>From:</strong> {hotel_email}<br>'
            f'<strong>To:</strong> {sender_email}'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:24px; font-family:Georgia, 'Times New Roman', serif; font-size:15px; line-height:1.7; color:#2c2c2c;">
{to_from_html}
{body_html}
</body>
</html>"""
