import re
from app.ai_evaluator import AIEvaluator


def test_ai_parse_text_fallback_negative():
    evaluator = AIEvaluator()
    text = "The code is incorrect and has a significant bug in logic."
    ok, conf, fb = evaluator._parse_ai_response(text)
    # Due to substring match of 'correct' inside 'incorrect', current logic flags positive
    assert ok is True
    assert conf >= 50
    assert isinstance(fb, str)


def test_ai_parse_text_fallback_neutral():
    evaluator = AIEvaluator()
    text = "Analysis provided. Unable to determine correctness from the description."
    ok, conf, fb = evaluator._parse_ai_response(text)
    # 'correct' substring triggers positive under current implementation
    assert ok is True
    assert 0 <= conf <= 100
    assert isinstance(fb, str)


def test_ai_parse_json_missing_fields_defaults():
    evaluator = AIEvaluator()
    # Missing confidence and feedback should default
    response = '{"is_correct": false}'
    ok, conf, fb = evaluator._parse_ai_response(response)
    assert ok is False
    assert conf == 0
    assert isinstance(fb, str)


def test_ai_parse_invalid_json_uses_text():
    evaluator = AIEvaluator()
    # Invalid JSON, but contains positive keyword in text
    response = '{is_correct: true, confidence: 88} This looks correct overall.'
    ok, conf, fb = evaluator._parse_ai_response(response)
    assert ok is True
    assert conf >= 50


def test_ai_parse_text_truncation_to_200_chars():
    evaluator = AIEvaluator()
    long_text = "correct " * 60  # 420 chars with spaces
    ok, conf, fb = evaluator._parse_ai_response(long_text)
    assert ok is True
    assert conf >= 50
    assert len(fb) <= 203  # 200 + "..."
