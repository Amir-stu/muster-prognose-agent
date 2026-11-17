import pytest

from prognose.interpreter import (
    ClaudeInterpreter,
    StepRejected,
    TemplateInterpreter,
    build_prompt,
    validate_interpretation,
)
from prognose.runner import AgentResult
from prognose.schemas import Interpretation
from prognose.steps import StepDefinition

STEP = StepDefinition(
    step_id="06_forecast",
    title="Modell auswählen",
    kind="tool_llm",
    tool="forecast",
    inputs=("06_forecast.json",),
    llm_first=False,
    instructions="Erkläre die Modellwahl.",
)
DOCUMENTS = {"06_forecast.json": '{"model": "ets", "mase": 0.4321, "points": [{"point": 150.25}]}'}


def _fake_agent(*structured_outputs):
    calls = []

    def run(spec, prompt, *, sandbox_dir, timeout_s):
        calls.append(prompt)
        return AgentResult(text="", structured=structured_outputs[len(calls) - 1], cost_usd=0.05)

    return run, calls


def test_template_interpreter_returns_text_without_numbers():
    outcome = TemplateInterpreter().interpret(STEP, DOCUMENTS)
    assert outcome.cost_usd == 0.0
    assert "Modell auswählen" in outcome.interpretation.summary
    validate_interpretation(STEP.step_id, outcome.interpretation, DOCUMENTS)


def test_build_prompt_contains_each_document_by_name():
    prompt = build_prompt(DOCUMENTS)
    assert "### 06_forecast.json" in prompt
    assert '"mase": 0.4321' in prompt


def test_claude_interpreter_when_numbers_backed_accepts_first_answer(config, tmp_path):
    run, calls = _fake_agent({"summary": "ETS gewinnt mit MASE 0,43; erster Wert 150,25.", "notes": []})
    interpreter = ClaudeInterpreter(llm=config.llm, sandbox_dir=tmp_path, run_agent_fn=run)
    outcome = interpreter.interpret(STEP, DOCUMENTS)
    assert len(calls) == 1
    assert outcome.cost_usd == pytest.approx(0.05)
    assert outcome.interpretation.summary.startswith("ETS")


def test_claude_interpreter_when_invented_number_retries_with_feedback(config, tmp_path):
    run, calls = _fake_agent(
        {"summary": "Wir erwarten 999,9 Einheiten.", "notes": []},
        {"summary": "ETS gewinnt.", "notes": ["Erster Wert 150,25."]},
    )
    interpreter = ClaudeInterpreter(llm=config.llm, sandbox_dir=tmp_path, run_agent_fn=run)
    outcome = interpreter.interpret(STEP, DOCUMENTS)
    assert len(calls) == 2
    assert "999,9" in calls[1]
    assert outcome.cost_usd == pytest.approx(0.10)


def test_claude_interpreter_when_always_invented_raises(config, tmp_path):
    bad = {"summary": "Wir erwarten 999,9 Einheiten.", "notes": []}
    run, _ = _fake_agent(bad, bad)
    interpreter = ClaudeInterpreter(llm=config.llm, sandbox_dir=tmp_path, run_agent_fn=run)
    with pytest.raises(StepRejected, match="06_forecast"):
        interpreter.interpret(STEP, DOCUMENTS)


def test_claude_interpreter_when_malformed_output_retries_then_raises(config, tmp_path):
    run, calls = _fake_agent(None, {"notes": []})
    interpreter = ClaudeInterpreter(llm=config.llm, sandbox_dir=tmp_path, run_agent_fn=run)
    with pytest.raises(StepRejected, match="Format"):
        interpreter.interpret(STEP, DOCUMENTS)
    assert len(calls) == 2


def test_validate_interpretation_when_unsupported_raises():
    with pytest.raises(StepRejected, match="777"):
        validate_interpretation("x", Interpretation(summary="777 Stück", notes=[]), DOCUMENTS)
