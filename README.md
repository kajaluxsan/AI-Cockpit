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

### CRM-Kern (neu)
- **CRM Upsert on intake** — jede Mail/Nachricht wird per E-Mail-Adresse
  dedupliziert. Bestehende Profile werden in place aktualisiert, die
  Kommunikations-Historie (Protokoll) bleibt intakt.
- **NOT-NULL Pflichtfelder** (`CRM_REQUIRED_FIELDS`) — fehlt etwas, sendet die
  App automatisch eine Follow-up Mail und hält den Kandidaten im Status
  `info_requested` bis der CV vollständig ist.
- **Vereinigtes Protokoll** pro Kandidat: eingehende/ausgehende Mails, Anrufe
  und AI-Chat als Timeline (`GET /api/candidates/{id}/protocol`).
- **CV-Speicher** — der Original-CV wird als Datei persistiert und kann im
  UI direkt im PDF-Viewer geöffnet werden
  (`GET /api/candidates/{id}/cv`).
- **External Webhook** für Messages aus einer bestehenden Webapp
  (`POST /api/messages/inbound`).

### AI-Chat pro Kandidat (neu)
- Per-Kandidat Chat mit Claude: System-Prompt enthält CV + Protokoll, damit
  der Bot kontextbezogen antworten kann.
- **Tool-Aufrufe** aus dem Chat: `send_email(subject, body)` oder
  `initiate_call(reason)`. Der Recruiter gibt eine Anweisung in
  Umgangssprache, die App führt sie aus und loggt den Aufruf ins Protokoll.
- **Mini-Chat-Dock** unten rechts: bis zu 5 Kandidaten parallel, einzeln
  minimierbar.

### Matching & Voice (aus dem Original übernommen)
- Heuristisches Matching (Skills, Erfahrung, Ort, Salary, Verfügbarkeit)
  plus optionaler semantischer Pass durch Claude.
- Voice-Agent: Twilio Outbound Call → WebSocket Media Stream →
  Deepgram STT → Claude Konversation → ElevenLabs TTS. DE/EN automatisch.
- Post-Call Summary per Claude, Mail an Recruiter.

### UI
- Minimaler 3-Tab-Header (People · Messages · Jobs) + "More"-Dropdown
  für Overview/Matches/Calls/Emails/Settings.
- **People-Tab**: einzige Suchleiste matched auf Name, Mail, Telefon,
  Adresse. Grid mit Avatar, Name, Kontakt & Status, sortierbar nach
  zuletzt aktualisiert oder Nachname A–Z.
- **Messages-Tab**: eingehende Nachrichten (Mails und Webhook-Events)
  mit Lesen-Toggle.
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
│       │   ├── crm.py           CRM upsert + CV storage
│       │   ├── cv_parser.py     Claude CV parser
│       │   ├── matching_engine  Heuristik + Semantik (Claude)
│       │   ├── voice_agent.py   Twilio + Deepgram + ElevenLabs
│       │   └── ...
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
# Optional: EMAIL_IMAP_*, SMTP, TWILIO_*, ELEVENLABS_*, DEEPGRAM_*

make up
make db-upgrade
open http://localhost:3000
```

Nach dem Start öffnet sich direkt der **People**-Tab. CVs, die per Mail
einlaufen, werden automatisch von `EmailPoller` abgeholt, per Claude
geparst und via `crm.upsert_from_inbound` deduplex angelegt oder
aktualisiert.

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

Die Konfiguration der NOT-NULL Felder passiert in `.env`:

```env
CRM_REQUIRED_FIELDS=first_name,last_name,email,phone
```

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
| `GET  /api/candidates/{id}/protocol`        | Vereinigtes Timeline                 |
| `GET  /api/candidates/{id}/matching-jobs`   | Job-Ranking für Kandidat             |
| `GET  /api/jobs/{id}/candidates`            | Kandidaten-Ranking für Job           |
| `GET  /api/messages/`                       | Neue Nachrichten (messages tab)      |
| `POST /api/messages/inbound`                | Webhook für externe Messages         |
| `POST /api/messages/{id}/read`              | Gelesen/ungelesen togglen            |
| `GET  /api/chat/{candidate_id}`             | AI-Chat History                      |
| `POST /api/chat/{candidate_id}`             | Nachricht senden + Tool execution    |

OpenAPI docs: `http://localhost:8000/docs`

---

## Sicherheits-Hinweise

- `.env` enthält Secrets — niemals committen.
- Twilio Webhook-URLs müssen öffentlich erreichbar sein (z.B. ngrok).
- Chat-Tool-Ausführung läuft nur, wenn `auto_execute_tools=true` im Request —
  die Frontend-UI setzt das per default. Für einen Dry-Run-Modus kann es
  abgeschaltet werden.
- Alle ausgehenden API-Calls (Claude, Deepgram, ElevenLabs, Twilio, …) laufen
  in try/except mit strukturiertem Logging via `loguru`.

---

## Lizenz

Proprietär.
