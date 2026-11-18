"""Turn a step's tool output into German text. The text may only quote numbers that exist in the inputs."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from prognose.config import LlmConfig
from prognose.numbers import allowed_values, find_unsupported
from prognose.runner import AgentResult, AgentSpec, run_agent
from prognose.schemas import Interpretation
from prognose.steps import StepDefinition

INTERPRETATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    },
    "required": ["summary", "notes"],
    "additionalProperties": False,
}

OUTPUT_RULES = """

## Ausgaberegeln (gelten für jeden Schritt)
- Schreibe auf Deutsch, sachlich, ohne Werbesprache.
- `summary`: höchstens vier Sätze. `notes`: höchstens fünf kurze Punkte.
- Verwende nur Zahlen, die in den Eingaben stehen. Rechne nichts neu aus, schätze nichts, runde höchstens.
- Wenn eine Aussage eine Zahl bräuchte, die nicht in den Eingaben steht, formuliere sie ohne Zahl.
"""

RETRY_TEMPLATE = (
    "\n\nDeine letzte Antwort wurde abgelehnt: {problem}. "
    "Antworte erneut und verwende ausschließlich Zahlen aus den Eingaben."
)
HOST_ANSWER_FORMAT = """## Antwortformat

Schreibe genau dieses JSON in eine UTF-8-Datei:

```json
{"summary": "<Text>", "notes": ["<Punkt>"]}
```"""
TEMPLATE_SUMMARY = (
    "{title}: automatisch erstellt ohne LLM-Interpretation. Die Kennzahlen stehen in den Tabellen."
)


class StepRejected(RuntimeError):
    """A step's interpretation could not be accepted (malformed, or numbers without a source)."""


@dataclass(frozen=True)
class InterpretationOutcome:
    interpretation: Interpretation
    cost_usd: float


class Interpreter(Protocol):
    def interpret(self, step: StepDefinition, documents: Mapping[str, str]) -> InterpretationOutcome: ...


def build_prompt(documents: Mapping[str, str]) -> str:
    sections = [f"### {name}\n```\n{text}\n```" for name, text in documents.items()]
    return "Eingaben für diesen Schritt:\n\n" + "\n\n".join(sections)


def _unsupported_message(tokens: list[str]) -> str:
    return f"Zahlen ohne Beleg in den Eingaben: {', '.join(tokens)}"


def validate_interpretation(
    step_id: str, interpretation: Interpretation, documents: Mapping[str, str]
) -> None:
    unsupported = find_unsupported(interpretation.full_text(), allowed_values(documents.values()))
    if unsupported:
        raise StepRejected(f"{step_id}: {_unsupported_message(unsupported)}")


@dataclass(frozen=True)
class TemplateInterpreter:
    """Offline interpreter for --no-llm runs and tests: fixed text, no numbers, no cost."""

    def interpret(self, step: StepDefinition, documents: Mapping[str, str]) -> InterpretationOutcome:
        return InterpretationOutcome(Interpretation(summary=TEMPLATE_SUMMARY.format(title=step.title)), 0.0)


def _check(structured: dict[str, Any] | None, allowed: set[float]) -> tuple[Interpretation | None, str]:
    try:
        interpretation = Interpretation.model_validate(structured)
    except ValidationError as error:
        return None, f"ungültiges Format der Interpretation ({error.error_count()} Fehler)"
    unsupported = find_unsupported(interpretation.full_text(), allowed)
    if unsupported:
        return None, _unsupported_message(unsupported)
    return interpretation, ""


class InterpretationPending(Exception):
    """The chat host must write this step's text; the run pauses until it is submitted."""

    def __init__(self, request: str) -> None:
        super().__init__("Interpretation ausstehend")
        self.request = request


def build_host_request(step: StepDefinition, documents: Mapping[str, str]) -> str:
    return "\n\n".join(
        [
            f"# Auftrag für Schritt {step.step_id}: {step.title}",
            step.instructions.strip() + OUTPUT_RULES,
            HOST_ANSWER_FORMAT,
            build_prompt(documents),
        ]
    )


@dataclass(frozen=True)
class HostInterpreter:
    """The chat agent hosting the run writes the text; `accept_answer` checks it on submission."""

    def interpret(self, step: StepDefinition, documents: Mapping[str, str]) -> InterpretationOutcome:
        raise InterpretationPending(build_host_request(step, documents))


def accept_answer(step_id: str, answer: Any, documents: Mapping[str, str]) -> Interpretation:
    """Apply the same format and number checks to a submitted answer as to a subagent's answer."""
    interpretation, problem = _check(answer, allowed_values(documents.values()))
    if interpretation is None:
        raise StepRejected(f"{step_id}: {problem}")
    return interpretation


@dataclass(frozen=True)
class ClaudeInterpreter:
    """Runs the step's instruction file as a `claude -p` subagent and retries once on a rejected answer."""

    llm: LlmConfig
    sandbox_dir: Path
    run_agent_fn: Callable[..., AgentResult] = run_agent

    def interpret(self, step: StepDefinition, documents: Mapping[str, str]) -> InterpretationOutcome:
        spec = AgentSpec(
            name=step.step_id,
            system_prompt=step.instructions + OUTPUT_RULES,
            model=self.llm.model,
            json_schema=INTERPRETATION_SCHEMA,
            max_budget_usd=self.llm.max_budget_usd,
        )
        allowed = allowed_values(documents.values())
        prompt = build_prompt(documents)
        feedback, cost, problem = "", 0.0, ""
        for _attempt in range(self.llm.retries + 1):
            result = self.run_agent_fn(
                spec, prompt + feedback, sandbox_dir=self.sandbox_dir, timeout_s=self.llm.timeout_s
            )
            cost += result.cost_usd
            interpretation, problem = _check(result.structured, allowed)
            if interpretation is not None:
                return InterpretationOutcome(interpretation, round(cost, 4))
            feedback = RETRY_TEMPLATE.format(problem=problem)
        raise StepRejected(f"{step.step_id}: {problem} (Kosten bis hier: {cost:.2f} USD)")
