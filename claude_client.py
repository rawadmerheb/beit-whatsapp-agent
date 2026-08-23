# -*- coding: utf-8 -*-
"""
Wraps the Anthropic Messages API with tool use (function calling) so Claude
can call `search_properties` when it needs listings.
"""

import json
import os

import anthropic

from .property_search import search_properties
from .system_prompt import SYSTEM_PROMPT

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

# claude-sonnet-5: good speed/cost balance for a chat agent. Swap to
# claude-haiku-4-5-20251001 for lower cost, or claude-opus-5 for the most
# capable (slower/pricier) answers. See:
# https://platform.claude.com/docs/en/about-claude/models/overview
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

TOOLS = [
    {
        "name": "search_properties",
        "description": (
            "Search for real estate listings across the whole Lebanese "
            "market: Arkan Estate's own listings (the priority source -- "
            "surface these first when present) plus the rest of the "
            "market -- other agencies, brokers, and portals (OLX/Dubizzle "
            "Lebanon, realestate.com.lb, Byootna, and an open web search "
            "for anything else indexed). include_public_sources defaults "
            "to true so both are checked in one call; set it false only "
            "to check Arkan alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "Area/neighborhood/city/region in Lebanon, e.g. 'Achrafieh', 'Batroun'.",
                },
                "transaction_type": {
                    "type": "string",
                    "enum": ["sale", "rent"],
                },
                "property_type": {
                    "type": "string",
                    "description": "e.g. apartment, villa, studio, office, land, duplex.",
                },
                "min_price": {"type": "number"},
                "max_price": {"type": "number"},
                "bedrooms": {"type": "integer"},
                "include_public_sources": {
                    "type": "boolean",
                    "description": "Also search public Lebanese portals beyond Arkan Estate.",
                },
            },
            "required": ["area"],
        },
    }
]

TOOL_IMPLS = {"search_properties": search_properties}


def _run_tool(block):
    fn = TOOL_IMPLS.get(block.name)
    if fn is None:
        return {"error": f"unknown tool '{block.name}'"}
    try:
        return fn(**block.input)
    except Exception as e:  # noqa: BLE001 - surface any tool error to the model
        return {"error": str(e)}


def ask_agent(user_text, history=None, max_tool_rounds=4):
    """Runs one turn of the agent, including any tool-use rounds.

    `history` is the running message list for this WhatsApp sender (keep it
    short in the caller -- a demo in-memory store trimmed to the last dozen
    turns is fine; swap for a real store before many concurrent users).

    Returns (final_reply_text, updated_history).
    """
    messages = list(history or []) + [{"role": "user", "content": user_text}]

    for _ in range(max_tool_rounds):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            return final_text or "Sorry, I didn't catch that -- can you rephrase?", messages

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _run_tool(block)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
        messages.append({"role": "user", "content": tool_results})

    return (
        "That search is taking more steps than expected -- can you narrow it down "
        "(one area + buy or rent)?",
        messages,
    )
