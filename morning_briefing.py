from datetime import datetime, timedelta
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

DBX_APP_KEY = os.environ.get("DBX_APP_KEY", "").strip()
DBX_APP_SECRET = os.environ.get("DBX_APP_SECRET", "").strip()
DBX_REFRESH_TOKEN = os.environ.get("DBX_REFRESH_TOKEN", "").strip()
DBX_PATH = "/casa_barra_calendar.json"
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
WEBAPP_URL = "https://luigibarra.github.io/casa-barra-calendar/"

MEMBERS = {
    "tutti": "👨‍👩‍👧‍👦 Tutti",
    "luigi": "👨🏻 Luigi",
    "vale": "👱🏻‍♀️ Vale",
    "leo": "👦🏻 Leo",
    "vitto": "👧🏻 Kiki",
}

DRIVERS = {
    "luigi": "👨🏻 Luigi",
    "vale": "👱🏻‍♀️ Vale",
    "entrambi": "👨🏻👱🏻‍♀️ Insieme",
    "nonni": "👵🏼 Nonni/Altri",
}


def check_secrets():
  missing = []
  for name, val in [
      ("DBX_APP_KEY", DBX_APP_KEY),
      ("DBX_APP_SECRET", DBX_APP_SECRET),
      ("DBX_REFRESH_TOKEN", DBX_REFRESH_TOKEN),
      ("TG_BOT_TOKEN", TG_BOT_TOKEN),
      ("TG_CHAT_ID", TG_CHAT_ID),
  ]:
    if not val:
      missing.append(name)
  if missing:
    print(f"❌ ERRORE: Mancano questi Secrets su GitHub: {', '.join(missing)}")
    sys.exit(1)


def get_dropbox_access_token():
  data = urllib.parse.urlencode({
      "grant_type": "refresh_token",
      "refresh_token": DBX_REFRESH_TOKEN,
      "client_id": DBX_APP_KEY,
      "client_secret": DBX_APP_SECRET,
  }).encode("utf-8")
  req = urllib.request.Request(
      "https://api.dropboxapi.com/oauth2/token", data=data
  )
  try:
    with urllib.request.urlopen(req) as resp:
      return json.loads(resp.read().decode("utf-8"))["access_token"]
  except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="ignore")
    print(f"❌ Errore autenticazione Dropbox ({e.code}): {body}")
    sys.exit(1)


def download_calendar_db(token):
  req = urllib.request.Request(
      "https://content.dropboxapi.com/2/files/download",
      headers={
          "Authorization": f"Bearer {token}",
          "Dropbox-API-Arg": json.dumps({"path": DBX_PATH}),
      },
  )
  try:
    with urllib.request.urlopen(req) as resp:
      return json.loads(resp.read().decode("utf-8"))
  except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="ignore")
    print(f"❌ Impossibile scaricare {DBX_PATH} da Dropbox ({e.code}): {body}")
    print(
        "💡 Suggerimento: Apri la Web App e clicca su 'Salva su Dropbox' per"
        " creare il file la prima volta."
    )
    sys.exit(1)


def send_telegram(text):
  url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
  payload_dict = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
  if WEBAPP_URL.startswith("https://"):
    payload_dict["reply_markup"] = {
        "inline_keyboard": [
            [{"text": "📅 Apri Calendario Casa Barra", "url": WEBAPP_URL}]
        ]
    }
  payload = json.dumps(payload_dict).encode("utf-8")
  req = urllib.request.Request(
      url, data=payload, headers={"Content-Type": "application/json"}
  )
  try:
    with urllib.request.urlopen(req) as resp:
      print("✅ Messaggio inviato su Telegram!")
  except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="ignore")
    print(f"❌ Errore invio Telegram ({e.code}): {body}")
    sys.exit(1)


def main():
  check_secrets()
  now_rome = datetime.now(ZoneInfo("Europe/Rome"))
  today_iso = now_rome.strftime("%Y-%m-%d")
  in_7_days_iso = (now_rome + timedelta(days=7)).strftime("%Y-%m-%d")

  token = get_dropbox_access_token()
  db = download_calendar_db(token)
  events = db.get("events", [])
  dinners = db.get("dinners", {})

  todays_events = sorted(
      [e for e in events if e.get("date") == today_iso],
      key=lambda x: x.get("start") or "99:99",
  )
  dinner_today = dinners.get(today_iso)

  series_map = {}
  for e in events:
    sid = e.get("seriesId")
    if sid:
      series_map.setdefault(sid, []).append(e)

  expiring_alerts = []
  for sid, sevents in series_map.items():
    sevents.sort(key=lambda x: x.get("date", ""))
    if len(sevents) >= 2:
      last_date = sevents[-1].get("date")
      penultimate_date = sevents[-2].get("date")
      if penultimate_date == today_iso or last_date == in_7_days_iso:
        expiring_alerts.append(
            (sevents[-1].get("icon", "🔁"), sevents[-1].get("title", ""), last_date)
        )

  if not todays_events and not dinner_today and not expiring_alerts:
    print("ℹ️ Nessun impegno oggi, nessuna notifica inviata.")
    return

  msg = (
      "☀️ <b>Buongiorno Famiglia Barra!</b>\nProgramma di oggi"
      f" (<b>{today_iso}</b>):\n\n"
  )
  if not todays_events:
    msg += "🎉 <i>Nessun impegno in calendario per oggi!</i>\n\n"
  else:
    for ev in todays_events:
      m_str = ", ".join(MEMBERS.get(m, m) for m in ev.get("members", []))
      start_t = ev.get("start") or "Tutto il giorno"
      msg += (
          f"• <b>{start_t}</b> — {ev.get('icon', '📌')} <b>{ev.get('title')}</b>"
          f" ({m_str})"
      )
      d_to = DRIVERS.get(ev.get("driverTo", ""))
      d_from = DRIVERS.get(ev.get("driverFrom", ""))
      if d_to or d_from:
        msg += (
            f"\n   └ 🚗 Porta: <b>{d_to or '—'}</b> | 🏡 Riprende:"
            f" <b>{d_from or '—'}</b>"
        )
      todos = [
          c.get("text") for c in ev.get("checklist", []) if not c.get("done")
      ]
      if todos:
        msg += f"\n   └ 📋 Da ricordare: <i>{', '.join(todos)}</i>"
      msg += "\n\n"

  if dinner_today:
    msg += f"🍽️ <b>Stasera a cena:</b> {dinner_today}\n"

  if expiring_alerts:
    msg += "\n⚠️ <b>Avviso Serie in Chiusura (manca 1 settimana!):</b>\n"
    for icon, title, ldate in expiring_alerts:
      msg += f"• {icon} <b>{title}</b> termina il <b>{ldate}</b>\n"

  send_telegram(msg)


if __name__ == "__main__":
  main()
