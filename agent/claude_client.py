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

# gemini-3.5-flash-lite: same tool-calling/thinking features as the full
# "flash" models, and on Google's free tier (no credit card needed) --
# chosen over gemini-3.6-flash specifically because the full "flash" tier's
# free daily quota is very low (20 requests/day at time of writing, which a
# single pilot user can burn through in minutes since each tool-using
# message costs 2 requests). "flash-lite" variants consistently get a much
# more generous free allowance. See https://ai.google.dev/gemini-api/docs/models
# for the current model lineup, and https://aistudio.google.com/rate-limit
# (while logged into the account that owns GEMINI_API_KEY) for this
# project's actual live quota numbers. Google periodically retires older
# free-tier models (gemini-2.5-flash was retired for new users in 2026), so
# if this ever starts returning a 404 "model no longer available" error,
# check the models page for the current name and update this default (and
# the GEMINI_MODEL env var, if you've set one). If you ever hit a 429
# RESOURCE_EXHAUSTED error again, that's this same daily-quota wall --
# either wait for it to reset or switch to a model with more free headroom.
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

SEARCH_PROPERTIES_FN = types.FunctionDeclaration(
    name="search_properties",
    description=(
        "Search for real estate listings across the whole Lebanese "
        "market in one call -- multiple listing sites/agencies are "
        "checked concurrently and merged into a single flat list of up "
        "to 12 matching properties, already ranked best-first by how well "
        "each one matches the request, how recently it was listed, and "
        "how complete its price/details are -- never by which site it "
        "came from, so no single site is prioritized, ordered first, or "
        "labeled as special. Present results in the order given rather "
        "than re-sorting them. Each result's own url shows which site "
        "it's on. When a bedroom count was requested and exact matches "
        "alone are thin, the list is topped up with the closest real "
        "listings found instead of returning little or nothing -- each "
        "result's own 'bedrooms' field says whether it's an exact match "
        "or the nearest available, so present that honestly rather than "
        "as identical. include_public_sources defaults to true so the "
        "widest possible set of sources is checked; set it false only if "
        "someone specifically asks to narrow the search to the internal "
        "database alone. Check the response's 'search_unavailable' field "
        "before reacting to an empty 'results' list -- true means the "
        "search couldn't reach any listing sites at all just now (a "
        "temporary issue, say so honestly, never imply the area has no "
        "properties), which is different from a completed search that "
        "genuinely found nothing."
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
                "description": "Also search the wider public Lebanese market beyond the internal database. Almost always leave this true.",
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

        # Gemini 3.x models require each FunctionResponse to echo back the
        # matching FunctionCall's `id` so the model can correlate calls and
        # responses (older models didn't need this). The SDK's
        # Part.from_function_response() convenience helper doesn't expose an
        # `id` parameter, so build the Part manually here instead.
        response_parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    id=call.id,
                    name=call.name,
                    response=_run_tool(call.name, dict(call.args or {})),
                )
            )
            for call in calls
        ]
        # IMPORTANT: this must be role="user", not role="tool"/"function".
        # Gemini's API rejects role="tool" outright with a 400
        # INVALID_ARGUMENT ("Role 'tool' is not supported") -- its role
        # vocabulary only has SYSTEM/USER/MODEL/etc, no separate tool role.
        # A FunctionResponse being sent back to the model is, from the
        # API's point of view, just another "user" turn (the model's own
        # function-call turn already came back with role="model" via
        # response.candidates[0].content above).
        contents.append(types.Content(role="user", parts=response_parts))

    return (
        "That search is taking more steps than expected -- can you narrow it "
        "down (one area + buy or rent)?",
        contents,
    )
