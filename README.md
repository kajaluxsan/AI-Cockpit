# RecruiterAI

**AI Recruiting Telephone Agent für Schweizer Personalvermittlungen.**

RecruiterAI empfängt Bewerbungen per E-Mail (und optional via LinkedIn oder einer
externen REST-API), parst CVs mit Claude, matched Kandidaten gegen offene Stellen,
führt automatische bilingue (DE/EN) Telefonate über Twilio + Deepgram +
ElevenLabs und liefert dem Recruiter strukturierte Zusammenfassungen.

---

## Features

- **Multi-Source Ingestion** — Email (IMAP / Microsoft Graph), LinkedIn,
  generische REST-API. Sources sind einzeln über `.env` an-/abschaltbar.
- **CV Parsing** mit Claude — extrahiert Skills, Erfahrung, Verfügbarkeit usw.
- **Automatische Follow-Up Mails** wenn Pflichtfelder fehlen.
- **Matching Engine** — heuristische Skill/Experience/Location/Salary/Availability
  Scores plus optional semantisches Matching durch Claude.
- **Voice Agent** — outbound Twilio-Anrufe, bidirektionaler Media Stream,
  Deepgram STT mit automatischer Sprachenerkennung, ElevenLabs TTS,
  Claude als Konversations-LLM, Post-Call Summary.
- **Recruiter Notifications** per Mail bei Matches und nach jedem Anruf.
- **React Dashboard** im "Swiss Precision"-Stil (dunkler Bloomberg/Linear-Hybrid).

---

## Architektur

```
recruiter-ai/
├── backend/                FastAPI + async SQLAlchemy + Alembic
│   └── app/
│       ├── api/            REST endpoints
│       ├── models/         SQLAlchemy ORM
│       ├── schemas/        Pydantic schemas
│       ├── services/       Business logic (Claude, Twilio, ElevenLabs, ...)
│       ├── workers/        Background pollers (Email, LinkedIn, Matching)
│       ├── utils/          Claude prompt templates
│       ├── config.py       Pydantic settings (source-aware validation)
│       ├── database.py     Async engine + session
│       └── main.py         FastAPI entrypoint
├── frontend/               React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── components/     Layout, Dashboard, lists, board, players, ...
│       ├── hooks/          useApi, useDashboardStats
│       ├── lib/api.ts      Axios client
│       └── types/          Shared TypeScript types
├── docker-compose.yml      Postgres + backend + frontend
├── Makefile                up / down / fresh / db-* / shell-*
└── .env.example            Vollständig dokumentierte Konfiguration
```

---

## Quickstart

```bash
# 1. Konfiguration
cp .env.example .env
# Trage mindestens diese Werte ein:
#   POSTGRES_PASSWORD
#   ANTHROPIC_API_KEY
#   EMAIL_IMAP_HOST + USER + PASSWORD  (falls SOURCE_EMAIL_ENABLED=true)
#   TWILIO_*  (für Anrufe)
#   ELEVENLABS_API_KEY + VOICE_IDs
#   DEEPGRAM_API_KEY

# 2. Start
make up

# 3. Datenbank-Migrationen
make db-upgrade

# 4. Logs anschauen
make logs

# 5. UI öffnen
open http://localhost:3000
# Backend Docs: http://localhost:8000/docs
```

### Häufige Make-Commands

| Command            | Was es tut                                              |
|--------------------|---------------------------------------------------------|
| `make up`          | Alle Services starten                                   |
| `make down`        | Stoppen, Volumes bleiben                                |
| `make down-clean`  | Stoppen UND Volumes löschen (DB wird gelöscht!)         |
| `make restart`     | Stop + Rebuild + Start                                  |
| `make reload`      | Schneller Neustart der Container ohne Rebuild           |
| `make fresh`       | Komplett neu: Volumes + Rebuild + Migrate               |
| `make logs`        | Logs aller Services                                     |
| `make logs-backend`| Nur Backend-Logs                                        |
| `make db-upgrade`  | Alembic Migrations laufen lassen                        |
| `make db-migrate MSG="..."` | Neue Migration generieren                       |
| `make db-shell`    | psql in der Postgres                                    |
| `make shell-backend` | Bash im Backend Container                             |

---

## Konfiguration über `.env`

Alle Settings stammen aus einer einzigen `.env`-Datei. Sources werden über
`SOURCE_*_ENABLED` Flags an- und abgeschaltet:

```env
SOURCE_EMAIL_ENABLED=true
SOURCE_LINKEDIN_ENABLED=false
SOURCE_EXTERNAL_API_ENABLED=false
```

**Wichtig:** Wenn eine Source deaktiviert ist, werden ihre zugehörigen Felder
auch nicht validiert — du kannst sie leer lassen. Wenn du sie aktivierst,
verlangt `Settings` beim Start die nötigen Pflichtfelder (siehe
`backend/app/config.py`).

Die generische REST-API ist mit jeder Kunden-Anwendung kompatibel: Auth-Methode
und alle Endpoint-Pfade sind über `.env` konfigurierbar
(`EXTERNAL_API_AUTH_TYPE`, `EXTERNAL_API_CANDIDATES_GET`, ...).

---

## Voice Agent Flow

```
1. Trigger:
   POST /api/calls/initiate { candidate_id, match_id? }
   → Twilio dialed candidate from configured number

2. On call connect Twilio fetches TwiML from:
   POST /api/webhooks/twilio/voice
   → Returns <Connect><Stream url="wss://.../api/webhooks/twilio/stream">

3. Twilio opens a WebSocket Media Stream with the backend.
   For each ~2s of caller audio:
     - Deepgram STT (with auto language detection DE/EN)
     - Claude generates a contextual reply (system prompt = job + candidate + agent identity)
     - ElevenLabs TTS (DE or EN voice depending on detected language)
     - Audio is streamed back into the Twilio Media Stream

4. After hangup, status callback hits:
   POST /api/webhooks/twilio/status
   → Call log status updated, Claude generates a recruiter summary,
     recruiter is notified by mail.
```

Der erste Satz des Agenten ist bilingue. Sobald die Sprache des Kandidaten
erkannt ist, wechselt die Konversation komplett in DE oder EN.

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

`MATCH_THRESHOLD_PERCENT` (default 80) bestimmt, ab welchem Score der Worker
automatisch Recruiter benachrichtigt und (wenn `MATCH_AUTO_CALL_ENABLED=true`)
einen Anruf auslöst. Wenn `ANTHROPIC_API_KEY` gesetzt ist, läuft zusätzlich
ein semantischer Pass durch Claude — z.B. erkennt er, dass "Spring Boot" zu
"Java Backend" passt.

---

## API Übersicht

| Route                                | Beschreibung                          |
|--------------------------------------|---------------------------------------|
| `GET  /api/dashboard/stats`          | KPIs für Dashboard                    |
| `GET  /api/dashboard/activity`       | Activity feed                         |
| `GET  /api/candidates/`              | Liste der Kandidaten (`status`, `q`)  |
| `POST /api/candidates/`              | Kandidat manuell erstellen            |
| `PATCH /api/candidates/{id}`         | Kandidat updaten                      |
| `GET  /api/jobs/`                    | Liste der Jobs                        |
| `POST /api/jobs/`                    | Job erstellen                         |
| `GET  /api/matches/`                 | Matches mit Filtern                   |
| `POST /api/matches/score/{c}/{j}`   | Score ad-hoc berechnen + Match anlegen|
| `GET  /api/calls/`                   | Call logs                             |
| `POST /api/calls/initiate`           | Anruf auslösen                        |
| `GET  /api/emails/`                  | Email-Log                             |
| `GET  /api/settings/`                | Read-only Konfigurations-Übersicht    |
| `POST /api/webhooks/twilio/voice`    | TwiML für Twilio Voice                |
| `POST /api/webhooks/twilio/status`   | Status-Callback                       |
| `WS   /api/webhooks/twilio/stream`   | Media Stream                          |

OpenAPI-Docs sind automatisch verfügbar unter
[`http://localhost:8000/docs`](http://localhost:8000/docs).

---

## Entwicklung

Backend nutzt **uv** (Astral) zum Verwalten der Python Dependencies. Im Container:

```bash
make shell-backend
uv sync
uv run uvicorn app.main:app --reload
```

Frontend ist eine reine Vite-App:

```bash
make shell-frontend
npm run dev
```

---

## Sicherheits-Hinweise

- `.env` enthält Secrets — niemals committen (`.gitignore` schließt sie aus).
- Twilio Webhook-URLs müssen öffentlich erreichbar sein (z.B. via ngrok während
  der Entwicklung). `TWILIO_WEBHOOK_BASE_URL` entsprechend setzen.
- Alle ausgehenden API Calls (Claude, Deepgram, ElevenLabs, LinkedIn, Twilio,
  externe REST-API) laufen in `try/except` mit strukturiertem Logging via
  `loguru`.

---

## Lizenz

Proprietär.
