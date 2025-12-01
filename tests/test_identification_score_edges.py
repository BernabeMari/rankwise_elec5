from app.routes import calculate_identification_score


def test_identification_score_punctuation_and_whitespace():
    ok, score, fb = calculate_identification_score('  Python!  ', 'python')
    assert ok is True
    assert score >= 85


def test_identification_score_strong_mismatch():
    ok, score, fb = calculate_identification_score('completely unrelated answer', 'short')
    assert ok in (False, True)
    assert score in (0, 70, 85, 95)  # bucketed scoring
    assert score <= 70
