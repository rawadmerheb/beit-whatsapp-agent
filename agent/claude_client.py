# -*- coding: utf-8 -*-
"""
Wraps the Google Gemini API with tool use (function calling) so Beit can
call `search_properties` when it needs listings.

Note on the filename: this file is still called `claude_client.py` for
historical reasons (the project started on Anthropic's Claude API), but it
now talks to Google's Gemini API instead -- Gemini's free tier needs no
credit card, unlike Anthropic's API, which was the whole reason for this
swap. Nothing else in the project had to change: `ask_agent()` below has
the exact same name and signature as before, so `app.py`'s
`from agent.claude_client import ask_agent` still works untouched.

Get a free key at https://aistudio.google.com/apikey (no billing needed)
and set it as GEMINI_API_KEY.
"""

import os

from google import genai
from google.genai import types

from .property_search import search_properties
from .system_prompt import SYSTEM_PROMPT

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# gemini-3.6-flash: fast, capable, and on Google's free tier (no credit
# card needed). See https://ai.google.dev/gemini-api/docs/models -- Google
# periodically retires older free-tier models (gemini-2.5-flash was retired
# for new users in 2026), so if this ever starts returning a 404 "model no
# longer available" error, check that page for the current model name and
# update this default (and the GEMINI_MODEL env var, if you've set one).
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

SEARCH_PROPERTIES_FN = types.FunctionDeclaration(
    name="search_properties",
    description=(
        "Search for real estate listings across the whole Lebanese "
        "market: Arkan Estate's own listings (the priority source -- "
        "surface these first when present) plus the rest of the "
        "market -- other agencies, brokers, and portals (OLX/Dubizzle "
        "Lebanon, realestate.com.lb, Byootna, and an open web search "
        "for anything else indexed). include_public_sources defaults "
        "to true so both are checked in one call; set it false only "
        "to check Arkan alone."
    ),
    parameters_json_schema={
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
)

TOOLS = [types.Tool(function_declarations=[SEARCH_PROPERTIES_FN])]

TOOL_IMPLS = {"search_properties": search_properties}

GENERATION_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=TOOLS,
    max_output_tokens=2048,
    # Keep replies snappy for a chat agent rather than spending a chunk of
    # the token budget on hidden "thinking". Gemini 3.x models (this
    # project uses gemini-3.6-flash) replaced the older numeric
    # thinking_budget field with a thinking_level enum
    # ("minimal"/"low"/"medium"/"high") -- passing the old thinking_budget
    # field to a 3.x model is rejected outright with a 400 INVALID_ARGUMENT
    # error, so make sure this stays thinking_level, not thinking_budget, if
    # you ever touch this again. "minimal" is the closest equivalent to the
    # old thinking_budget=0 (least hidden reasoning, fastest replies).
    thinking_config=types.ThinkingConfig(thinking_level="minimal"),
)


def _run_tool(name, args):
    fn = TOOL_IMPLS.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**args)
    except Exception as e:  # noqa: BLE001 - surface any tool error to the model
        return {"error": str(e)}


def ask_agent(user_text, history=None, max_tool_rounds=4):
    """Runs one turn of the agent, including any tool-use rounds.

    `history` is the running message list for this WhatsApp sender (keep it
    short in the caller -- a demo in-memory store trimmed to the last dozen
    turns is fine; swap for a real store before many concurrent users).

    Returns (final_reply_text, updated_history).
    """
    contents = list(history or [])
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
    )

    for _ in range(max_tool_rounds):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=GENERATION_CONFIG,
        )

        contents.append(response.candidates[0].content)

        calls = response.function_calls
        if not calls:
            final_text = (response.text or "").strip()
            return (
                final_text or "Sorry, I didn't catch that -- can you rephrase?",
                contents,
            )

        response_parts = [
            types.Part.from_function_response(
                name=call.name,
                response=_run_tool(call.name, dict(call.args or {})),
            )
            for call in calls
        ]
        contents.append(types.Content(role="tool", parts=response_parts))

    return (
        "That search is taking more steps than expected -- can you narrow it down "
        "(one area + buy or rent)?",
        contents,
    )
