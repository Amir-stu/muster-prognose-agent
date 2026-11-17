"""Load steps/NN_*.md: front-matter plus instructions that become the subagent system prompt."""

from dataclasses import dataclass
from pathlib import Path

STEP_KINDS = ("tool_llm", "gate", "human")
REQUIRED_FIELDS = ("step", "title", "kind")
FRONT_MATTER_DELIMITER = "---"


@dataclass(frozen=True)
class StepDefinition:
    step_id: str
    title: str
    kind: str
    tool: str | None
    inputs: tuple[str, ...]
    llm_first: bool
    instructions: str


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise ValueError(f"{path.name}: Front-Matter fehlt")
    try:
        end = lines.index(FRONT_MATTER_DELIMITER, 1)
    except ValueError as error:
        raise ValueError(f"{path.name}: Front-Matter wird nicht geschlossen") from error
    pairs = [line.split(":", 1) for line in lines[1:end] if ":" in line]
    fields = {key.strip(): value.strip() for key, value in pairs}
    return fields, "\n".join(lines[end + 1 :])


def parse_step_file(path: Path) -> StepDefinition:
    fields, body = _split_front_matter(path.read_text(encoding="utf-8"), path)
    missing = [name for name in REQUIRED_FIELDS if not fields.get(name)]
    if missing:
        raise ValueError(f"{path.name}: Pflichtfeld fehlt: {', '.join(missing)}")
    if fields["kind"] not in STEP_KINDS:
        raise ValueError(f"{path.name}: unbekannter kind '{fields['kind']}'")
    inputs = tuple(item.strip() for item in fields.get("inputs", "").split(",") if item.strip())
    return StepDefinition(
        step_id=fields["step"],
        title=fields["title"],
        kind=fields["kind"],
        tool=fields.get("tool") or None,
        inputs=inputs,
        llm_first=fields.get("llm_first", "false").lower() == "true",
        instructions=body,
    )


def load_steps(steps_dir: Path) -> dict[str, StepDefinition]:
    definitions = [parse_step_file(path) for path in sorted(steps_dir.glob("[0-9][0-9]_*.md"))]
    return {definition.step_id: definition for definition in definitions}
