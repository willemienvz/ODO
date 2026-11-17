import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.request import Request, urlopen
import html as html_lib

STATE = Path("seen.json")
PAGE = "https://www.onedayonly.co.za/"

request = Request(PAGE, headers={"User-Agent": "Mozilla/5.0"})
html = urlopen(request, timeout=60).read().decode("utf-8", "replace")
match = re.search(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    html,
)
if not match:
    raise SystemExit("Homepage did not contain deal data.")

payload = json.loads(match.group(1))
deals = []

def walk(node):
    if isinstance(node, dict):
        if "saving" in node and "retailPrice" in node and node.get("id"):
            deals.append(node)
            return
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for value in node:
            walk(value)

walk(payload["props"]["pageProps"]["homePage"])

def is_hit(deal):
    saving = deal.get("saving") or {}
    percent = saving.get("percent")
    return (
        isinstance(percent, (int, float))
        and percent > 69
        and not deal.get("isSoldOut")
    )

seen = set(json.loads(STATE.read_text(encoding="utf-8"))) if STATE.exists() else set()
fresh = []
already = set()
for deal in deals:
    if not is_hit(deal) or deal["id"] in already:
        continue
    already.add(deal["id"])
    if deal["id"] not in seen:
        fresh.append(deal)

if fresh:
    plain_parts = []
    html_parts = []
    for deal in fresh:
        product_url = f"https://www.onedayonly.co.za/products/{deal['id']}"
        name = deal["name"]
        percent = deal["saving"]["percent"]
        price = deal["price"]["formattedValue"]
        retail = deal["retailPrice"]["formattedValue"]
        picture = ((deal.get("image") or {}).get("url")) or ""
        if picture and "?" not in picture:
            picture += "?auto=compress,format&w=480"
        plain_parts.append(
            f"{percent}% off — {name}\n"
            f"Now {price} (was {retail})\n"
            f"{product_url}"
        )
        image_html = ""
        if picture:
            image_html = (
                f'<p><img src="{html_lib.escape(picture, quote=True)}" '
                f'alt="{html_lib.escape(name)}" width="280"></p>'
            )
        html_parts.append(
            "<div>"
            f"{image_html}"
            f"<p><strong>{html_lib.escape(str(percent))}% off</strong> — {html_lib.escape(name)}<br>"
            f"Now {html_lib.escape(price)} (was {html_lib.escape(retail)})<br>"
            f'<a href="{html_lib.escape(product_url, quote=True)}">View deal</a></p>'
            "</div>"
        )
    recipients = [
        address.strip()
        for address in os.environ["ODO_MAIL_TO"].split(",")
        if address.strip()
    ]
    if not recipients:
        raise SystemExit("ODO_MAIL_TO has no email addresses.")
    message = EmailMessage()
    message["Subject"] = f"OneDayOnly: {len(fresh)} deal(s) over 69% off"
    message["From"] = os.environ["ODO_MAIL_FROM"]
    message["To"] = ", ".join(recipients)
    message.set_content("\n\n".join(plain_parts))
    message.add_alternative(
        "<html><body>" + "<hr>".join(html_parts) + "</body></html>",
        subtype="html",
    )
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["ODO_SMTP_USERNAME"], os.environ["ODO_SMTP_PASSWORD"])
        smtp.send_message(message, to_addrs=recipients)
    seen.update(deal["id"] for deal in fresh)
STATE.write_text(json.dumps(sorted(seen), indent=2) + "\n", encoding="utf-8")