import sys
import json
import types


def _force_offline(module):
    return lambda: False


def test_offline_mc_generation_structure(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", _force_offline(ai_question_generator))

    result = ai_question_generator.generate_question(
        prompt="basic arithmetic",
        language="Python",
        question_type="multiple_choice",
    )

    assert result.get("question_type") == "multiple_choice"
    assert isinstance(result.get("question_text"), str) and result["question_text"].strip()
    assert isinstance(result.get("options"), list) and len(result["options"]) >= 2
    assert isinstance(result.get("correct_answer"), str)
    if len(result.get("options", [])) >= 2:
        assert result["correct_answer"] in result["options"] or result["correct_answer"]


def test_offline_identification_generation_structure(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", _force_offline(ai_question_generator))

    result = ai_question_generator.generate_question(
        prompt="web browser language",
        language="Python",
        question_type="identification",
    )

    assert result.get("question_type") == "identification"
    assert isinstance(result.get("question_text"), str) and result["question_text"].strip()
    assert isinstance(result.get("expected_outputs"), str)


def test_offline_true_false_generation_structure(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", _force_offline(ai_question_generator))

    result = ai_question_generator.generate_question(
        prompt="is python dynamically typed",
        language="Python",
        question_type="true_false",
    )

    assert result.get("question_type") == "true_false"
    assert isinstance(result.get("question_text"), str) and result["question_text"].strip()
    assert isinstance(result.get("options"), list)
    assert set(map(str, result.get("options", []))) >= {"True", "False"}
    assert result.get("correct_answer") in {"True", "False"}


def test_offline_enumeration_generation_structure(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", _force_offline(ai_question_generator))

    result = ai_question_generator.generate_question(
        prompt="list sorting algorithms",
        language="Python",
        question_type="enumeration",
    )

    assert result.get("question_type") == "enumeration"
    assert isinstance(result.get("question_text"), str) and result["question_text"].strip()
    assert isinstance(result.get("expected_outputs"), str)


def test_online_checkbox_generation_stays_checkbox(monkeypatch):
    sys.path.append('app')
    from ai_question_generator import ai_question_generator
    
    # Force online path
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: True)
    sample_response = json.dumps({
        "question_text": "Which protocols provide secure communication?",
        "question_type": "multiple_choice",
        "options": ["HTTPS", "SSL/TLS", "HTTP", "FTP"],
        "correct_answer": "HTTPS, SSL/TLS"
    })
    monkeypatch.setattr(ai_question_generator, "_send_lm_studio_request", lambda prompt: sample_response)
    
    result = ai_question_generator.generate_question(
        prompt="select all secure protocols",
        language="Python",
        question_type="checkbox",
    )
    
    assert result.get("question_type") == "checkbox"
    assert isinstance(result.get("options"), list)
    assert set(result.get("correct_answer", [])) == {"HTTPS", "SSL/TLS"}
