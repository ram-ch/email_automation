from __future__ import annotations

import re
from html import escape


def _markdown_to_html(text: str) -> str:
    """Convert basic markdown formatting to HTML."""
    # Bold: **text** → <strong>text</strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text* → <em>text</em>
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # Horizontal rules: --- or ___ on their own line → <hr>
    text = re.sub(r'\n---+\n', '\n<hr style="border:none; border-top:1px solid #e0e0e0; margin:16px 0;">\n', text)
    text = re.sub(r'^---+\n', '<hr style="border:none; border-top:1px solid #e0e0e0; margin:16px 0;">\n', text)
    return text


def render_email_html(
    body_text: str,
    hotel_name: str,
    hotel_address: str,
    hotel_phone: str,
    hotel_email: str,
) -> str:
    """Render a guest email as branded HTML with inline CSS."""
    # Convert markdown formatting to HTML, then newlines to <br>
    body_html = _markdown_to_html(body_text)
    body_html = body_html.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Georgia, 'Times New Roman', serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f4f4; padding:32px 0;">
<tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:800px; background-color:#ffffff; border-radius:4px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr>
    <td style="background-color:#1a3c5e; padding:28px 40px; text-align:center;">
      <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:normal; letter-spacing:1px;">
        {hotel_name}
      </h1>
    </td>
  </tr>

  <!-- Body -->
  <tr>
    <td style="padding:36px 40px; color:#2c2c2c; font-size:15px; line-height:1.7;">
      {body_html}
    </td>
  </tr>

  <!-- Divider -->
  <tr>
    <td style="padding:0 40px;">
      <hr style="border:none; border-top:1px solid #e0e0e0; margin:0;">
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:24px 40px 32px; color:#888888; font-size:12px; line-height:1.6; text-align:center;">
      <strong>{hotel_name}</strong><br>
      {hotel_address}<br>
      {hotel_phone}<br>
      <a href="mailto:{hotel_email}" style="color:#1a3c5e; text-decoration:none;">{hotel_email}</a>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def render_preview_html(
    email_html: str,
    action_plan: list[dict],
    mode: str,
    status: str,
    risk_flag: str | None,
) -> str:
    """Render a full preview page with the email and metadata panel."""
    # Status badge colors
    status_colors = {
        "completed": "#2e7d32",
        "approved": "#2e7d32",
        "rejected": "#c62828",
        "escalated": "#e65100",
    }
    badge_color = status_colors.get(status, "#555")

    # Build action plan rows
    if action_plan:
        plan_rows = ""
        for step in action_plan:
            plan_rows += (
                f'<tr>'
                f'<td style="padding:6px 12px; border-bottom:1px solid #eee; color:#666; width:30px; text-align:center;">{step["step"]}</td>'
                f'<td style="padding:6px 12px; border-bottom:1px solid #eee; color:#2c2c2c;">{escape(step["description"])}</td>'
                f'</tr>'
            )
        action_plan_html = (
            f'<table style="width:100%; border-collapse:collapse; margin-top:8px;">'
            f'{plan_rows}'
            f'</table>'
        )
    else:
        action_plan_html = '<p style="color:#888; margin:8px 0 0 0; font-style:italic;">No actions</p>'

    # Risk flag
    risk_html = ""
    if risk_flag:
        risk_html = (
            f'<div style="margin-top:16px; padding:12px 16px; background-color:#fff3e0; '
            f'border-left:4px solid #e65100; border-radius:2px;">'
            f'<strong style="color:#e65100;">Risk Flag:</strong> '
            f'<span style="color:#2c2c2c;">{escape(risk_flag)}</span>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Email Preview</title>
</head>
<body style="margin:0; padding:0; background-color:#e8e8e8; font-family:-apple-system, 'Segoe UI', Roboto, sans-serif;">

<!-- Metadata Panel -->
<div style="max-width:680px; margin:24px auto 0; background:#ffffff; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,0.1); padding:24px 32px;">
  <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:16px;">
    <h2 style="margin:0; font-size:16px; color:#2c2c2c; font-weight:600;">Agent Response</h2>
    <span style="display:inline-block; padding:4px 12px; border-radius:12px; font-size:12px; font-weight:600; color:#fff; background-color:{badge_color}; text-transform:uppercase; letter-spacing:0.5px;">
      {status}
    </span>
  </div>
  <div style="font-size:13px; color:#666; margin-bottom:12px;">
    Mode: <strong style="color:#2c2c2c;">{mode}</strong>
  </div>
  <div style="font-size:13px; color:#666;">
    <strong style="color:#2c2c2c;">Action Plan</strong>
  </div>
  {action_plan_html}
  {risk_html}
</div>

<!-- Email Preview Label -->
<div style="max-width:680px; margin:20px auto 8px; padding:0 4px;">
  <span style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:#888; font-weight:600;">Guest Email Preview</span>
</div>

<!-- Email Preview -->
<div style="max-width:680px; margin:0 auto 32px; border-radius:6px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,0.1);">
  {email_html}
</div>

</body>
</html>"""
