import json
import time
import pytest
from unittest.mock import patch

from app import db
from app.models.models import Form, Question, Response, Answer


@pytest.fixture()
def sample_form(app):
    with app.app_context():
        form = Form(title='Test Form', description='desc')
        db.session.add(form)
        db.session.flush()
        q1 = Question(form_id=form.id, question_text='2+2?', question_type='multiple_choice', correct_answer='4', points=2, order=1)
        q1.set_options(['3','4','5','6'])
        q2 = Question(form_id=form.id, question_text='Language in browsers', question_type='identification', correct_answer='JavaScript', points=3, order=2)
        q3 = Question(form_id=form.id, question_text='Write sum function', question_type='coding', points=5, order=3)
        db.session.add_all([q1, q2, q3])
        db.session.commit()
        return form.id


def test_submit_form_scoring(student_session, app, sample_form):
    client = student_session
    # Ensure form visible
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
    # Mock AI evaluation for coding
    with patch('app.routes.evaluate_code_with_ai', return_value=(True, 90, 'SCORE_VERDICT: MINOR_FLAW (90%)')):
        resp = client.post(f'/form/{sample_form}/submit', data={}, follow_redirects=False)
    # fetch created response
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        assert resp_db is not None
        answers = {a.question.question_type: a for a in resp_db.answers}
        # Multiple choice default empty => incorrect
        assert answers['multiple_choice'].score_percentage == 0
        # Identification default empty => 0
        assert answers['identification'].score_percentage == 0
        # Coding empty answer should be 0 (AI not invoked)
        assert answers['coding'].score_percentage == 0


def test_submit_form_with_answers(student_session, app, sample_form):
    client = student_session
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form.id).all()}
    with patch('app.routes.evaluate_code_with_ai', return_value=(True, 100, 'SCORE_VERDICT: PERFECT (100%)')):
        resp = client.post(f'/form/{sample_form}/submit', data={
            f'question_{q_by_type["multiple_choice"].id}': '4',
            f'question_{q_by_type["identification"].id}': 'javascript',
            f'question_{q_by_type["coding"].id}': 'def add(a,b): return a+b',
        }, follow_redirects=False)
        assert resp.status_code == 302
    with app.app_context():
        resp_db = Response.query.order_by(Response.id.desc()).first()
        answers = {a.question.question_type: a for a in resp_db.answers}
        assert answers['multiple_choice'].is_correct is True
        assert answers['identification'].score_percentage >= 70
        assert answers['coding'].score_percentage == 100


def test_view_responses_ranking(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        # create two responses with different percentages via answers directly
        r1 = Response(form_id=form.id, submitted_by='s1')
        r2 = Response(form_id=form.id, submitted_by='s2')
        db.session.add_all([r1, r2])
        db.session.flush()
        q_list = Question.query.filter_by(form_id=form.id).all()
        # r1: better score
        db.session.add_all([
            Answer(response_id=r1.id, question_id=q_list[0].id, score_percentage=100),
            Answer(response_id=r1.id, question_id=q_list[1].id, score_percentage=100),
            Answer(response_id=r1.id, question_id=q_list[2].id, score_percentage=100),
        ])
        # r2: lower
        db.session.add_all([
            Answer(response_id=r2.id, question_id=q_list[0].id, score_percentage=0),
            Answer(response_id=r2.id, question_id=q_list[1].id, score_percentage=70),
            Answer(response_id=r2.id, question_id=q_list[2].id, score_percentage=50),
        ])
        db.session.commit()
    resp = client.get(f'/form/{sample_form}/responses')
    assert resp.status_code == 200
    assert b'rank' in resp.data or b'Rank' in resp.data


def test_view_response_badges_and_speed(student_session, app, sample_form):
    client = student_session
    # Submit a response with high scores through the route to avoid detached instances
    with app.app_context():
        form = Form.query.get(sample_form)
        form.is_visible = True
        db.session.commit()
        q_by_type = {q.question_type: q for q in Question.query.filter_by(form_id=form.id).all()}
    with patch('app.routes.evaluate_code_with_ai', return_value=(True, 100, 'SCORE_VERDICT: PERFECT (100%)')):
        client.post(f'/form/{sample_form}/submit', data={
            f'question_{q_by_type["multiple_choice"].id}': '4',
            f'question_{q_by_type["identification"].id}': 'javascript',
            f'question_{q_by_type["coding"].id}': 'def add(a,b): return a+b',
        }, follow_redirects=False)
    with app.app_context():
        r = Response.query.order_by(Response.id.desc()).first()
        r_id = r.id
    with client.session_transaction() as sess:
        sess[f'response_duration_{r_id}'] = 10.0
    resp = client.get(f'/response/{r_id}')
    assert resp.status_code == 200
    assert b'High Score' in resp.data or b'Good Score' in resp.data


def test_clear_form_responses(admin_session, app, sample_form):
    client = admin_session
    with app.app_context():
        form = Form.query.get(sample_form)
        r = Response(form_id=form.id)
        db.session.add(r)
        db.session.flush()
        a = Answer(response_id=r.id, question_id=Question.query.filter_by(form_id=form.id).first().id, score_percentage=100)
        db.session.add(a)
        db.session.commit()
    resp = client.post(f'/form/{sample_form}/responses/clear', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert Response.query.filter_by(form_id=sample_form).count() == 0
        assert Answer.query.count() == 0 