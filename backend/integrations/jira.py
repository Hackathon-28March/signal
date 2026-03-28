"""
jira.py — Jira integration
Creates Jira tickets from classified customer signals.
"""

import os
import requests
from base64 import b64encode
from pydantic import BaseModel
import railtracks as rt


class JiraTicketInput(BaseModel):
    summary: str
    description: str
    priority: str       # "Highest" | "High" | "Medium" | "Low"
    issue_type: str     # "Task" | "Epic" (project has: Epic, Subtask, Task)
    customer_quote: str
    labels: list[str] = ["signal-agent"]


class JiraTicketOutput(BaseModel):
    ticket_key: str
    url: str


@rt.function_node
async def create_jira_ticket(ticket: JiraTicketInput) -> JiraTicketOutput:
    """
    Create a Jira issue with the given summary, description, priority, and customer quote.
    Returns the ticket key (e.g. SCRUM-42) and URL.
    """
    auth = b64encode(
        f"{os.environ['JIRA_EMAIL']}:{os.environ['JIRA_API_TOKEN']}".encode()
    ).decode()

    base_url = os.environ["JIRA_BASE_URL"].rstrip("/")
    body_text = f'Customer said: "{ticket.customer_quote}"\n\n{ticket.description}'

    payload = {
        "fields": {
            "project": {"key": os.environ["JIRA_PROJECT_KEY"]},
            "summary": ticket.summary,
            "description": {
                "type": "doc", "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body_text}],
                }],
            },
            "issuetype": {"name": ticket.issue_type},
            "priority": {"name": ticket.priority},
            "labels": ticket.labels,
        }
    }

    r = requests.post(
        f"{base_url}/rest/api/3/issue",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    if not r.ok:
        print(f"[jira] Error {r.status_code}: {r.text}")
    r.raise_for_status()

    result = r.json()
    key = result["key"]
    return JiraTicketOutput(ticket_key=key, url=f"{base_url}/browse/{key}")
