# Signal — Autonomous Engineering Action Agent
## CLAUDE.md — Read this first before writing any code

---

## What We Are Building

Signal is an autonomous agent that listens to customer signals — emails and recorded
calls — and automatically takes engineering action across the company's toolstack
without any human in the loop.

A customer emails about a bug → Jira ticket created, Slack notified, roadmap updated.
A call recording is uploaded → transcribed, classified, cross-referenced against past
signals, actions taken, CEO digest updated.

Nobody manually triages. Nobody decides what to build. The agent does.

**Hackathon:** Multimodal Frontier Hackathon (Mar 28, 2026)
**Submission deadline:** 4:30 PM PT
**Demo:** 5:00 PM PT — 3 minutes
**Team:** 2 people

---

## Project Structure

```
signal-agent/
├── CLAUDE.md                        ← you are here, read before anything else
├── .env                             ← never commit, see env vars section below
├── backend/
│   ├── main.py                      ← FastAPI server, API routes, webhooks
│   ├── pipeline.py                  ← main Railtracks orchestration entry point
│   ├── agents/
│   │   ├── transcriber.py           ← audio transcription (Whisper API)
│   │   ├── classifier.py            ← classify signal type + extract entities
│   │   ├── memory.py                ← Senso search + ingest helpers
│   │   ├── router.py                ← decide which actions to take
│   │   └── digest.py                ← CEO weekly digest generator
│   ├── integrations/
│   │   ├── jira.py                  ← create/update Jira tickets
│   │   ├── notion.py                ← update Notion roadmap pages
│   │   ├── slack.py                 ← send Slack notifications
│   │   └── email_reply.py           ← draft customer reply emails
│   ├── auth/
│   │   └── unkey.py                 ← Unkey API key verification middleware
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── page.tsx                 ← main dashboard (two panel layout)
│   │   ├── api/
│   │   │   ├── chat/
│   │   │   │   └── route.ts         ← assistant-ui chat backend route
│   │   │   └── stream/
│   │   │       └── route.ts         ← SSE stream for live activity feed
│   │   └── components/
│   │       ├── ActivityFeed.tsx     ← right panel: live agent activity log
│   │       ├── SignalCard.tsx       ← individual signal/action card
│   │       ├── DigestPanel.tsx      ← CEO digest display
│   │       └── UploadZone.tsx       ← drag and drop call recording upload
│   ├── package.json
│   └── .env.local
└── README.md
```

---

## File Ownership — Do Not Cross These Lines

**Person 1 owns:**
- `backend/pipeline.py`
- `backend/agents/` (all files)
- `backend/integrations/` (all files)

**Person 2 owns:**
- `frontend/` (all files)
- `backend/main.py` (API routes and webhook receivers only)
- `backend/auth/unkey.py`

**Shared — communicate before touching:**
- `.env`
- `requirements.txt`
- `package.json`

**Git discipline:**
- Commit and push every 45 minutes minimum
- Always pull before starting a new task
- Format: `feat: [what you built]` or `fix: [what you fixed]`

---

## Person 2 — Backend Integration Instructions (updated Mar 28)

Person 1's backend is **fully complete**. All you need to do is wire `main.py` to call it.

### What exists in backend/ right now

```
backend/
├── pipeline.py              ← ENTRY POINT — call run_pipeline() from here
├── agents/
│   ├── transcriber.py       ← Whisper API (audio → text)
│   ├── classifier.py        ← GPT-4o (text → BUG/FEATURE_REQUEST/CHURN_RISK/PRAISE/QUESTION)
│   ├── memory.py            ← Senso CLI (search + ingest)
│   ├── router.py            ← routing rules (BUG→Jira, CHURN→Slack, etc.)
│   └── digest.py            ← CEO digest generator (call generate_digest())
├── integrations/
│   ├── jira.py              ← creates real Jira tickets
│   ├── notion.py            ← creates real Notion roadmap items
│   └── slack.py             ← sends real Slack alerts (also has send_test_message())
```

### Wiring pipeline.py into main.py

**POST /upload (audio file):**
```python
from pipeline import run_pipeline

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    import base64
    content = base64.b64encode(await file.read()).decode()
    await run_pipeline({"type": "audio", "content": content}, broadcast=broadcast)
    return {"ok": True}
```

**POST /webhook/email:**
```python
@app.post("/webhook/email")
async def email_webhook(payload: dict):
    body = payload.get("text") or payload.get("body") or str(payload)
    await run_pipeline({"type": "email", "content": body}, broadcast=broadcast)
    return {"ok": True}
```

**POST /monitor (manual demo trigger):**
```python
@app.post("/monitor")
async def monitor(payload: dict):
    await run_pipeline({
        "type": payload.get("type", "email"),
        "content": payload.get("content", ""),
    }, broadcast=broadcast)
    return {"ok": True}
```

**GET /digest:**
```python
from agents.digest import generate_digest

@app.get("/digest")
async def get_digest():
    return generate_digest()
```

### broadcast() — how it works

`run_pipeline` accepts a sync `broadcast(event: dict)` callback. Call it like this:

```python
def broadcast(event: dict):
    # push to your SSE queue here
    sse_queue.put_nowait(event)
```

Event shape:
```python
{
  "stage": "TRANSCRIBE"|"CLASSIFY"|"MEMORY"|"ROUTE"|"JIRA"|"NOTION"|"SLACK"|"SENSO"|"SYSTEM",
  "type": "info"|"success"|"warning"|"error",
  "message": "Ticket SCRUM-5 created",
  "meta": {"url": "...", "ticket_key": "SCRUM-5"}   # optional
}
```

### Turn off demo events once pipeline is wired
Add to `.env`:
```
DEMO_TEST_EVENTS=false
```

### Senso CLI — required on the server
The backend uses `@senso-ai/cli` for memory. Install it:
```bash
npm install -g @senso-ai/cli
```

### Test the pipeline standalone
```bash
cd backend
python3 pipeline.py 3   # runs all 3 signal types end-to-end
```

---

## Person 1 — Pull & Run Instructions (updated Mar 28)

After pulling, Person 1 needs to do the following on their machine:

### First time setup
```bash
git pull
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

### Run the backend
```bash
cd /path/to/signal
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

### Integrate the pipeline with the activity feed

`main.py` already handles `/upload`, `/webhook/email`, and `/monitor`. It will automatically
call your pipeline once `backend/pipeline.py` exists. All you need:

**1. Define `run_pipeline` in `backend/pipeline.py`:**
```python
async def run_pipeline(input: dict, broadcast=None) -> None:
    # input: {"type": "audio"|"email", "content": bytes|str, ...}
    # call broadcast() at each stage to stream events to the frontend feed
    ...
```

**2. Call `broadcast` at each pipeline stage to stream live events:**
```python
# broadcast signature — call it anywhere in your pipeline
broadcast({"stage": "TRANSCRIBE", "type": "info",    "message": "Transcribing audio…"})
broadcast({"stage": "CLASSIFY",   "type": "success", "message": "BUG detected, urgency 8",
           "meta": {"customer": "Jane", "company": "Acme"}})
broadcast({"stage": "JIRA",       "type": "success", "message": "Ticket ENG-42 created",
           "meta": {"url": "https://yourco.atlassian.net/browse/ENG-42"}})
```

Valid `stage` values (each has its own color in the UI):
`TRANSCRIBE` `CLASSIFY` `MEMORY` `ROUTE` `JIRA` `NOTION` `SLACK` `DIGEST` `SYSTEM`

Valid `type` values: `info` `success` `warning` `error`

**3. Once your pipeline is wired, turn off demo events** — add to `.env`:
```
DEMO_TEST_EVENTS=false
```

### .env — copy from teammate, never commit
The `.env` file is gitignored. Get a copy from Person 2 with the real API keys filled in.
Required keys: `OPENAI_API_KEY`, `SENSO_API_KEY`, `JIRA_API_TOKEN`, `NOTION_API_KEY`,
`SLACK_WEBHOOK_URL`.

---

## The Core Pipeline

```
TRIGGER
  Email received (webhook) OR call recording uploaded (POST /upload)
        │
        ▼
STAGE 1 — TRANSCRIBE + UNDERSTAND
  - If audio: transcribe with Whisper API
  - If email: parse raw text
  - Extract: customer name, company, sentiment, key phrases
  - Classify: BUG | FEATURE_REQUEST | CHURN_RISK | PRAISE | QUESTION
  - Assign urgency score 1-10
        │
        ▼
STAGE 2 — MEMORY LOOKUP (Senso)
  - Search Senso KB for similar past signals
  - Count: how many other customers said something similar?
  - Retrieve: what actions were taken last time?
  - Calculate: frequency score
        │
        ▼
STAGE 3 — ROUTING DECISION
  - BUG + urgency >= 7 OR frequency >= 3: create Jira P1, ping Slack #engineering
  - BUG + urgency < 7: create Jira P2, no Slack
  - FEATURE_REQUEST + frequency >= 5: update Notion roadmap, Slack #product
  - FEATURE_REQUEST + frequency < 5: log to Senso only
  - CHURN_RISK: Slack #cs-team immediately, draft reply email, flag for CEO digest
  - PRAISE: log to Senso, add to CEO digest only
        │
        ▼
STAGE 4 — EXECUTE ACTIONS
  - Jira: create ticket with full context and customer quotes
  - Notion: update roadmap page priority or add new item
  - Slack: send formatted message to correct channel
  - Email: draft reply to customer
  - Senso: store this signal + actions taken for future memory
        │
        ▼
STAGE 5 — LOG + STREAM
  - Write action log entry to database
  - Stream event via SSE to frontend activity feed
  - Append to CEO digest
```

---

## Sponsor Tools — Exact Usage

### Railtracks — Agent Orchestration
Every stage is a Railtracks agent node. Do not use raw LLM calls for orchestration.
Railtracks IS the pipeline.

```python
import railtracks as rt

@rt.function_node
async def transcribe_and_classify(input: dict) -> dict:
    """
    Input: { "type": "audio"|"email", "content": bytes|str }
    Output: {
        "text": str,
        "classification": "BUG"|"FEATURE_REQUEST"|"CHURN_RISK"|"PRAISE"|"QUESTION",
        "urgency": int,  # 1-10
        "customer": str,
        "company": str,
        "key_phrases": list[str],
        "sentiment": "positive"|"negative"|"neutral"
    }
    """
    ...

@rt.function_node
async def search_memory(classification_result: dict) -> dict:
    """Search Senso for similar past signals. Returns frequency + related actions."""
    ...

@rt.function_node
async def decide_actions(memory_result: dict) -> list[dict]:
    """
    Returns list of actions.
    Each: { "type": "jira"|"notion"|"slack"|"email", "payload": {} }
    """
    ...

@rt.function_node
async def execute_actions(actions: list[dict]) -> list[dict]:
    """Execute each action against real APIs. Return results with URLs."""
    ...

@rt.function_node
async def update_digest(signal: dict, actions: list[dict]) -> None:
    """Append signal + actions to CEO digest in Senso."""
    ...

signal_pipeline = rt.agent_node(
    "Signal Processor",
    tool_nodes=(
        transcribe_and_classify,
        search_memory,
        decide_actions,
        execute_actions,
        update_digest
    ),
    llm=rt.llm.OpenAILLM("gpt-4o"),
    system_message="""You are an autonomous engineering operations agent.
    Process customer signals (emails and call recordings) and take
    appropriate engineering actions without human intervention.

    Classification rules:
    - BUG: customer reports something broken or not working as expected
    - FEATURE_REQUEST: customer asks for something new or different
    - CHURN_RISK: customer expresses frustration or mentions cancelling
    - PRAISE: customer expresses satisfaction
    - QUESTION: customer needs information or clarification

    Always err toward taking action rather than waiting.
    Multiple customers reporting the same thing means higher priority.
    Churn risk always gets immediate Slack notification.
    Never hallucinate customer names, company names, or technical details.
    Only use information from the actual signal content."""
)
```

### Senso.ai — Memory and Knowledge Layer
Install skills first:
```bash
npx @senso-ai/shipables install senso-ai/senso-ingest
npx @senso-ai/shipables install senso-ai/senso-search
```

Three types of content stored in Senso:

**1. Customer signals**
```python
# backend/agents/memory.py
import requests, os

SENSO_API = "https://api.senso.ai"
HEADERS = {"Authorization": f"Bearer {os.environ['SENSO_API_KEY']}"}

async def ingest_signal(signal: dict) -> str:
    content = f"""
Customer: {signal['customer']} at {signal['company']}
Type: {signal['classification']}
Urgency: {signal['urgency']}/10
Summary: {signal['text'][:500]}
Key phrases: {', '.join(signal['key_phrases'])}
Actions taken: {signal.get('actions_summary', 'none')}
    """
    r = requests.post(f"{SENSO_API}/content", headers=HEADERS, json={
        "text": content,
        "metadata": {
            "type": "customer_signal",
            "classification": signal['classification'],
            "company": signal['company'],
            "urgency": signal['urgency']
        }
    })
    return r.json()["id"]

async def search_similar_signals(key_phrases: list[str], classification: str) -> dict:
    query = f"{classification}: {' '.join(key_phrases[:3])}"
    r = requests.get(f"{SENSO_API}/search", headers=HEADERS,
        params={"query": query, "limit": 10})
    results = r.json()["results"]
    return {
        "frequency": len(results),
        "related_signals": results
    }
```

**2. CEO digest** — appended to throughout the day, retrieved on GET /digest

**3. Roadmap state** — synced when Notion updates happen

### Jira Integration
```python
# backend/integrations/jira.py
import requests
from base64 import b64encode
import os

def create_ticket(summary: str, description: str, priority: str,
                  issue_type: str, customer_quote: str) -> dict:
    auth = b64encode(
        f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
    ).decode()
    r = requests.post(
        f"{os.environ['JIRA_BASE_URL']}/rest/api/3/issue",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"fields": {
            "project": {"key": os.environ['JIRA_PROJECT_KEY']},
            "summary": summary,
            "description": {"type": "doc", "version": 1, "content": [{
                "type": "paragraph",
                "content": [{"type": "text",
                    "text": f'Customer said: "{customer_quote}"\n\n{description}'}]
            }]},
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
            "labels": ["signal-agent"]
        }}
    )
    result = r.json()
    return {
        "ticket_key": result["key"],
        "url": f"{os.environ['JIRA_BASE_URL']}/browse/{result['key']}"
    }
```

### Slack Integration
```python
# backend/integrations/slack.py
import requests, os

def send_alert(channel_env_key: str, signal: dict, actions: list) -> None:
    requests.post(os.environ['SLACK_WEBHOOK_URL'], json={
        "text": f"Signal Agent: *{signal['classification']}* detected",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text":
                f"*{signal['classification']}* from {signal['customer']} "
                f"at {signal['company']}\n"
                f"Urgency: {signal['urgency']}/10\n"
                f"_{signal['text'][:200]}..._"
            }},
            {"type": "section", "text": {"type": "mrkdwn", "text":
                "*Actions taken automatically:*\n" +
                "\n".join([f"• {a}" for a in actions])
            }}
        ]
    })
```

### Notion Integration
```python
# backend/integrations/notion.py
from notion_client import Client
import os

notion = Client(auth=os.environ["NOTION_API_KEY"])

def create_roadmap_item(title: str, description: str,
                        priority: str, signal_count: int) -> str:
    page = notion.pages.create(
        parent={"database_id": os.environ["NOTION_ROADMAP_DB_ID"]},
        properties={
            "Name": {"title": [{"text": {"content": title}}]},
            "Priority": {"select": {"name": priority}},
            "Status": {"select": {"name": "Considering"}},
            "Signal Count": {"number": signal_count},
            "Source": {"select": {"name": "Signal Agent"}}
        }
    )
    return page["url"]
```

### assistant-ui — Dashboard
```bash
npx assistant-ui create frontend
cd frontend && npm install
```

Two panel layout:
- **Left:** Chat — CEO asks natural language questions about customer signals,
  answered from Senso knowledge base
- **Right:** Live activity feed — SSE stream showing each agent action as it fires

```typescript
// frontend/app/api/stream/route.ts
// SSE endpoint streaming activity log to frontend in real time
export async function GET() {
  const stream = new ReadableStream({ ... })
  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream" }
  })
}
```

### Unkey — API Auth (do this last, 20 minutes)
```python
# backend/auth/unkey.py
from unkey import Unkey
from fastapi import Header, HTTPException
import os

unkey_client = Unkey(root_key=os.environ["UNKEY_ROOT_KEY"])

async def verify_api_key(x_api_key: str = Header(...)):
    result = await unkey_client.keys.verify({"key": x_api_key})
    if not result.valid:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return result
```

### DigitalOcean — Deployment
Use App Platform, not raw droplets.
1. Push code to GitHub
2. App Platform → New App → connect repo
3. Set all env vars in the dashboard
4. Deploy (3-4 minutes)
5. Get live public URL

---

## Environment Variables

```bash
# .env — NEVER COMMIT THIS FILE

OPENAI_API_KEY=sk-...

SENSO_API_KEY=...
SENSO_KB_ID=...

JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=...
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_PROJECT_KEY=ENG

NOTION_API_KEY=secret_...
NOTION_ROADMAP_DB_ID=...

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

UNKEY_ROOT_KEY=...
UNKEY_API_ID=...
```

---

## Signal Classification + Routing Rules

| Classification | Triggers | Jira | Notion | Slack | Digest |
|---|---|---|---|---|---|
| BUG (urgency >= 7) | broken, crash, error | P1 Bug | — | #engineering | yes |
| BUG (urgency < 7) | not working, fails | P2 Bug | — | — | yes |
| FEATURE_REQUEST (freq >= 5) | wish, need, add | Story | update priority | #product | yes |
| FEATURE_REQUEST (freq < 5) | would love, missing | — | — | — | yes |
| CHURN_RISK | cancel, leaving, switching | — | — | #cs-team immediately | yes |
| PRAISE | love, amazing, great | — | — | — | yes |
| QUESTION | how do I, can I | — | — | — | no |

Frequency multiplier: 3-4 customers = urgency +2, 5+ customers = urgency +4

---

## API Routes

```
POST /webhook/email     Inbound email webhook (SendGrid/Mailgun)
POST /upload            Audio file upload (multipart/form-data)
POST /monitor           Manual trigger for demo use
GET  /alerts/stream     SSE stream of agent activity
GET  /digest            Current CEO digest
GET  /signals           All processed signals
GET  /health            Health check
```

---

## Build Order

### Hour 1: 11:00am — 12:00pm

**Person 1:**
- `pip install railtracks openai requests notion-client`
- Build `transcriber.py` — Whisper API with test audio file
- Build `classifier.py` — returns classification dict from transcript
- Wire into Railtracks pipeline in `pipeline.py`
- Test with hardcoded fake transcript
- **Goal:** pipeline classifies a fake transcript correctly

**Person 2:**
- `npx assistant-ui create frontend`
- Get two-panel layout running at localhost:3000
- Build `slack.py` — send one real test message to Slack
- **Goal:** Slack message appears in real channel (proves real action early)

### Hour 2: 12:00pm — 1:00pm

**Person 1:**
- Build `memory.py` — ingest to Senso, search back
- Build `jira.py` — create one real Jira ticket from test data
- Build `notion.py` — create one real Notion page from test data
- Wire: transcribe → classify → Senso → Jira
- **Goal:** fake transcript creates real Jira ticket end to end

**Person 2:**
- Build `main.py` with `/upload` and `/alerts/stream` routes
- Build SSE that streams test events every 5 seconds
- Connect `ActivityFeed.tsx` to SSE stream
- **Goal:** frontend shows live events from backend

### Hour 3: 1:30pm — 2:30pm

**Person 1:**
- Build `router.py` with full routing table above
- Connect full pipeline: transcribe → classify → Senso → route → Jira + Notion + Slack
- Test with 3 different signal types
- **Goal:** one audio file in → Jira + Slack + Senso out

**Person 2:**
- Wire `/upload` to Person 1's pipeline
- Build `UploadZone.tsx` — drag and drop audio
- Connect chat to Senso search
- Build `DigestPanel.tsx`
- **Goal:** full end to end visible in UI

### Hour 4: 2:30pm — 3:30pm

**Person 1:**
- Build `digest.py` — generate CEO summary from Senso
- Add Unkey auth to all routes
- **Goal:** /digest returns real formatted summary

**Person 2:**
- Push to GitHub, deploy on DigitalOcean App Platform
- Test live URL
- Fix worst visual bug
- **Goal:** live public URL, everything works

### Hour 5: 3:30pm — 4:30pm — DEMO PREP ONLY
- Stop adding features
- Run demo 3 times out loud, timed
- Prepare cached backup results
- Write Devpost submission
- Publish to Shipables

---

## The 3-Minute Demo Script

**Before going on stage:**
1. Have a 30-second fake customer call recording ready
2. Jira project open in browser tab
3. Slack channel open in another tab
4. Signal dashboard open in third tab
5. CEO digest pre-generated

**0:00 — 0:20: Hook**
"Every week PMs spend hours listening to calls, reading emails, deciding what to build.
Engineers wait. Roadmaps go stale. We built Signal — an agent that turns customer
signals into engineering action automatically."

**0:20 — 1:00: Trigger**
"I'm uploading a real customer call right now."
→ Drag audio into upload zone
→ Show activity feed firing: transcribing... classifying... searching history...
→ "It found 4 other customers reported the same thing this month."

**1:00 — 2:00: The actions**
→ Switch to Jira — real ticket just appeared, created by the agent
→ Switch to Slack — real message in #engineering
→ Switch back — Notion roadmap item promoted to P1
"Three real engineering actions. Zero human input. 45 seconds."

**2:00 — 2:30: The intelligence**
→ Show CEO digest
"The CEO got this this morning. 12 customers mentioned export bugs.
3 are churn risks. Top requested feature has 8 signals.
No meeting required. The agent tracked all of it."

**2:30 — 3:00: Business case**
"You could hire a full-time ops person for $80,000 a year to do this manually.
Signal costs $299 a month. Every company with customers and an engineering
team needs this. That is every company."

---

## Backup Plans

**If audio transcription is slow:** Pre-transcribe the demo audio. POST the text
directly to `/monitor` skipping transcription. Pipeline still runs fully.

**If Jira fails:** Lead with Slack message. Equally real. Explain Jira is one
of multiple action targets.

**If DigitalOcean fails:** Demo from localhost with ngrok:
```bash
ngrok http 8080
```

**If everything breaks:** Show the pre-generated CEO digest. Walk through what
the agent found and what actions it took. The intelligence is compelling on its own.

---

## Shipables Publication (Required)

Create `SKILL.md` in project root:

```markdown
# Signal — Autonomous Engineering Action Agent

Processes customer signals (emails, call recordings) and takes autonomous
engineering action across Jira, Notion, and Slack without human intervention.

## When to use
- Process a customer call recording or email automatically
- Create Jira tickets from customer feedback
- Update product roadmap based on customer signals
- Generate CEO digest of customer feedback trends

## Inputs
- Audio file (call recording)
- Email webhook payload

## Outputs
- Jira ticket (bugs and high-frequency feature requests)
- Notion roadmap update (feature requests with 3+ signals)
- Slack notification (routed by signal type)
- CEO digest entry

## Required env vars
OPENAI_API_KEY, SENSO_API_KEY, JIRA_API_TOKEN,
NOTION_API_KEY, SLACK_WEBHOOK_URL, UNKEY_ROOT_KEY
```

```bash
npx @senso-ai/shipables publish
```

---

## Definition of Done (4:30pm Checklist)

- [ ] Audio upload triggers full pipeline end to end
- [ ] Real Jira ticket created by agent (not manually)
- [ ] Real Slack message sent by agent (not manually)
- [ ] Notion roadmap updated by agent (not manually)
- [ ] Senso stores every processed signal
- [ ] CEO digest generates from real stored signals
- [ ] Frontend shows live activity feed via SSE
- [ ] Frontend chat answers questions about customer signals
- [ ] Live public URL on DigitalOcean
- [ ] Unkey auth on all routes
- [ ] Demo rehearsed 3 times, fits in 3 minutes
- [ ] Devpost submitted
- [ ] Published to Shipables

If all boxes are checked at 4:00pm, you are winning this hackathon.
