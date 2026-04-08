# RecruiterAI — Personal-Vermittler Cockpit

**AI-gestütztes CRM- und Voice-Cockpit für Schweizer Personalvermittlungen.**

RecruiterAI ist ein CRM-System mit integriertem Voice-Agent und pro-Kandidat
AI-Chat. Jede eingehende Bewerbung (per E-Mail, LinkedIn oder externer
REST-API) wird automatisch gegen die PostgreSQL-Datenbank abgeglichen — gibt
es noch kein Profil mit dieser Mail-Adresse, wird eines angelegt; andernfalls
landet die Nachricht als Eintrag im Protokoll des bestehenden Profils. Fehlen
Pflichtfelder (Vorname, Nachname, E-Mail, Telefon), fragt die Applikation den
Kandidaten per Follow-up-Mail danach und erstellt das Profil erst, wenn die
Daten vollständig sind.

Der Personal-Vermittler arbeitet in einer minimalen 3-Tab-Oberfläche
(**People · Messages · Jobs**) und kann pro Kandidat ein **AI-Chat-Fenster**
öffnen: Claude kennt den CV + das komplette Protokoll und kann per
Werkzeug-Aufruf Mails verschicken oder Telefonanrufe auslösen. Es können
mehrere Mini-Chats (bis zu 5, abhängig von der Bildschirmgrösse) gleichzeitig
geöffnet und einzeln minimiert werden — wie bei einem Messenger-Dock.

---

## Features

### CRM-Kern
- **CRM Upsert on intake** — jede Mail/Nachricht wird per E-Mail-Adresse
  dedupliziert. Bestehende Profile werden in place aktualisiert, die
  Kommunikations-Historie (Protokoll) bleibt intakt.
- **NOT-NULL Pflichtfelder** (`CRM_REQUIRED_FIELDS`) — fehlt etwas, sendet die
  App automatisch eine **persönliche** Follow-up Mail (Claude verwendet
  Headline, Skills und letzte Stationen aus dem CV, um nicht generisch zu
  klingen) und hält den Kandidaten im Status `info_requested` bis der CV
  vollständig ist.
- **Vereinigtes Protokoll** pro Kandidat: eingehende/ausgehende Mails, Anrufe
  und AI-Chat als Timeline (`GET /api/candidates/{id}/protocol`).
- **CV-Speicher** — der Original-CV wird als Datei persistiert und kann im
  UI direkt im PDF-Viewer geöffnet werden
  (`GET /api/candidates/{id}/cv`).
- **Foto-Extraktion aus dem CV** — beim Ingest wird automatisch das
  Profilfoto aus dem CV (PDF/DOCX) gezogen und unter
  `GET /api/candidates/{id}/photo` ausgeliefert. Recruiter können ein Foto
  manuell hochladen oder die Extraktion erneut anstossen.
- **External Webhook** für Messages aus einer bestehenden Webapp
  (`POST /api/messages/inbound`) — geschützt über `X-Webhook-Secret`
  (Constant-Time Vergleich, optional konfigurierbar via
  `INBOUND_WEBHOOK_SECRET`).
- **Auto-Migrations beim Container-Start** — der Backend-Container wartet
  auf Postgres und führt automatisch `alembic upgrade head` aus, bevor
  Uvicorn startet.
- **Runtime-konfigurierbare CRM-Pflichtfelder** — über die Settings-UI
  kann der Recruiter `CRM_REQUIRED_FIELDS` ohne Redeploy ändern. Die
  Werte werden in einer JSON-Datei im CV-Storage-Volume persistiert und
  bei der nächsten Upsert-Operation automatisch berücksichtigt
  (`PUT /api/settings/runtime`).
- **Live-Events via WebSocket** — neue Mails, eingehende Webhook-Events
  und Chat-Aktionen werden über `/api/events/ws` an das Frontend gepusht,
  sodass die People/Messages/Chat-Ansichten sich ohne manuelles Reload
  aktualisieren. In-Memory Pub/Sub (`EventBroker`), keine zusätzliche
  Infrastruktur nötig.
- **Quadrilingual (DE · EN · FR · IT)** — CH-spezifisch, alle vier
  Landessprachen werden bei Sprach-Erkennung, Follow-up-Mails (inkl.
  Fallback-Templates) und Voice-Opener unterstützt.

### AI-Chat pro Kandidat
- Per-Kandidat Chat mit Claude: System-Prompt enthält CV + Protokoll, damit
  der Bot kontextbezogen antworten kann.
- **Tool-Aufrufe** aus dem Chat: `send_email(subject, body)` oder
  `initiate_call(reason)`. Der Recruiter gibt eine Anweisung in
  Umgangssprache, die App führt sie aus und loggt den Aufruf ins Protokoll.
- **Call-Objective wird end-to-end durchgereicht** — die `reason` aus dem
  AI-Chat ("Frag nach Gehalt und Verfügbarkeit") wird als Query-Parameter
  an den Twilio-Voice-Webhook angehängt, als TwiML `<Parameter>` in den
  Media-Stream gelegt, beim `start`-Event der WebSocket in die
  `CallSession.objective` geschrieben und im `build_system_prompt` als
  "ZUSÄTZLICHER AUFTRAG VOM RECRUITER (höchste Priorität)" angehängt —
  ausserdem im `CallLog.summary` persistiert, damit der Recruiter im
  Protokoll sieht, wozu die KI angerufen hat.
- **Rate-Limit** auf dem Chat-Endpoint: max. 12 Turns pro Kandidat pro
  Minute (in-memory sliding window) — bricht Agent-Loops ab, bevor sie
  Claude- oder Twilio-Kosten verursachen.
- **Mini-Chat-Dock** unten rechts: bis zu 5 Kandidaten parallel, einzeln
  minimierbar. Die Fenster aktualisieren sich live über `chat.append`
  Events, wenn ein anderer Browser-Tab eine Antwort generiert.

### Matching & Voice (aus dem Original übernommen)
- Heuristisches Matching (Skills, Erfahrung, Ort, Salary, Verfügbarkeit)
  plus optionaler semantischer Pass durch Claude.
- Voice-Agent: Twilio Outbound Call → WebSocket Media Stream →
  Deepgram STT → Claude Konversation → ElevenLabs TTS. DE/EN/FR/IT mit
  automatischer Sprach-Erkennung (Heuristik + Claude-Fallback).
- Post-Call Summary per Claude, Mail an Recruiter.

### UI
- Minimaler 3-Tab-Header (People · Messages · Jobs) + "More"-Dropdown
  für Overview/Matches/Calls/Emails/Settings.
- **People-Tab**: einzige Suchleiste matched auf Name, Mail, Telefon,
  Adresse. Grid mit Avatar, Name, Kontakt & Status, sortierbar nach
  zuletzt aktualisiert oder Nachname A–Z. Pagination per "Mehr laden"
  Button (60 Zeilen / Seite).
- **Messages-Tab**: eingehende Nachrichten (Mails und Webhook-Events)
  mit Lesen-Toggle. Pagination per "Mehr laden" Button (50 Zeilen /
  Seite).
- **Jobs-Tab**: Suche nach Titel / Firma / Ort / Beschreibung; Detailseite
  zeigt das Ranking passender Kandidaten per Knopfdruck.
- **Candidate-Detail**: Foto, alle Daten, CV als PDF im iframe, Liste
  passender offener Stellen, vollständiges Protokoll, AI-Chat-Button.

---

## Architektur

```
recruiter-ai/
├── backend/                FastAPI + async SQLAlchemy + Alembic
│   └── app/
│       ├── api/            REST endpoints (inkl. chat, messages)
│       ├── models/         ORM — jetzt mit chat_messages
│       ├── schemas/        Pydantic schemas
│       ├── services/       Business logic
│       │   ├── crm.py             CRM upsert + CV storage + photo wiring
│       │   ├── cv_parser.py       Claude CV parser
│       │   ├── photo_extractor.py CV → profile photo (PDF + DOCX)
│       │   ├── followup_mail.py   Personalised Claude follow-ups
│       │   ├── matching_engine    Heuristik + Semantik (Claude)
│       │   ├── voice_agent.py     Twilio + Deepgram + ElevenLabs (objective)
│       │   └── ...
│       ├── entrypoint.sh   Wait-for-Postgres + alembic upgrade head + run app
│       ├── workers/        Background poller (Email, LinkedIn, Matching)
│       ├── utils/          Prompt templates (inkl. chat system prompt)
│       └── main.py
├── frontend/               React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── components/
│       │   ├── Layout.tsx          3-Tab Header + dropdown
│       │   ├── PeopleTab.tsx       Suche + Kandidaten-Grid
│       │   ├── MessagesTab.tsx     Neue Nachrichten
│       │   ├── JobsTab.tsx         Jobs suchen
│       │   ├── CandidateDetail.tsx Profil + CV PDF + Matches + Protokoll
│       │   ├── JobDetail.tsx       Description + Ranking-Button
│       │   ├── chat/
│       │   │   ├── ChatDockContext.tsx  Fenster-State + max visible
│       │   │   ├── ChatDock.tsx         Fixed-bottom Dock
│       │   │   └── ChatWindow.tsx       Per-Kandidat Mini-Chat
│       │   └── shared/Avatar.tsx
│       ├── hooks/          useApi, useDashboardStats
│       ├── lib/api.ts      Axios client (alle Endpoints)
│       └── types/          Shared TypeScript types
├── docker-compose.yml      Postgres + backend + frontend + cv_storage volume
└── .env.example
```

---

## Quickstart

```bash
cp .env.example .env
# Pflicht:  POSTGRES_PASSWORD, ANTHROPIC_API_KEY
# Optional: EMAIL_IMAP_*, SMTP, TWILIO_*, ELEVENLABS_*, DEEPGRAM_*,
#           INBOUND_WEBHOOK_SECRET (für Production)

make up
open http://localhost:3000
```

Der Backend-Container wartet beim Start auf Postgres und führt automatisch
`alembic upgrade head` aus — `make db-upgrade` ist nur für lokale
Iteration nötig.

Nach dem Start öffnet sich direkt der **People**-Tab. CVs, die per Mail
einlaufen, werden automatisch von `EmailPoller` abgeholt, per Claude
geparst, das Profilfoto extrahiert und via `crm.upsert_from_inbound`
deduplex angelegt oder aktualisiert.

---

## CRM-Lifecycle

```
┌───────────────┐   CV / Mail   ┌────────────────────┐
│ Inbound event │──────────────▶│ cv_parser (Claude) │
└───────────────┘               └──────────┬─────────┘
                                           │ parsed JSON
                                           ▼
                           ┌────────────────────────────────┐
                           │ crm.upsert_from_inbound(db, …) │
                           │  • lookup by email             │
                           │  • merge into existing profile │
                           │  • or create new if required   │
                           │    fields are present          │
                           └──────┬─────────────────────────┘
                                  │
              ┌───────────────────┼────────────────────────┐
              ▼                   ▼                        ▼
    ┌─────────────────┐  ┌────────────────┐  ┌───────────────────────┐
    │ append_message  │  │ follow-up mail │  │ match_processor       │
    │ (EmailLog row)  │  │ (missing info) │  │ (only if profile new  │
    └─────────────────┘  └────────────────┘  │  AND complete)        │
                                             └───────────────────────┘
```

Die Konfiguration der NOT-NULL Felder passiert primär in `.env`:

```env
CRM_REQUIRED_FIELDS=first_name,last_name,email,phone
```

…kann aber zur Laufzeit vom Recruiter in der **Settings-UI** überschrieben
werden. Die Überschreibung lebt in `runtime_config.json` innerhalb des
CV-Storage-Volumes und überlebt Container-Neustarts ohne DB-Migration. Die
nächste eingehende Bewerbung liest den neuen Wert sofort über einen
mtime-Cache.

---

## AI-Chat pro Kandidat

### System-Prompt
Für jede Session baut `app/api/chat.py` den System-Prompt aus:
- **Kandidatenprofil** (JSON)
- **Kurzprotokoll** (letzte 10 Mails + 5 Anrufe)
- **Tool-Spec**: `send_email` und `initiate_call`

Der Recruiter sagt im Chatfenster z.B. *"Schreib ihm eine kurze Mail und
frag nach seiner Gehaltsvorstellung"*. Claude antwortet mit einem JSON
Objekt:

```json
{
  "action": "send_email",
  "args": {"subject": "...", "body": "..."},
  "message": "Mail vorbereitet, sende jetzt."
}
```

Das Backend führt die Aktion aus, schreibt einen Protokoll-Eintrag und
gibt den gesamten Chat-Verlauf zurück.

### REST Endpoints

| Route                               | Beschreibung                                 |
|-------------------------------------|----------------------------------------------|
| `GET  /api/chat/{candidate_id}`     | Chat-History (ohne system / tool intern)     |
| `POST /api/chat/{candidate_id}`     | Neue Nachricht, führt tool automatisch aus   |

### UI — Mini-Chat-Dock
- Klick auf "AI Chat" in People-Tab oder Candidate-Detail öffnet ein
  Chat-Fenster.
- Es können so viele Fenster parallel offen sein, wie auf den Bildschirm
  passen (min 1, max 5 — `computeMaxVisible` in
  `ChatDockContext.tsx`).
- Jedes Fenster hat oben ein Mail- und ein Anruf-Icon für manuelle
  Actions und kann über die Titelleiste minimiert werden.

---

## Matching

Matches werden in `app/services/matching_engine.py` berechnet. Dimensionen:

| Dimension          | Gewicht |
|--------------------|--------:|
| Skills match       |    40 % |
| Erfahrung          |    20 % |
| Standort           |    15 % |
| Gehalt             |    15 % |
| Verfügbarkeit      |    10 % |

Neue Endpoints für's Ranking direkt aus der UI:

- `GET /api/jobs/{id}/candidates` — Kandidaten ranked für einen Job
- `GET /api/candidates/{id}/matching-jobs` — Jobs ranked für einen Kandidaten

---

## API-Übersicht (Auszug der neuen Routen)

| Route                                       | Beschreibung                         |
|---------------------------------------------|--------------------------------------|
| `GET  /api/candidates/`                     | Suche (name/email/phone/address)     |
| `POST /api/candidates/upload-cv`            | Manueller CV-Upload (läuft durch CRM)|
| `GET  /api/candidates/{id}/cv`              | CV-Datei streamen (PDF)              |
| `GET  /api/candidates/{id}/photo`           | Profilfoto streamen                  |
| `POST /api/candidates/{id}/photo`           | Foto manuell hochladen (Recruiter)   |
| `POST /api/candidates/{id}/extract-photo`   | Foto-Extraktion erneut anstossen     |
| `GET  /api/candidates/{id}/protocol`        | Vereinigtes Timeline                 |
| `GET  /api/candidates/{id}/matching-jobs`   | Job-Ranking für Kandidat             |
| `GET  /api/jobs/{id}/candidates`            | Kandidaten-Ranking für Job           |
| `GET  /api/messages/`                       | Neue Nachrichten (messages tab)      |
| `POST /api/messages/inbound`                | Webhook für externe Messages (Auth)  |
| `POST /api/messages/{id}/read`              | Gelesen/ungelesen togglen            |
| `GET  /api/chat/{candidate_id}`             | AI-Chat History                      |
| `POST /api/chat/{candidate_id}`             | Nachricht senden + Tool execution    |
| `GET  /api/settings/runtime`                | Runtime-Config (CRM Pflichtfelder)   |
| `PUT  /api/settings/runtime`                | Runtime-Config editieren             |
| `WS   /api/events/ws`                       | Live-Events Push (message.new, chat) |

OpenAPI docs: `http://localhost:8000/docs`

---

## Sicherheits-Hinweise

- `.env` enthält Secrets — niemals committen.
- Setze in Production **immer** `INBOUND_WEBHOOK_SECRET`. Ist die Variable
  leer, ist `POST /api/messages/inbound` offen — das ist nur für lokale
  Entwicklung gedacht. Externe Webapps müssen den Secret im Header
  `X-Webhook-Secret` mitschicken.
- Twilio Webhook-URLs müssen öffentlich erreichbar sein (z.B. ngrok).
- Chat-Tool-Ausführung läuft nur, wenn `auto_execute_tools=true` im Request —
  die Frontend-UI setzt das per default. Für einen Dry-Run-Modus kann es
  abgeschaltet werden.
- Alle ausgehenden API-Calls (Claude, Deepgram, ElevenLabs, Twilio, …) laufen
  in try/except mit strukturiertem Logging via `loguru`.

---

## Tests

Die Unit-Suite läuft ohne DB oder Docker — alles sind reine
Helper-Funktionen (CRM missing-field check, photo picker, webhook secret
guard, Runtime-Config roundtrips, Follow-up Mail Fallbacks in allen vier
Sprachen):

```bash
cd backend
uv run pytest tests/
```

Erwartete Ausgabe: **23 passed**.

---

## Lizenz

Proprietär.
