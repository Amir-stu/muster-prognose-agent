import pytest

from prognose.steps import load_steps, parse_step_file

EXPECTED = [
    "01_quality",
    "02_gate",
    "03_data_request",
    "04_patterns",
    "05_backtest",
    "06_forecast",
    "07_visualize",
    "08_review",
    "09_handover",
    "10_export",
]


def test_load_steps_returns_one_definition_per_diagram_box(steps_dir):
    steps = load_steps(steps_dir)
    assert list(steps) == EXPECTED
    assert steps["02_gate"].kind == "gate"
    assert steps["08_review"].kind == "human"
    assert steps["09_handover"].kind == "human"
    assert steps["10_export"].llm_first is True
    assert steps["03_data_request"].llm_first is True
    assert all(steps[step_id].kind == "tool_llm" for step_id in ("01_quality", "04_patterns", "05_backtest"))
    assert all(step.instructions.strip() for step in steps.values())


def test_non_human_steps_declare_a_tool(steps_dir):
    for step in load_steps(steps_dir).values():
        if step.kind != "human":
            assert step.tool, step.step_id


def test_parse_step_file_reads_front_matter(tmp_path):
    path = tmp_path / "x.md"
    path.write_text(
        "---\r\nstep: 99_test\r\ntitle: Test\r\nkind: tool_llm\r\ntool: profile\r\n"
        "inputs: a.json, b.json\r\nllm_first: true\r\n---\r\nTu etwas.\r\n",
        encoding="utf-8",
    )
    step = parse_step_file(path)
    assert step.step_id == "99_test"
    assert step.inputs == ("a.json", "b.json")
    assert step.llm_first is True
    assert step.instructions.strip() == "Tu etwas."


def test_parse_step_file_when_no_front_matter_raises(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("Nur Text", encoding="utf-8")
    with pytest.raises(ValueError, match="Front-Matter"):
        parse_step_file(path)


def test_parse_step_file_when_unknown_kind_raises(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("---\nstep: a\ntitle: b\nkind: magic\n---\nx\n", encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        parse_step_file(path)


def test_parse_step_file_when_field_missing_raises(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("---\nstep: a\nkind: gate\n---\nx\n", encoding="utf-8")
    with pytest.raises(ValueError, match="title"):
        parse_step_file(path)
