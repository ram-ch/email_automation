from __future__ import annotations


def render_email_html(
    body_text: str,
    hotel_name: str,
    hotel_address: str,
    hotel_phone: str,
    hotel_email: str,
) -> str:
    """Render a guest email as branded HTML with inline CSS."""
    # Convert plain text newlines to HTML line breaks
    body_html = body_text.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background-color:#f4f4f4; font-family:Georgia, 'Times New Roman', serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f4f4; padding:32px 0;">
<tr><td align="center">
<table role="presentation" width="600" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:4px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.08);">

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
