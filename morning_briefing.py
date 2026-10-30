import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Script automatico "Buongiorno Casa Barra" (gira su GitHub Actions ogni mattina alle 07:30)
DBX_APP_KEY = os.environ["DBX_APP_KEY"]
DBX_APP_SECRET = os.environ["DBX_APP_SECRET"]
DBX_REFRESH_TOKEN = os.environ["DBX_REFRESH_TOKEN"]
DBX_PATH = "/casa_barra_calendar.json"
TG_BOT_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
WEBAPP_URL = "https://luigibarra.github.io/casa-barra-calendar/"

MEMBERS = {
    "tutti": "👨‍👩‍👧‍👦 Tutti",
    "luigi": "👨🏻 Luigi",
    "vale": "👱🏻‍♀️ Vale",
    "leo": "👦🏻 Leo",
    "vitto": "👧🏻 Kiki"
}

DRIVERS = {
    "luigi": "👨🏻 Luigi",
    "vale": "👱🏻‍♀️ Vale",
    "entrambi": "👨🏻👱🏻‍♀️ Insieme",
    "nonni": "👵🏼 Nonni/Altri"
}

def get_dropbox_access_token():
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": DBX_REFRESH_TOKEN,
        "client_id": DBX_APP_KEY,
        "client_secret": DBX_APP_SECRET
    }).encode("utf-8")
    req = urllib.request.Request("https://api.dropboxapi.com/oauth2/token", data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]

def download_calendar_db(token):
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/files/download",
        headers={
            "Authorization": f"Bearer {token}",
            "Dropbox-API-Arg": json.dumps({"path": DBX_PATH})
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[{"text": "📅 Apri Calendario Casa Barra", "url": WEBAPP_URL}]]
        }
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

def main():
    now_rome = datetime.now(ZoneInfo("Europe/Rome"))
    today_iso = now_rome.strftime("%Y-%m-%d")
    in_7_days_iso = (now_rome + timedelta(days=7)).strftime("%Y-%m-%d")

    token = get_dropbox_access_token()
    db = download_calendar_db(token)
    events = db.get("events", [])
    dinners = db.get("dinners", {})

    todays_events = sorted(
        [e for e in events if e.get("date") == today_iso],
        key=lambda x: x.get("start") or "99:99"
    )
    dinner_today = dinners.get(today_iso)

    # Controlla se qualche serie settimanale ha il penultimo incontro oggi (1 settimana dalla fine)
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
                expiring_alerts.append((sevents[-1].get("icon", "🔁"), sevents[-1].get("title", ""), last_date))

    # Invia il messaggio del mattino se ci sono impegni oggi, una cena segnata o una serie in scadenza
    if not todays_events and not dinner_today and not expiring_alerts:
        print("Nessun impegno oggi, nessuna notifica inviata.")
        return

    msg = f"☀️ <b>Buongiorno Famiglia Barra!</b>\nProgramma di oggi (<b>{today_iso}</b>):\n\n"
    if not todays_events:
        msg += "🎉 <i>Nessun impegno in calendario per oggi!</i>\n\n"
    else:
        for ev in todays_events:
            m_str = ", ".join(MEMBERS.get(m, m) for m in ev.get("members", []))
            start_t = ev.get("start") or "Tutto il giorno"
            msg += f"• <b>{start_t}</b> — {ev.get('icon', '📌')} <b>{ev.get('title')}</b> ({m_str})"
            d_to = DRIVERS.get(ev.get("driverTo", ""))
            d_from = DRIVERS.get(ev.get("driverFrom", ""))
            if d_to or d_from:
                msg += f"\n   └ 🚗 Porta: <b>{d_to or '—'}</b> | 🏡 Riprende: <b>{d_from or '—'}</b>"
            todos = [c.get("text") for c in ev.get("checklist", []) if not c.get("done")]
            if todos:
                msg += f"\n   └ 📋 Da ricordare: <i>{', '.join(todos)}</i>"
            msg += "\n\n"

    if dinner_today:
        msg += f"🍽️ <b>Stasera a cena:</b> {dinner_today}\n"

    if expiring_alerts:
        msg += "\n⚠️ <b>Avviso Serie in Chiusura (manca 1 settimana!):</b>\n"
        for icon, title, ldate in expiring_alerts:
            msg += f"• {icon} <b>{title}</b> termina il <b>{ldate}</b> (apri l'app per prolungarla!)\n"

    send_telegram(msg)
    print("Briefing mattutino inviato con successo!")

if __name__ == "__main__":
    main()
