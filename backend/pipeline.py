"""
pipeline.py — Main Railtracks orchestration entry point
Full pipeline: transcribe → classify → memory search → route → execute → ingest

Person 2 interface: run_pipeline(input: dict, broadcast=None)
Internal interface: process_signal(signal_type, content, stream_callback=None)
"""

import asyncio
import os
import sys
import railtracks as rt

from agents.transcriber import transcribe, TranscribeInput
from agents.classifier import classify, ClassifyInput, ClassifyOutput
from agents.memory import ingest_signal, search_memory, IngestInput, SearchInput
from agents.router import decide_actions, RouterInput, RouterOutput
from integrations.jira import create_jira_ticket, JiraTicketInput
from integrations.notion import create_roadmap_item, NotionRoadmapInput
from integrations.slack import send_slack_alert, SlackAlertInput


# ---------------------------------------------------------------------------
# Railtracks agent node (for LLM-orchestrated runs)
# ---------------------------------------------------------------------------

signal_pipeline = rt.agent_node(
    "Signal Processor",
    tool_nodes=(transcribe, classify, search_memory, decide_actions,
                create_jira_ticket, create_roadmap_item, send_slack_alert, ingest_signal),
    llm=rt.llm.OpenAILLM("gpt-4o"),
    system_message="""You are an autonomous engineering operations agent.
Process customer signals and take appropriate engineering actions without human intervention.

Steps:
1. transcribe() — get text from audio or email
2. classify() — classify signal type, urgency, entities
3. search_memory() — find similar past signals (frequency)
4. decide_actions() — determine what actions to take based on routing rules
5. Execute each action: create_jira_ticket(), create_roadmap_item(), send_slack_alert()
6. ingest_signal() — store signal + actions in Senso memory

Never hallucinate customer names, company names, or technical details.""",
)


# ---------------------------------------------------------------------------
# Person 2 interface — called from main.py
# ---------------------------------------------------------------------------

async def run_pipeline(input: dict, broadcast=None) -> None:
    """
    Main entry point for main.py.

    Args:
        input: {"type": "audio"|"email", "content": bytes|str, ...}
        broadcast: optional sync fn(event: dict) to stream events to frontend

    broadcast event shape:
        {"stage": "TRANSCRIBE"|"CLASSIFY"|"MEMORY"|"ROUTE"|"JIRA"|"NOTION"|"SLACK"|"SENSO"|"SYSTEM",
         "type": "info"|"success"|"warning"|"error",
         "message": str,
         "meta": {}}   # optional
    """
    def emit(stage: str, msg: str, kind: str = "info", meta: dict = None):
        if broadcast:
            broadcast({"stage": stage, "type": kind, "message": msg,
                       "meta": meta or {}})

    signal_type = input.get("type", "email")
    content = input.get("content", "")
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")

    await process_signal(
        signal_type=signal_type,
        content=content,
        stream_callback=_make_broadcast_adapter(broadcast),
        sender_email=input.get("sender_email", ""),
    )


def _make_broadcast_adapter(broadcast):
    """Convert our async stream_callback signature to Person 2's sync broadcast."""
    if broadcast is None:
        return None

    async def adapter(event: dict):
        # Map our stage names to Person 2's uppercase stage names
        stage_map = {
            "transcribe": "TRANSCRIBE",
            "classify": "CLASSIFY",
            "memory": "MEMORY",
            "route": "ROUTE",
            "jira": "JIRA",
            "notion": "NOTION",
            "slack": "SLACK",
            "senso": "SENSO",
        }
        stage = stage_map.get(event.get("stage", ""), "SYSTEM")
        broadcast({
            "stage": stage,
            "type": event.get("type", "info"),
            "message": event.get("message", ""),
            "meta": event.get("meta", {}),
        })

    return adapter


# ---------------------------------------------------------------------------
# Core pipeline — internal
# ---------------------------------------------------------------------------

async def process_signal(signal_type: str, content: str,
                         stream_callback=None,
                         sender_email: str = "") -> dict:
    """
    Full pipeline: transcribe → classify → memory → route → execute → ingest.

    Args:
        signal_type: "audio" | "email"
        content: raw text (email) or base64-encoded audio bytes
        stream_callback: optional async fn(event: dict) for SSE streaming

    Returns:
        dict with classification_result, memory_result, actions_taken
    """
    async def emit(stage: str, message: str, kind: str = "info", meta: dict = None):
        event = {"stage": stage, "type": kind, "message": message, "meta": meta or {}}
        if stream_callback:
            await stream_callback(event)
        else:
            print(f"  [{stage.upper()}] {message}")

    # Stage 1: Transcribe + Classify
    # Use Gemini multimodal if key is set (single call for audio),
    # otherwise fall back to Whisper + GPT-4o (two calls)
    use_gemini = bool(os.environ.get("GEMINI_API_KEY"))

    if use_gemini:
        model_label = "Gemini 2.5 Flash (multimodal)"
        await emit("transcribe", f"Processing with {model_label}...")
        from agents.gemini_processor import gemini_process, GeminiInput
        gemini_result = await gemini_process(GeminiInput(
            signal_type=signal_type,
            content=content,
        ))
        text = gemini_result.text
        # Wrap as ClassifyOutput-compatible object
        from agents.classifier import ClassifyOutput
        classification = ClassifyOutput(
            text=gemini_result.text,
            classification=gemini_result.classification,
            urgency=gemini_result.urgency,
            customer=gemini_result.customer,
            company=gemini_result.company,
            key_phrases=gemini_result.key_phrases,
            sentiment=gemini_result.sentiment,
        )
        await emit("transcribe", f"Transcribed ({len(text)} chars)", "success")
    else:
        model_label = "Whisper + GPT-4o"
        await emit("transcribe", f"Transcribing with {model_label}...")
        if signal_type == "audio":
            import base64
            from agents.transcriber import transcribe_audio_bytes
            audio_bytes = base64.b64decode(content)
            text = transcribe_audio_bytes(audio_bytes)
        else:
            text = content
        await emit("transcribe", f"Transcribed ({len(text)} chars)", "success")

        await emit("classify", "Classifying signal...")
        classification = await classify(ClassifyInput(text=text))

    await emit("classify",
               f"Classified as {classification.classification} "
               f"(urgency {classification.urgency}/10) — "
               f"{classification.customer} @ {classification.company}",
               "success",
               {"customer": classification.customer, "company": classification.company,
                "classification": classification.classification, "urgency": classification.urgency})

    # Stage 2: Memory search
    await emit("memory", "Searching memory for similar signals...")
    memory_result = await search_memory(SearchInput(
        key_phrases=classification.key_phrases,
        classification=classification.classification,
    ))
    frequency = memory_result.frequency
    await emit("memory", f"Found {frequency} similar past signals", "success")

    # Stage 3: Route
    await emit("route", "Deciding actions...")
    routing: RouterOutput = await decide_actions(RouterInput(
        classification=classification.classification,
        urgency=classification.urgency,
        customer=classification.customer,
        company=classification.company,
        text=text,
        key_phrases=classification.key_phrases,
        sentiment=classification.sentiment,
        frequency=frequency,
        sender_email=sender_email,
    ))
    action_types = [a.type for a in routing.actions]
    await emit("route",
               f"Actions queued: {', '.join(action_types)} "
               f"(effective urgency {routing.effective_urgency}/10)",
               "info")

    # Stage 4: Execute actions
    actions_taken = []
    action_labels = []

    for action in routing.actions:
        if action.type == "jira":
            await emit("jira", "Creating Jira ticket...")
            try:
                p = action.payload
                ticket = await create_jira_ticket(JiraTicketInput(
                    summary=p["summary"],
                    description=p["description"],
                    priority=p["priority"],
                    issue_type=p["issue_type"],
                    customer_quote=p["customer_quote"],
                ))
                actions_taken.append({"type": "jira", "ticket_key": ticket.ticket_key, "url": ticket.url})
                action_labels.append(f"Jira {ticket.ticket_key} ({p['priority']}): {ticket.url}")
                await emit("jira", f"Ticket {ticket.ticket_key} created — {ticket.url}",
                           "success", {"ticket_key": ticket.ticket_key, "url": ticket.url})
            except Exception as e:
                await emit("jira", f"Failed: {e}", "error")

        elif action.type == "notion":
            await emit("notion", "Updating Notion roadmap...")
            try:
                p = action.payload
                page = await create_roadmap_item(NotionRoadmapInput(
                    title=p["title"],
                    description=p["description"],
                    priority=p["priority"],
                    signal_count=p["signal_count"],
                ))
                actions_taken.append({"type": "notion", "page_id": page.page_id, "url": page.url})
                action_labels.append(f"Notion roadmap item: {page.url}")
                await emit("notion", f"Roadmap item created — {page.url}",
                           "success", {"url": page.url})
            except Exception as e:
                await emit("notion", f"Failed: {e}", "error")

        elif action.type == "slack":
            channel = action.payload.get("channel_hint", "#engineering")
            await emit("slack", f"Sending alert to {channel}...")
            result = await send_slack_alert(SlackAlertInput(
                channel_hint=channel,
                classification=classification.classification,
                urgency=routing.effective_urgency,
                customer=classification.customer,
                company=classification.company,
                text=text,
                actions_taken=action_labels,
            ))
            actions_taken.append({"type": "slack", "channel": channel, "ok": result.ok})
            await emit("slack",
                       f"Alert sent to {channel}" if result.ok else "Slack failed",
                       "success" if result.ok else "error")

        elif action.type == "email_reply":
            to_address = action.payload.get("to_address", "")
            await emit("system", f"Drafting and sending reply email{' to ' + to_address if to_address else ''}...")
            try:
                from integrations.email_reply import generate_and_send_reply
                result_email = await generate_and_send_reply(
                    classification_result=classification.model_dump() | {"text": text},
                    to_address=to_address or os.environ.get("GMAIL_USER", ""),
                    actions_taken="; ".join(action_labels),
                )
                actions_taken.append({
                    "type": "email_reply",
                    "subject": result_email["subject"],
                    "body": result_email["body"],
                    "to": result_email["to_address"],
                    "sent": result_email["sent"],
                })
                status = "sent" if result_email["sent"] else "drafted (not sent)"
                await emit("system",
                           f"Reply {status} to {result_email['to_name']} — \"{result_email['subject']}\"",
                           "success" if result_email["sent"] else "warning",
                           {"subject": result_email["subject"], "body": result_email["body"],
                            "sent": result_email["sent"]})
            except Exception as e:
                await emit("system", f"Email reply failed: {e}", "error")

        elif action.type == "digest":
            actions_taken.append({"type": "digest"})

    # Stage 5: Ingest to Senso
    await emit("senso", "Storing signal in memory...")
    actions_summary = "; ".join(
        f"{a['type']}:{a.get('ticket_key') or a.get('page_id', '')}"
        for a in actions_taken if a["type"] not in ("senso", "digest", "email_reply")
    ) or "none"

    senso_result = await ingest_signal(IngestInput(
        text=text,
        classification=classification.classification,
        urgency=routing.effective_urgency,
        customer=classification.customer,
        company=classification.company,
        key_phrases=classification.key_phrases,
        actions_summary=actions_summary,
    ))
    actions_taken.append({"type": "senso", "id": senso_result.senso_id})
    await emit("senso", f"Stored (id={senso_result.senso_id})", "success")

    return {
        "classification_result": classification.model_dump(),
        "memory_result": {"frequency": frequency},
        "effective_urgency": routing.effective_urgency,
        "actions_taken": actions_taken,
    }


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

SCENARIOS = [
    {
        "name": "BUG — high urgency (→ Jira P1 + Slack #engineering)",
        "type": "email",
        "text": (
            "Hi, I'm Sarah from Acme Corp. Our entire data export is completely broken. "
            "Every time we try to export to CSV it just crashes with a 500 error. "
            "This is blocking our entire finance team from running their end-of-month reports. "
            "This needs to be fixed immediately."
        ),
    },
    {
        "name": "FEATURE_REQUEST (→ Notion + Slack #product if freq >= 5)",
        "type": "email",
        "text": (
            "Hey team, this is James from TechFlow. Love the product overall. "
            "One thing I really wish you had is a Zapier integration. "
            "We'd love to connect it to our CRM automatically. "
            "Would make our workflow so much smoother."
        ),
    },
    {
        "name": "CHURN_RISK (→ Slack #cs-team immediately)",
        "type": "email",
        "text": (
            "To whom it may concern — I'm Maria from GlobalOps. "
            "We've been really frustrated with the reliability issues over the past month. "
            "We're seriously considering switching to a competitor if things don't improve. "
            "We need a response by end of week or we're cancelling our subscription."
        ),
    },
]


async def _run_tests():
    print("=" * 60)
    print("Signal Pipeline — Full Stage 3 Test (3 signal types)")
    print("=" * 60)

    for scenario in SCENARIOS:
        print(f"\n{'='*60}")
        print(f"SCENARIO: {scenario['name']}")
        print("=" * 60)
        result = await process_signal(scenario["type"], scenario["text"])

        c = result["classification_result"]
        print(f"\nResult:")
        print(f"  Classification   : {c['classification']} (urgency {result['effective_urgency']}/10)")
        print(f"  Customer         : {c['customer']} @ {c['company']}")
        print(f"  Senso frequency  : {result['memory_result']['frequency']} similar signals")
        print(f"  Actions taken:")
        for a in result["actions_taken"]:
            t = a["type"]
            if t == "jira":
                print(f"    [JIRA]   {a['ticket_key']} — {a['url']}")
            elif t == "notion":
                print(f"    [NOTION] {a['url']}")
            elif t == "slack":
                print(f"    [SLACK]  {'✓' if a['ok'] else '✗'} {a['channel']}")
            elif t == "senso":
                print(f"    [SENSO]  id={a['id']}")
            elif t == "digest":
                print(f"    [DIGEST] queued")

    print(f"\n{'='*60}")
    print("All 3 scenarios complete.")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

    mode = sys.argv[1] if len(sys.argv) > 1 else "3"
    if mode == "2":
        async def _s2():
            print("=" * 60)
            print("Stage 2 — Classify → Senso → Jira (BUG scenario)")
            print("=" * 60)
            result = await process_signal("email", SCENARIOS[0]["text"])
            c = result["classification_result"]
            print(f"\nClassification : {c['classification']} (urgency {result['effective_urgency']}/10)")
            print(f"Customer       : {c['customer']} @ {c['company']}")
            print(f"Senso frequency: {result['memory_result']['frequency']} similar past signals")
            print("\nActions taken:")
            for a in result["actions_taken"]:
                if a["type"] == "jira":
                    print(f"  [JIRA]  {a['ticket_key']} — {a['url']}")
                elif a["type"] == "senso":
                    print(f"  [SENSO] ingested id={a['id']}")
            print("\nStage 2 test complete.")
        asyncio.run(_s2())
    else:
        asyncio.run(_run_tests())
