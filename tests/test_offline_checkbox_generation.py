import sys


def test_offline_checkbox_generation_structure(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator

    # Force offline path
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)

    result = ai_question_generator.generate_question(
        prompt="select all that apply",
        language="Python",
        question_type="checkbox",
    )

    assert result.get("question_type") == "checkbox"
    assert isinstance(result.get("question_text"), str) and result["question_text"].strip()
    assert isinstance(result.get("options"), list) and len(result["options"]) >= 2
    # correct_answer may be a string or list depending on dataset; just assert the field exists
    assert "correct_answer" in result
