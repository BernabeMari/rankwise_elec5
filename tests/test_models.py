import pytest
from app import db
from app.models.models import Form, Question, Response, Answer


def test_question_options_roundtrip(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='multiple_choice')
        q.set_options(['A','B'])
        db.session.add(q)
        db.session.commit()
        assert q.get_options() == ['A','B']


def test_non_mc_options_behaviour(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='identification')
        db.session.add(q)
        db.session.commit()
        assert q.get_options() == []


def test_cascade_delete_form_removes_children(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='multiple_choice')
        db.session.add(q)
        db.session.flush()
        r = Response(form_id=f.id)
        db.session.add(r)
        db.session.flush()
        a = Answer(response_id=r.id, question_id=q.id, score_percentage=100)
        db.session.add(a)
        db.session.commit()
        db.session.delete(f)
        db.session.commit()
        assert Form.query.count() == 0
        assert Question.query.count() == 0
        # Responses are not automatically cascaded when a form is deleted
        assert Response.query.count() == 1
        # Answers tied to deleted questions should be removed
        assert Answer.query.count() == 0 