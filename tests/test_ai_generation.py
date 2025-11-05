import pytest
from unittest.mock import patch, MagicMock
from app.ai_question_generator import ai_question_generator


def test_generate_question_offline_mode(monkeypatch):
    """Test question generation in offline mode (LM Studio unavailable)"""
    # Force LM Studio to be unavailable
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="python function",
        language="Python",
        question_type="coding"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "coding"
    assert result.get("question_text")
    assert "unit_tests" in result
    assert isinstance(result.get("unit_tests"), str)


def test_generate_question_multiple_choice_offline(monkeypatch):
    """Test multiple choice question generation in offline mode"""
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="machine learning",
        language="Python",
        question_type="multiple_choice"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "multiple_choice"
    assert result.get("question_text")
    assert "options" in result
    assert isinstance(result.get("options"), list)


def test_generate_question_checkbox_offline(monkeypatch):
    """Test checkbox question generation in offline mode"""
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="programming languages",
        language="Python",
        question_type="checkbox"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "checkbox"
    assert "options" in result
    assert "correct_answer" in result


def test_generate_question_true_false_offline(monkeypatch):
    """Test true/false question generation in offline mode"""
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="python compiled",
        language="Python",
        question_type="true_false"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "true_false"
    assert result.get("question_text")


def test_generate_question_identification_offline(monkeypatch):
    """Test identification question generation in offline mode"""
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="web browser language",
        language="Python",
        question_type="identification"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "identification"
    assert result.get("question_text")
    assert "correct_answer" in result


def test_generate_question_enumeration_offline(monkeypatch):
    """Test enumeration question generation in offline mode"""
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: False)
    
    result = ai_question_generator.generate_question(
        prompt="data types",
        language="Python",
        question_type="enumeration"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_type") == "enumeration"
    assert result.get("question_text")


@patch('app.ai_question_generator.ai_question_generator._send_lm_studio_request')
def test_generate_question_with_lm_studio(mock_lm_studio, monkeypatch):
    """Test question generation with LM Studio available"""
    # Mock LM Studio as available
    monkeypatch.setattr(ai_question_generator, "_check_lm_studio_available", lambda: True)
    
    # Mock LM Studio response
    mock_lm_studio.return_value = '{"question_text": "Write a Python function", "unit_tests": "assert test() == True", "language": "Python", "topic": "Functions"}'
    
    result = ai_question_generator.generate_question(
        prompt="python function",
        language="Python",
        question_type="coding"
    )
    
    assert isinstance(result, dict)
    assert result.get("question_text")
    mock_lm_studio.assert_called_once()


def test_generate_ai_question_with_context_endpoint(admin_session, app):
    """Test the /generate_ai_question_with_context endpoint"""
    client = admin_session
    
    with patch('app.ai_question_generator.ai_question_generator._check_lm_studio_available', return_value=False):
        resp = client.post('/generate_ai_question_with_context', json={
            'prompt': 'python function',
            'language': 'Python',
            'question_type': 'coding'
        })
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'question_text' in data or 'error' in data


def test_generate_ai_question_standalone_endpoint(admin_session, app):
    """Test the /form/ai-question endpoint"""
    client = admin_session
    
    with patch('app.ai_question_generator.ai_question_generator._check_lm_studio_available', return_value=False):
        resp = client.post('/form/ai-question', json={
            'prompt': 'machine learning',
            'language': 'Python',
            'question_type': 'multiple_choice'
        })
        
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'question_text' in data or 'error' in data

