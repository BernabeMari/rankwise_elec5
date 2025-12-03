from app.ai_evaluator import AIEvaluator


def test_ai_parse_text_negative_only_is_false():
    evaluator = AIEvaluator()
    text = "This implementation is wrong and has a clear bug."
    ok, conf, fb = evaluator._parse_ai_response(text)
    assert ok is False
    assert conf == 75
    assert isinstance(fb, str) and len(fb) > 0


def test_ai_parse_text_no_keywords_neutral():
    evaluator = AIEvaluator()
    text = "Ambiguous evaluation with limited context."
    ok, conf, fb = evaluator._parse_ai_response(text)
    assert ok is False
    assert conf == 50
    assert isinstance(fb, str) and len(fb) > 0
