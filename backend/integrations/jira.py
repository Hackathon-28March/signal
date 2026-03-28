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


def _find_existing_ticket(company: str, auth: str, base_url: str) -> dict | None:
    """
    Search for an open signal-agent ticket for this company.
    Returns {'ticket_key', 'url'} if found, else None.
    """
    project = os.environ["JIRA_PROJECT_KEY"]
    jql = f'project = {project} AND labels = "signal-agent" AND summary ~ "\\"{company}\\"" AND statusCategory != Done ORDER BY created DESC'
    r = requests.get(
        f"{base_url}/rest/api/3/search/jql",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        params={"jql": jql, "maxResults": 1, "fields": "summary,status"},
        timeout=10,
    )
    if not r.ok:
        return None
    issues = r.json().get("issues", [])
    if not issues:
        return None
    key = issues[0]["key"]
    return {"ticket_key": key, "url": f"{base_url}/browse/{key}"}


def _add_comment(ticket_key: str, comment: str, auth: str, base_url: str) -> None:
    """Add a comment to an existing Jira ticket."""
    requests.post(
        f"{base_url}/rest/api/3/issue/{ticket_key}/comment",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph",
                         "content": [{"type": "text", "text": comment}]}],
        }},
        timeout=10,
    )


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

    # Extract company from summary (format: "... — CompanyName")
    company = ticket.summary.split("—")[-1].strip() if "—" in ticket.summary else ""

    # Check for existing open ticket for this company — avoid duplicates
    if company:
        existing = _find_existing_ticket(company, auth, base_url)
        if existing:
            comment = (
                f"Another signal received from {company}.\n\n"
                f'Customer said: "{ticket.customer_quote[:300]}"\n\n'
                f"{ticket.description}"
            )
            _add_comment(existing["ticket_key"], comment, auth, base_url)
            print(f"[jira] Existing ticket {existing['ticket_key']} updated (no duplicate created)")
            return JiraTicketOutput(
                ticket_key=existing["ticket_key"],
                url=existing["url"],
            )

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
