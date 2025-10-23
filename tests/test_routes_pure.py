import re
import pytest

from app.routes import calculate_identification_score, clean_short_answer, parse_ai_response


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


def test_clean_short_answer_basic_trimming():
    out = clean_short_answer('Answer: The Python interpreter, because it runs code.', 'What runs Python code?')
    assert out.startswith('The Python interpreter')
    assert len(out.split()) <= 6


def test_clean_short_answer_preserve_full():
    text = 'A) Option one\nB) Option two'
    out = clean_short_answer('Correct answer: Option one', text, preserve_full=True)
    assert out == 'Option one'


def test_parse_mc_response_happy_path():
    content = 'What is 2+2?\nA) 3\nB) 4\nC) 5\nD) 6\nCorrect answer: B'
    data = parse_ai_response(content, 'multiple_choice')
    assert data['question_type'] == 'multiple_choice'
    assert data['text'].startswith('What is 2+2')
    assert data['options'] == ['3', '4', '5', '6']
    assert data['correct_answer'] == '4'


def test_parse_identification_response_variants():
    content = 'What language runs in a web browser?\nCorrect answer: JavaScript'
    data = parse_ai_response(content, 'identification')
    assert data['correct_answer'].lower() == 'javascript'


def test_parse_coding_response_extracts_problem():
    content = 'Problem: Write a function to sum two integers.\n\nSample Code:'
    data = parse_ai_response(content, 'coding')
    assert 'sum two integers' in data['text']


def test_parse_ai_response_error_fallback():
    data = parse_ai_response('', 'multiple_choice')
    assert data['question_type'] == 'multiple_choice'
    assert data['options'] is not None 


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