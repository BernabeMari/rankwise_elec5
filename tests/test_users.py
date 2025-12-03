import os
import io
import csv
import pytest
from unittest.mock import patch

from app.models import users as users_mod
from app.models.users import (
    hash_password,
    initialize_users_file,
    initialize_sections_file,
    initialize_students_dir,
    get_user,
    register_user,
    authenticate_user,
    get_all_sections,
    get_section,
    get_all_students,
    save_section_from_excel,
    student_id_exists,
    delete_section,
    delete_student_from_section,
    move_student_to_section,
    get_all_section_names,
    add_single_student,
)


def test_hash_password_deterministic():
    h1 = hash_password('secret')
    h2 = hash_password('secret')
    assert h1 == h2 and h1 != hash_password('other')


def test_initialize_files_and_dirs(tmp_path):
    # Autouse fixture set paths; just call and assert created
    initialize_users_file()
    initialize_sections_file()
    initialize_students_dir()
    assert os.path.exists(users_mod.USERS_FILE)
    assert os.path.exists(users_mod.SECTIONS_FILE)
    assert os.path.exists(users_mod.STUDENTS_DIR)


def test_register_and_get_user(tmp_path):
    initialize_users_file()
    ok = register_user('alice', 'pass', 'admin')
    assert ok is True
    user = get_user('alice')
    assert user is not None and user.username == 'alice' and user.role == 'admin'
    # duplicate
    assert register_user('alice', 'pass', 'admin') is False


def test_authenticate_user_via_users_csv(tmp_path):
    initialize_users_file()
    register_user('bob', 'pw', 'student')
    user = authenticate_user('bob', 'pw')
    assert user is not None and user.role == 'student'
    assert authenticate_user('bob', 'wrong') is None


def _create_section_csv(section_name, rows):
    # Helper to write a section CSV and register in sections file
    initialize_sections_file()
    initialize_students_dir()
    filename = 'section.csv'
    file_path = os.path.join(users_mod.STUDENTS_DIR, filename)
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['student_id','fullname','is_irregular','email','grade_level'])
        writer.writerows(rows)
    with open(users_mod.SECTIONS_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([section_name, filename, '2024-01-01 00:00:00'])


def test_get_sections_and_students(tmp_path):
    _create_section_csv('S1', [['1','A','No','a@example.com','11']])
    sections = get_all_sections()
    assert len(sections) == 1 and sections[0].name == 'S1'
    section = get_section('S1')
    assert section is not None and section.student_count == 1
    students = get_all_students()
    assert any(s.student_id == '1' for s in students)


def test_student_id_exists(tmp_path):
    _create_section_csv('S1', [['1','A','No','a@example.com','11']])
    assert student_id_exists('1') is True
    assert student_id_exists('2') is False


def test_save_section_from_excel_happy_and_duplicates(tmp_path, monkeypatch):
    import pandas as pd
    # Mock read_excel to avoid engine/dependency issues
    def fake_read_excel(path):
        return pd.DataFrame({
            'studentid': ['10','11'],
            'name': ['X','Y'],
            'email': ['x@e.com','y@e.com'],
            'isregular': [True, False],
            'gradelevel': ['10','11'],
        })
    initialize_students_dir()
    initialize_sections_file()
    monkeypatch.setattr(pd, 'read_excel', lambda p: fake_read_excel(p))
    class Dummy:
        def __init__(self): pass
        def save(self, p):
            open(p, 'wb').close()
    ok, msg = save_section_from_excel('SecA', Dummy())
    assert ok is True
    # Now duplicate student id across sections
    def fake_read_excel_dup(path):
        return pd.DataFrame({
            'studentid': ['10'],
            'name': ['Z'],
            'email': ['z@e.com'],
            'isregular': [True],
            'gradelevel': ['12'],
        })
    monkeypatch.setattr(pd, 'read_excel', lambda p: fake_read_excel_dup(p))
    ok2, msg2 = save_section_from_excel('SecB', Dummy())
    assert ok2 is False and 'Duplicate student IDs' in msg2


def test_register_students_from_section_and_authenticate(tmp_path):
    _create_section_csv('S1', [['7','Stud','No','s@example.com','12']])
    # auth should auto-register student if not present
    user = authenticate_user('7', '7')
    assert user is not None and user.role == 'student'
    assert get_user('7') is not None


def test_delete_section_and_student(tmp_path):
    _create_section_csv('S1', [['1','A','No','a@example.com','11'], ['2','B','Yes','b@example.com','11']])
    ok, msg = delete_student_from_section('S1', '2')
    assert ok is True
    ok2, msg2 = delete_section('S1')
    assert ok2 is True


def test_move_student_to_section_irregular_only_and_duplicates(tmp_path):
    _create_section_csv('A', [['9','A','Yes','a@example.com','11']])
    _create_section_csv('B', [['9','A','Yes','a@example.com','11']])
    ok, msg = move_student_to_section('9', 'A', 'B')
    assert ok is False and 'already exists' in msg


def test_add_single_student(tmp_path):
    _create_section_csv('A', [['1','A','Yes','a@example.com','11']])
    ok, msg = add_single_student('2', 'B', True, 'b@example.com', '11', 'A')
    assert ok is True


def test_admin_required_and_login_required_redirects(app, client):
    # Access an admin route without login
    resp = client.get('/auth/admin/users', follow_redirects=False)
    assert resp.status_code in (302, 401, 403) 