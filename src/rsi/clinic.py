"""The frozen environment: simulated patient, exam/test examiner, and the doctor's clinic tools.

Nothing in this file is visible to or editable by the optimizer.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import lookup as web
from .cases import Case

PATIENT_SYSTEM = """You are role-playing a patient in a doctor's office. Stay in character.

Rules:
- Reply only with what the patient says out loud: 1-3 short sentences, plain everyday language.
- Answer only the question asked. Do not volunteer extra symptoms or history.
- You do not know your diagnosis. Never name a disease, diagnosis or test result, even if asked.
- If the doctor asks about something not in your information, answer plausibly as a patient
  without that problem would (for example "No, nothing like that").
- You cannot report exam findings or lab results; the doctor must examine you or order tests.

Your information:
{patient}
"""

EXAMINER_SYSTEM = """You are the examination and test-results system in a clinic.
The doctor requests a physical exam component or a diagnostic test; you report the result.

Rules:
- Report only the findings that match the request, copied faithfully from the data below.
- Start every reply with "RESULTS:".
- If the requested exam or test is not in the data, reply "RESULTS: Normal / unremarkable."
- Never state, suggest or hint at a diagnosis. Never reveal findings that were not requested.

Physical examination findings:
{exam}

Test results:
{tests}
"""

CLINIC_TOOLS = ["ask_patient", "examine", "order_test", "submit_diagnosis"]
TOOL_PREFIX = "mcp__clinic__"


def clinic_tool_names(max_lookups: int) -> list[str]:
    """Full MCP names of the doctor's clinic tools; `lookup` only when the harness has a lookup budget."""
    return [TOOL_PREFIX + t for t in CLINIC_TOOLS + (["lookup"] if max_lookups > 0 else [])]


class Speaker(Protocol):
    async def say(self, text: str) -> str: ...


@dataclass
class Budget:
    max_questions: int = 15
    max_requests: int = 10  # examine + order_test combined
    max_lookups: int = 0  # web lookups; 0 means no lookup tool


@dataclass
class Episode:
    """Everything that happens in one consultation, in order."""

    case: Case
    budget: Budget
    events: list[dict] = field(default_factory=list)
    diagnosis: str | None = None
    differential: list[str] = field(default_factory=list)
    reasoning: str = ""
    questions: int = 0
    requests: int = 0
    lookups: int = 0
    started: float = field(default_factory=time.time)

    def log(self, kind: str, **data: Any) -> None:
        self.events.append({"t": round(time.time() - self.started, 2), "kind": kind, **data})

    @property
    def submitted(self) -> bool:
        return self.diagnosis is not None


def patient_system(case: Case) -> str:
    return PATIENT_SYSTEM.format(patient=json.dumps(case.patient, indent=1))


def examiner_system(case: Case) -> str:
    return EXAMINER_SYSTEM.format(exam=json.dumps(case.exam, indent=1), tests=json.dumps(case.tests, indent=1))


def _text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


REDACTED = "[finding consistent with the diagnosis; name withheld]"


def redact(text: str, case: Case) -> str:
    """Case files sometimes name the diagnosis in a result ("biopsy consistent with dermatofibroma").
    Strip the answer key and its aliases from what the frozen roles say, so the doctor must still name it."""
    keys = {case.diagnosis, *case.aliases, re.sub(r"\s*\([^)]*\)", "", case.diagnosis)}
    for k in sorted((k.strip() for k in keys if len(k.strip()) >= 5), key=len, reverse=True):
        words = re.split(r"[\s\-]+", k.replace("'s", "").replace("’s", ""))
        pattern = r"\b" + r"(?:['’]?s)?[\s\-]*".join(map(re.escape, words)) + r"(?:['’]?s)?\b"
        text = re.sub(pattern, REDACTED, text, flags=re.IGNORECASE)
    return text


def build_clinic_tools(ep: Episode, patient: Speaker, examiner: Speaker) -> list:
    """The doctor's tools. They close over this episode's state."""

    def closed() -> dict | None:
        if ep.submitted:
            return _text("The consultation is over; a diagnosis was already submitted. Stop now.")
        return None

    @tool("ask_patient", "Ask the patient one question. Returns what the patient says.", {"question": str})
    async def ask_patient(args: dict) -> dict:
        if (r := closed()) is not None:
            return r
        if ep.questions >= ep.budget.max_questions:
            return _text("Question budget used up. Call submit_diagnosis now.")
        ep.questions += 1
        answer = redact(await patient.say(args["question"]), ep.case)
        ep.log("ask_patient", question=args["question"], answer=answer)
        left = ep.budget.max_questions - ep.questions
        return _text(f"{answer}\n\n[{left} questions left]")

    async def _request(kind: str, what: str) -> dict:
        if (r := closed()) is not None:
            return r
        if ep.requests >= ep.budget.max_requests:
            return _text("Exam/test budget used up. Call submit_diagnosis now.")
        ep.requests += 1
        label = "Physical exam" if kind == "examine" else "Test ordered"
        result = redact(await examiner.say(f"{label}: {what}"), ep.case)
        ep.log(kind, request=what, result=result)
        left = ep.budget.max_requests - ep.requests
        return _text(f"{result}\n\n[{left} exam/test requests left]")

    @tool("examine", "Perform a physical exam component or take vital signs. Describe what you examine.", {"exam": str})
    async def examine(args: dict) -> dict:
        return await _request("examine", args["exam"])

    @tool("order_test", "Order one lab, imaging or other diagnostic test and get its result.", {"test": str})
    async def order_test(args: dict) -> dict:
        return await _request("order_test", args["test"])

    @tool(
        "lookup",
        "Search trusted medical references (StatPearls/PubMed/Merck/MedlinePlus...). Returns top results with highlights.",
        {"query": str},
    )
    async def lookup(args: dict) -> dict:
        if (r := closed()) is not None:
            return r
        if ep.lookups >= ep.budget.max_lookups:
            return _text("Lookup budget used up. Continue the consultation without it.")
        ep.lookups += 1
        results = await asyncio.to_thread(web.exa_search, args["query"])
        block = "\n".join(f"- {r['title']} ({r['url']})\n  {r['text']}" for r in results) or "No results."
        text = redact(block, ep.case)  # titles and urls too: the answer key is never spelled out
        ep.log("lookup", query=args["query"], results=results, text=text)  # raw results kept for the contamination check
        left = ep.budget.max_lookups - ep.lookups
        return _text(f"{text}\n\n[{left} lookups left]")

    @tool(
        "submit_diagnosis",
        "Submit your final diagnosis. This ends the consultation; call it exactly once.",
        {
            "type": "object",
            "properties": {
                "diagnosis": {"type": "string", "description": "Single most likely diagnosis"},
                "differential": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other diagnoses still considered, most likely first (up to 4)",
                },
                "reasoning": {"type": "string", "description": "Brief justification"},
            },
            "required": ["diagnosis"],
        },
    )
    async def submit_diagnosis(args: dict) -> dict:
        if (r := closed()) is not None:
            return r
        ep.diagnosis = args["diagnosis"].strip()
        ep.differential = [d.strip() for d in args.get("differential") or []][:4]
        ep.reasoning = args.get("reasoning", "")
        ep.log("submit_diagnosis", diagnosis=ep.diagnosis, differential=ep.differential, reasoning=ep.reasoning)
        return _text("Diagnosis recorded. The consultation is over. Do not call any more tools.")

    return [ask_patient, examine, order_test, submit_diagnosis] + ([lookup] if ep.budget.max_lookups > 0 else [])


def build_clinic_server(ep: Episode, patient: Speaker, examiner: Speaker):
    """In-process MCP server exposing the clinic tools as mcp__clinic__*."""
    return create_sdk_mcp_server("clinic", tools=build_clinic_tools(ep, patient, examiner))
