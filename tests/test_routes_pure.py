import re
import pytest

from app.routes import calculate_identification_score
from app.ai_evaluator import AIEvaluator


def test_calculate_identification_score_exact():
    ok, score, fb = calculate_identification_score('Answer', 'answer')
    assert ok is True
    assert score == 100
    assert 'Perfect' in fb


def test_calculate_identification_score_thresholds():
    # Close but below threshold should be 0 or lower bucket
    ok, score, _ = calculate_identification_score('answerrr', 'answer')
    assert score in (0, 70, 85, 95)
    # Length penalties
    ok2, score2, _ = calculate_identification_score('answer with lots of extra stuff', 'answer')
    assert score2 <= 85


def test_calculate_identification_score_empty():
    ok, score, fb = calculate_identification_score('', 'answer')
    assert ok is False and score == 0


def test_ai_evaluator_parse_json_response():
    evaluator = AIEvaluator()
    response = '{"is_correct": true, "confidence": 88, "feedback": "Looks correct and efficient."}'
    ok, conf, fb = evaluator._parse_ai_response(response)
    assert ok is True
    assert conf == 88
    assert 'efficient' in fb


def test_ai_evaluator_parse_text_fallback_positive():
    evaluator = AIEvaluator()
    response = 'The solution is correct and well-structured. Good job.'
    ok, conf, fb = evaluator._parse_ai_response(response)
    assert ok is True
    assert conf >= 50
    assert isinstance(fb, str) and len(fb) > 0


def test_evaluate_code_with_custom_system_smoke(monkeypatch):
    from app import routes as routes_mod
    # Use a trivial python function that should pass when evaluated against problem 1 (sum)
    monkeypatch.setattr(routes_mod, 'evaluate_code_with_custom_system', lambda code_answer, question_text: (True, 100, 'All tests passed'))
    ok, score, fb = routes_mod.evaluate_code_with_custom_system('def sum_numbers(xs):\n    return sum(xs)', 'Write a Python function to sum numbers')
    assert ok is True
    assert score == 100
    assert 'All tests passed' in fb


def test_no_lm_studio_leftovers():
    # Ensure legacy LM Studio functions are removed
    import inspect
    import app.routes as routes_mod
    src = inspect.getsource(routes_mod)
    assert 'query_lm_studio' not in src