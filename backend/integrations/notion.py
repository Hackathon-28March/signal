"""
notion.py — Notion integration
Creates roadmap items in a Notion database.
"""

import os
from notion_client import Client
from pydantic import BaseModel
import railtracks as rt


def _client() -> Client:
    return Client(auth=os.environ["NOTION_API_KEY"])


class NotionRoadmapInput(BaseModel):
    title: str
    description: str
    priority: str       # "P1 - Critical" | "P2 - High" | "P3 - Medium" | "P4 - Low"
    signal_count: int


class NotionRoadmapOutput(BaseModel):
    page_id: str
    url: str


@rt.function_node
async def create_roadmap_item(item: NotionRoadmapInput) -> NotionRoadmapOutput:
    """
    Create a new roadmap item in the Notion database.
    Returns the Notion page ID and URL.
    """
    notion = _client()

    page = notion.pages.create(
        parent={"database_id": os.environ["NOTION_ROADMAP_DB_ID"]},
        properties={
            "Name": {"title": [{"text": {"content": item.title}}]},
            "Priority": {"select": {"name": item.priority}},
            "Status": {"select": {"name": "Considering"}},
            "Signal Count": {"number": item.signal_count},
            "Source": {"select": {"name": "Signal Agent"}},
        },
        children=[{
            "object": "block", "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": item.description}}]
            },
        }],
    )

    return NotionRoadmapOutput(page_id=page["id"], url=page["url"])
