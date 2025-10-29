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

    # Unit tests should be present in offline mode (sourced from datasets)
    assert "unit_tests" in result
    # Accept non-empty string; datasets store tests in a text field
    assert isinstance(result.get("unit_tests"), str)
    unit_tests_content = result.get("unit_tests", "").strip()
    assert len(unit_tests_content) > 0, f"Unit tests should not be empty. Got: {unit_tests_content[:100]}"
    
    # Also verify that other expected fields are present
    assert result.get("language") is not None, "Language should be present"
    assert result.get("topic") is not None, "Topic should be present"
    
    # Verify hints are present (extracted from sample_code)
    # Hints should be a non-empty string if available from the dataset
    hints = result.get("hints", "")
    # Note: Hints may be empty if the dataset doesn't have hints for that question
    # but it should be a string
    assert isinstance(hints, str), "Hints should be a string"


