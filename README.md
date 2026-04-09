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

### Authentication (Argon2 + JWT Cookie)
- **Session Login** — `POST /api/auth/login` prüft Username + Passwort
  (Argon2-id, rehash-on-login), setzt ein HTTP-only Session-Cookie (JWT
  HS256) und liefert das User-Objekt zurück. `POST /api/auth/logout`
  löscht das Cookie, `GET /api/auth/me` gibt den aktuellen User.
- **Bootstrap-Admin** — beim ersten Startup prüft die App, ob die
  `users`-Tabelle leer ist; wenn ja, legt sie einen Admin aus
  `AUTH_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` an. Damit ist die erste
  Inbetriebnahme ein einzelner `docker compose up`-Schritt.
- **Protected Routes** — alle API-Router ausser `/api/auth` und
  `/api/webhooks` laufen hinter `Depends(current_user_dep)`. Im
  Frontend wrappt ein `ProtectedRoute`-Wrapper den kompletten Tree
  hinter einem `AuthProvider`-Context; ein Axios-Response-Interceptor
  wirft bei 401 direkt auf `/login` zurück.

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

### GDPR / Schweizer FADP
- **Einwilligung & Widerruf** — `consent_given_at` / `consent_source`
  werden auf dem Kandidaten-Record gepflegt; die UI zeigt einen
  "Einwilligung ausstehend"-Badge, solange kein Timestamp gesetzt ist.
- **Recht auf Vergessenwerden (Art. 17 DSGVO / Art. 32 DSG)** —
  `POST /api/candidates/{id}/anonymise` blankt alle PII (Name, Mail,
  Telefon, CV, Foto, Mails, Chat-Historie), lässt die Row-ID aber
  bestehen, damit Match-Historie & Statistiken nicht brechen.
- **Retention-Clock** — `retain_until` pro Kandidat plus ein
  Scheduled-Purge-Worker; Bulk-Actions und die LinkedIn-Proxycurl-Import
  Routen überspringen anonymisierte Kandidaten hart.

### Bulk Actions
- **CSV-Export** — `GET /api/candidates/bulk/export` (alle) oder
  `POST /api/candidates/bulk/export` (ausgewählte IDs) liefert eine
  per-`StreamingResponse` heruntergeladene CSV mit stabilen Spalten.
  Anonymisierte Kandidaten werden ausgefiltert.
- **Bulk-Mail** — `POST /api/candidates/bulk/email` sendet entweder
  eine per `template_id` gerenderte Mail oder ein ad-hoc `subject`/`body`
  an beliebig viele Kandidaten. Pro Versand entsteht ein `EmailLog`,
  sodass die Mail auch im Kandidaten-Protokoll auftaucht. Fehlgeschlagene
  Empfänger werden einzeln mit Grund zurückgegeben.
- **Multi-Select UI** — im People-Tab schaltet ein Toggle den
  Auswahl-Modus ein; eine Selection-Bar zeigt die Anzahl, "Alle auf
  dieser Seite", "Zurücksetzen", "CSV exportieren" und "E-Mail senden".

### Email-Templates
- **CRUD API** — `/api/templates/` mit Name, `language` (de/en/fr/it),
  Subject, Body und optionalem `is_signature`-Flag. Duplikate
  `(name, language)` geben 409 zurück.
- **Plain `{{placeholder}}`-Rendering** — `email_templates.render_for_candidate`
  ersetzt Platzhalter wie `{{first_name}}`, `{{skills}}`,
  `{{recent_jobs}}` ohne Jinja-Sandbox. Signature-Templates werden
  automatisch vor dem Body expandiert.
- **Editor** — zweispaltiges UI unter `/templates`: Liste links,
  Editor rechts mit Subject/Body, Sprache, Signature-Flag und einem
  Live-Preview-Button, der Beispiel-Platzhalter einsetzt.

### Reporting-Dashboard
- **Pipeline-Metriken** — `/api/reports/pipeline`, `/sources`, `/calls`,
  `/emails`, `/timeseries`, `/summary`.
- **KPI-Tiles + Pure-CSS Charts** — die `/reports`-Seite zeigt eine
  Day-Window-Auswahl (7/30/90/180/365), KPI-Kacheln und reine
  CSS-Bar- bzw. Inline-SVG-Sparkline-Visualisierungen; keine
  Charting-Library, kein Build-Overhead.

### Semantic Matching (Qdrant + BGE-M3)
- **Optionale Pre-Filter-Stage** — wenn `QDRANT_ENABLED=true`, bettet
  `vector_index.py` Kandidaten und Jobs mit `fastembed` + BGE-M3 ein
  und speichert die Vektoren in Qdrant. Der Matching-Engine verwendet
  die Top-K Nachbarn als Shortlist, bevor die deterministische +
  optionale Claude-Stage läuft.
- **Hybrid Ranking** — die Reihenfolge der Vector-Suche wird beibehalten,
  aber jedes Pair wird zusätzlich durch den explainable Skills/Experience/
  Location/Salary/Availability-Scorer geschickt.
- **Graceful Degradation** — fehlt die Qdrant-Verbindung, das
  Embedding-Modell oder die Python-Dependency, degradiert die Engine
  lautlos auf den Full-Scan-Pfad. Kein Boot-Break.
- **Reindex-Endpoint** — `POST /api/matches/reindex` baut den Index
  von Grund auf neu auf (z.B. nach Bulk-Imports).
- **GDPR-aware** — anonymisierte Kandidaten werden nie embedded und
  beim Index-Update proaktiv gelöscht.

### LinkedIn Proxycurl Import
- **Non-Destructive Merge** — `POST /api/candidates/{id}/import-linkedin`
  holt ein Public-Profile via `linkedin_scraper_api_key` (Proxycurl),
  normalisiert die Felder und füllt nur **leere** Felder auf dem
  Kandidaten. Skills und gesprochene Sprachen werden case-insensitive
  vereinigt.
- **Erfahrung & Timeline** — `work_history` und `education` werden
  aus den Proxycurl `experiences`/`education`-Listen aufgebaut,
  `experience_years` wird aus den Start-/End-Dates summiert.
- **UI** — Button "LinkedIn importieren" auf der Candidate-Detail-Seite,
  zeigt anschliessend die Liste der tatsächlich aktualisierten Felder.

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

### Matching & Voice
- Heuristisches Matching (Skills, Erfahrung, Ort, Salary, Verfügbarkeit)
  plus optionaler semantischer Pass durch Claude. Optionaler
  Qdrant+BGE-M3 Pre-Filter (siehe Abschnitt "Semantic Matching").
- Voice-Agent: Twilio Outbound Call → WebSocket Media Stream →
  Deepgram STT → Claude Konversation → ElevenLabs TTS. DE/EN/FR/IT mit
  automatischer Sprach-Erkennung (Heuristik + Claude-Fallback).
- **Call Recording** — jeder ausgehende Anruf startet mit `record=True`
  und `recording_channels="dual"`; Twilio postet nach Abschluss an
  `POST /api/webhooks/twilio/recording`, wir hängen `.mp3` an die URL
  und persistieren sie plus `duration_seconds` auf dem `CallLog`. Die
  Protokoll-UI rendert einen Inline-HTML5-`<audio>`-Player.
- **Manual Take-Over** — laufende Anrufe (`initiated`/`ringing`/
  `in_progress`) können mit dem "Anruf beenden"-Button aus dem
  Protokoll heraus abgebrochen werden; `POST /api/calls/{id}/hangup`
  ruft `client.calls(sid).update(status="completed")`, der reguläre
  Status-Callback liefert die finale Terminal-Statusübergabe.
- Post-Call Summary per Claude, Mail an Recruiter.

### UI
- **Login** — `/login` mit generischer Fehlermeldung, Avatar-Init +
  "Abmelden"-Button im "More"-Dropdown.
- Minimaler 3-Tab-Header (People · Messages · Jobs) + "More"-Dropdown
  für Overview/Matches/Calls/Emails/**Reports**/**Templates**/Settings.
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
  passender offener Stellen, vollständiges Protokoll mit Inline-
  Recording-Player und "Anruf beenden"-Button, GDPR-Actions
  (Einwilligung vermerken, Anonymisieren), "LinkedIn importieren"-
  Button, AI-Chat-Button.
- **Reports**: KPI-Kacheln, Pipeline-Funnel, Quellen-Mix,
  Anruf-Statistik, Mail-Volumen und eine Sparkline für neue
  Kandidaten pro Tag.
- **Templates**: Mail-Template-Editor mit Sprachwahl, Signature-Flag,
  Platzhalter-Referenzliste und Live-Preview.

---

## Architektur

```
recruiter-ai/
├── backend/                FastAPI + async SQLAlchemy + Alembic
│   └── app/
│       ├── api/            REST endpoints (auth, candidates, chat,
│       │                   messages, templates, reports, matches, …)
│       ├── models/         ORM (inkl. users, email_templates,
│       │                   chat_messages)
│       ├── schemas/        Pydantic schemas
│       ├── services/       Business logic
│       │   ├── auth.py                Argon2 + JWT cookie + bootstrap admin
│       │   ├── crm.py                 CRM upsert + CV storage + photo wiring
│       │   ├── cv_parser.py           Claude CV parser
│       │   ├── photo_extractor.py     CV → profile photo (PDF + DOCX)
│       │   ├── followup_mail.py       Personalised Claude follow-ups
│       │   ├── email_templates.py     {{placeholder}} renderer + preview
│       │   ├── matching_engine.py     Heuristik + Claude + Qdrant pre-filter
│       │   ├── vector_index.py        Qdrant + BGE-M3 (lazy, feature-flagged)
│       │   ├── linkedin_proxycurl.py  Proxycurl import + non-destructive merge
│       │   ├── gdpr.py                Anonymisation + retention purge
│       │   ├── voice_agent.py         Twilio + Deepgram + ElevenLabs
│       │   │                          (recording + hangup + objective)
│       │   └── ...
│       ├── entrypoint.sh   Wait-for-Postgres + alembic upgrade head + run app
│       ├── workers/        Background poller (Email, LinkedIn, Matching)
│       ├── utils/          Prompt templates (inkl. chat system prompt)
│       └── main.py
├── frontend/               React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── components/
│       │   ├── Layout.tsx              3-Tab Header + dropdown + logout
│       │   ├── LoginPage.tsx           /login form
│       │   ├── ProtectedRoute.tsx      Auth guard
│       │   ├── PeopleTab.tsx           Suche + Grid + Bulk-Select-Bar
│       │   ├── MessagesTab.tsx         Neue Nachrichten
│       │   ├── JobsTab.tsx             Jobs suchen
│       │   ├── CandidateDetail.tsx     Profil + CV + Protokoll + Audio +
│       │   │                           LinkedIn import + GDPR
│       │   ├── JobDetail.tsx           Description + Ranking-Button
│       │   ├── EmailTemplates.tsx      Template CRUD editor
│       │   ├── ReportingDashboard.tsx  KPIs + pure-CSS charts
│       │   ├── chat/
│       │   │   ├── ChatDockContext.tsx Fenster-State + max visible
│       │   │   ├── ChatDock.tsx        Fixed-bottom Dock
│       │   │   └── ChatWindow.tsx      Per-Kandidat Mini-Chat
│       │   └── shared/Avatar.tsx
│       ├── hooks/
│       │   ├── useApi.ts               Generic fetch + reload
│       │   └── useAuth.tsx             AuthProvider + 401 interceptor
│       ├── lib/api.ts                  Axios client (alle Endpoints)
│       └── types/                      Shared TypeScript types
├── docker-compose.yml      Postgres + Qdrant + backend + frontend +
│                           cv_storage + qdrant_data volumes
└── .env.example
```

---

## Quickstart

```bash
cp .env.example .env
# Pflicht:  POSTGRES_PASSWORD, ANTHROPIC_API_KEY
# Auth:     AUTH_JWT_SECRET (zwingend rotieren!)
#           AUTH_BOOTSTRAP_ADMIN_USERNAME, _PASSWORD, _EMAIL
# Optional: EMAIL_IMAP_*, SMTP, TWILIO_*, ELEVENLABS_*, DEEPGRAM_*,
#           INBOUND_WEBHOOK_SECRET (für Production),
#           LINKEDIN_SCRAPER_API_KEY (Proxycurl Import),
#           QDRANT_ENABLED=true (Semantic Matching)

make up
open http://localhost:3000
```

Der Backend-Container wartet beim Start auf Postgres und führt automatisch
`alembic upgrade head` aus — `make db-upgrade` ist nur für lokale
Iteration nötig. Beim ersten Boot prüft das Backend, ob die `users`-Tabelle
leer ist; wenn ja, wird aus den `AUTH_BOOTSTRAP_ADMIN_*`-Variablen ein
erster Admin angelegt. **Ändere das Passwort sofort im Anschluss.**

Nach dem Login öffnet sich direkt der **People**-Tab. CVs, die per Mail
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

### Optional: Semantic Pre-Filter (Qdrant + BGE-M3)

Wenn die Kandidaten-Datenbank wächst, ist die O(n) Scoring-Schleife nicht
mehr wirtschaftlich. Mit `QDRANT_ENABLED=true` kommt ein Vector-Index
davor:

```env
QDRANT_ENABLED=true
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=          # optional, nur für Qdrant Cloud
EMBEDDING_MODEL=BAAI/bge-m3
SEMANTIC_TOP_K=50
```

- `docker-compose.yml` bringt einen `qdrant/qdrant:v1.12.4`-Container
  plus persistentes `qdrant_data`-Volume mit.
- Beim ersten Zugriff initialisiert `vector_index.py` den Qdrant-Client,
  lädt das BGE-M3-Modell via `fastembed` und legt die Collections
  `recruiterai_candidates` / `recruiterai_jobs` an.
- `POST /api/matches/reindex` re-embed't alle (nicht anonymisierten)
  Kandidaten und offenen Jobs. Sinnvoll nach Bulk-Imports oder wenn
  man das Embedding-Modell wechselt.
- Wenn Qdrant unreachable ist oder `fastembed` nicht installiert ist,
  degradiert die Engine stumm auf den Full-Scan — der Flag ist
  reversibel ohne Code-Änderung.

---

## API-Übersicht (Auszug)

| Route                                             | Beschreibung                         |
|---------------------------------------------------|--------------------------------------|
| `POST /api/auth/login`                            | Session-Login (setzt JWT-Cookie)     |
| `POST /api/auth/logout`                           | Session beenden                      |
| `GET  /api/auth/me`                               | Aktuell eingeloggten User abrufen    |
| `GET  /api/candidates/`                           | Suche (name/email/phone/address)     |
| `POST /api/candidates/upload-cv`                  | Manueller CV-Upload (läuft durch CRM)|
| `GET  /api/candidates/{id}/cv`                    | CV-Datei streamen (PDF)              |
| `GET  /api/candidates/{id}/photo`                 | Profilfoto streamen                  |
| `POST /api/candidates/{id}/photo`                 | Foto manuell hochladen               |
| `POST /api/candidates/{id}/extract-photo`         | Foto-Extraktion erneut anstossen     |
| `GET  /api/candidates/{id}/protocol`              | Vereinigtes Timeline (inkl. recording_url) |
| `GET  /api/candidates/{id}/matching-jobs`         | Job-Ranking für Kandidat             |
| `POST /api/candidates/{id}/anonymise`             | GDPR right-to-be-forgotten           |
| `POST /api/candidates/{id}/consent`               | Einwilligung vermerken               |
| `POST /api/candidates/{id}/import-linkedin`       | Proxycurl Profil-Import              |
| `GET  /api/candidates/bulk/export`                | CSV aller Kandidaten                 |
| `POST /api/candidates/bulk/export`                | CSV ausgewählter IDs                 |
| `POST /api/candidates/bulk/email`                 | Bulk-Mail (Template oder ad-hoc)     |
| `GET  /api/jobs/{id}/candidates`                  | Kandidaten-Ranking für Job           |
| `GET  /api/messages/`                             | Neue Nachrichten (messages tab)      |
| `POST /api/messages/inbound`                      | Webhook für externe Messages (Auth)  |
| `POST /api/messages/{id}/read`                    | Gelesen/ungelesen togglen            |
| `GET  /api/chat/{candidate_id}`                   | AI-Chat History                      |
| `POST /api/chat/{candidate_id}`                   | Nachricht senden + Tool execution    |
| `GET/POST/PATCH/DELETE /api/templates/…`          | Mail-Template CRUD                   |
| `POST /api/templates/{id}/preview`                | Rendering mit Beispieldaten          |
| `GET  /api/reports/summary\|pipeline\|sources\|…` | Reporting-KPIs                       |
| `POST /api/matches/reindex`                       | Qdrant-Vector-Index neu aufbauen     |
| `POST /api/calls/{id}/hangup`                     | Laufenden Anruf manuell beenden      |
| `POST /api/webhooks/twilio/recording`             | Twilio Recording-Callback            |
| `GET  /api/settings/runtime`                      | Runtime-Config (CRM Pflichtfelder)   |
| `PUT  /api/settings/runtime`                      | Runtime-Config editieren             |
| `WS   /api/events/ws`                             | Live-Events Push (message.new, chat) |

Alle Routen ausser `/api/auth/*` und `/api/webhooks/*` sind hinter dem
Session-Cookie geschützt.

OpenAPI docs: `http://localhost:8000/docs`

---

## Sicherheits-Hinweise

- `.env` enthält Secrets — niemals committen.
- Setze in Production **immer** einen eigenen `AUTH_JWT_SECRET` und
  rotiere das Bootstrap-Admin-Passwort direkt nach dem ersten Login.
  Beim Start warnt das Backend ausdrücklich, wenn der Default-Placeholder
  noch aktiv ist.
- Setze in Production **immer** `INBOUND_WEBHOOK_SECRET`. Ist die Variable
  leer, ist `POST /api/messages/inbound` offen — das ist nur für lokale
  Entwicklung gedacht. Externe Webapps müssen den Secret im Header
  `X-Webhook-Secret` mitschicken.
- Twilio Webhook-URLs müssen öffentlich erreichbar sein (z.B. ngrok).
  Der Twilio Status- und Recording-Callback werden per Inbound-Webhook-
  Secret am Reverse-Proxy validiert.
- Bulk-Actions und der LinkedIn-Proxycurl-Importer überspringen
  anonymisierte Kandidaten hart — ein einmaliges "Recht auf
  Vergessenwerden" bleibt persistent und kann nicht aus Versehen durch
  einen Re-Import rückgängig gemacht werden.
- Chat-Tool-Ausführung läuft nur, wenn `auto_execute_tools=true` im Request —
  die Frontend-UI setzt das per default. Für einen Dry-Run-Modus kann es
  abgeschaltet werden.
- Alle ausgehenden API-Calls (Claude, Deepgram, ElevenLabs, Twilio,
  Qdrant, Proxycurl, …) laufen in try/except mit strukturiertem Logging
  via `loguru`.

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
