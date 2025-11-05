import pytest
import json
from app import db
from app.models.models import Form, Question, Response, Answer, Dataset


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


def test_checkbox_options_roundtrip(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='checkbox')
        q.set_options(['A','B','C','D'])
        db.session.add(q)
        db.session.commit()
        assert q.get_options() == ['A','B','C','D']


def test_true_false_options(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='true_false')
        db.session.add(q)
        db.session.commit()
        assert q.get_options() == ['True', 'False']


def test_non_mc_options_behaviour(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='identification')
        db.session.add(q)
        db.session.commit()
        assert q.get_options() == []


def test_get_correct_answers_multiple_choice(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='multiple_choice', correct_answer='A')
        db.session.add(q)
        db.session.commit()
        assert q.get_correct_answers() == ['A']


def test_get_correct_answers_checkbox(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='checkbox', correct_answer=json.dumps(['A', 'B']))
        db.session.add(q)
        db.session.commit()
        assert set(q.get_correct_answers()) == {'A', 'B'}


def test_get_correct_answers_enumeration(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.flush()
        q = Question(form_id=f.id, question_text='Q', question_type='enumeration', correct_answer=json.dumps(['Item1', 'Item2', 'Item3']))
        db.session.add(q)
        db.session.commit()
        assert set(q.get_correct_answers()) == {'Item1', 'Item2', 'Item3'}


def test_form_visibility_default(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.commit()
        assert f.is_visible is True


def test_form_visibility_toggle(app):
    with app.app_context():
        f = Form(title='F')
        db.session.add(f)
        db.session.commit()
        assert f.is_visible is True
        f.is_visible = False
        db.session.commit()
        assert f.is_visible is False


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


def test_dataset_model(app):
    with app.app_context():
        d = Dataset(
            name='Test Dataset',
            description='Test',
            filename='test.csv',
            file_path='/path/to/test.csv',
            file_size=1000,
            is_builtin=True,
            is_active=True
        )
        d.set_columns(['col1', 'col2', 'col3'])
        db.session.add(d)
        db.session.commit()
        assert d.get_columns() == ['col1', 'col2', 'col3']
        assert d.name == 'Test Dataset'
        assert d.is_builtin is True
        assert d.is_active is True 