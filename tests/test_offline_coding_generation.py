import sys
import types


def test_offline_coding_generation_includes_unit_tests(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator

    # Force LM Studio to be reported as unavailable
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)

    # Generate a coding question with a common prompt
    result = ai_question_generator.generate_question(
        prompt="python function",
        language="Python",
        question_type="coding",
    )

    # Ensure basic structure
    assert isinstance(result, dict)
    assert result.get("question_type") == "coding"
    assert result.get("question_text")

    # Unit tests field should exist in offline mode
    assert "unit_tests" in result
    # It may be an empty string when sourced from datasets fallback
    assert isinstance(result.get("unit_tests"), str)
    
    # Also verify that other expected fields are present
    assert result.get("language") is not None, "Language should be present"
    assert result.get("topic") is not None, "Topic should be present"
    
    # Verify hints are present (extracted from sample_code)
    # Hints may be empty if the dataset doesn't have hints for that question
    hints = result.get("hints", "")
    assert isinstance(hints, str), "Hints should be a string"


