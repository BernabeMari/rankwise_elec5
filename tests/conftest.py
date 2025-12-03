import os
import tempfile
import shutil
import pytest
from flask import session

from app import create_app, db
import app.models.users as users_mod


@pytest.fixture(scope='session')
def temp_dir_session():
    d = tempfile.mkdtemp(prefix='rankwise-tests-')
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def patch_user_paths(tmp_path, monkeypatch):
    base = tmp_path
    users_file = base / 'users.csv'
    sections_file = base / 'sections.csv'
    students_dir = base / 'students'
    students_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(users_mod, 'USERS_FILE', str(users_file), raising=False)
    monkeypatch.setattr(users_mod, 'SECTIONS_FILE', str(sections_file), raising=False)
    monkeypatch.setattr(users_mod, 'STUDENTS_DIR', str(students_dir), raising=False)
    # Ensure clean state for each test
    for p in [users_file, sections_file]:
        if p.exists():
            p.unlink()


@pytest.fixture()
def app(tmp_path, monkeypatch):
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret',
    })
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_session(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 'admin'
        sess['role'] = 'admin'
    return client


@pytest.fixture()
def student_session(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 'student1'
        sess['role'] = 'student'
    return client


def set_session_role(client, user_id, role):
    with client.session_transaction() as sess:
        sess['user_id'] = user_id
        sess['role'] = role 