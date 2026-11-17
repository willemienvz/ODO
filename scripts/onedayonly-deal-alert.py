import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.request import Request, urlopen

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
    types = deal.get("dealTypes") or []
    promotional = deal.get("isPromotionalDeal") is True or "PD" in types
    return (
        and isinstance(percent, (int, float))
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
    lines = []
    for deal in fresh:
        lines.append(
            f"{deal['saving']['percent']}% off — {deal['name']}\n"
            f"Now {deal['price']['formattedValue']} (was {deal['retailPrice']['formattedValue']})\n"
            f"https://www.onedayonly.co.za/products/{deal['id']}"
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
    message.set_content("\n\n".join(lines))
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["ODO_SMTP_USERNAME"], os.environ["ODO_SMTP_PASSWORD"])
        smtp.send_message(message, to_addrs=recipients)
    seen.update(deal["id"] for deal in fresh)
STATE.write_text(json.dumps(sorted(seen), indent=2) + "\n", encoding="utf-8")