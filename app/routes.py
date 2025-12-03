from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from app import db
from app.models.models import Form, Question, Response, Answer, Dataset
from app.models.users import login_required, admin_required, get_user, get_all_students
from datetime import datetime
from io import BytesIO
import requests, time
import re
from rapidfuzz import fuzz
import json
import subprocess
import tempfile
import os
import uuid
from app.ai_evaluator import ai_evaluator

main = Blueprint('main', __name__)

QUESTION_CATEGORY_CHOICES = [
    'Cybersecurity',
    'Digital Electronics',
    'Linux Administration',
    'Networking',
    'Robotics',
    'Android App Development',
    'Database',
    'Java',
    'C#',
    'Python',
    'Web Design',
    'Esports',
    'C',
    'C++'
]


def calculate_identification_score(student_answer, correct_answer):
    """
    Calculate score for identification questions using fuzzy matching.
    Returns a tuple of (is_correct, score_percentage, feedback).
    
    Scoring rules:
    - 100% for exact match (case-insensitive)
    - 95% for very high similarity (95-99%) - only for minor typos
    - 85% for high similarity (85-94%) - only for close spelling
    - 70% for medium similarity (70-84%) - only for reasonable attempts
    - 0% for low similarity (<70%) - no partial credit for poor matches
    """
    if not student_answer or not correct_answer:
        return False, 0, "No answer provided"
    
    # Clean and normalize both answers
    student_clean = student_answer.lower().strip()
    correct_clean = correct_answer.lower().strip()
    
    # Check for exact match first (case-insensitive)
    if student_clean == correct_clean:
        return True, 100, "Perfect match!"
    
    # For identification questions, use more strict matching
    # Use ratio (overall similarity) as primary, with stricter thresholds
    ratio = fuzz.ratio(student_clean, correct_clean)
    
    # Use partial_ratio only if the student answer is not significantly longer
    # This prevents "defended" from matching "def" with high scores
    length_ratio = len(student_clean) / len(correct_clean) if len(correct_clean) > 0 else 1
    
    # If student answer is much longer than correct answer, penalize heavily
    if length_ratio > 1.5:  # Student answer is 50% longer
        ratio = ratio * 0.7  # Reduce similarity score
    
    # If student answer is much shorter, also penalize
    if length_ratio < 0.7:  # Student answer is 30% shorter
        ratio = ratio * 0.8  # Reduce similarity score
    
    # Determine score based on similarity with stricter thresholds
    if ratio >= 95 and length_ratio >= 0.8 and length_ratio <= 1.2:
        score = 95
        feedback = f"Excellent! Similarity: {ratio:.1f}% (minor typo)"
    elif ratio >= 85 and length_ratio >= 0.7 and length_ratio <= 1.3:
        score = 85
        feedback = f"Very good! Similarity: {ratio:.1f}% (close spelling)"
    elif ratio >= 70 and length_ratio >= 0.6 and length_ratio <= 1.4:
        score = 70
        feedback = f"Good attempt! Similarity: {ratio:.1f}% (reasonable match)"
    else:
        score = 0
        feedback = f"Not close enough. Similarity: {ratio:.1f}% (length difference: {length_ratio:.1f}x)"
    
    # Consider it correct if score is 70% or higher
    is_correct = score >= 70
    
    return is_correct, score, feedback


@main.route('/')
@login_required
def index():
    # Show all forms for admins, only visible forms for regular users
    if session.get('role') == 'admin':
        forms = Form.query.order_by(Form.created_at.desc()).all()
        answered_forms = []
    else:
        # For students: show both unanswered and answered forms
        user_id = session.get('user_id')
        
        # Get all visible forms
        visible_forms = Form.query.filter_by(is_visible=True).order_by(Form.created_at.desc()).all()
        
        # Separate forms into answered and unanswered
        forms = []
        answered_forms = []
        
        for form in visible_forms:
            # Check if this student has already submitted a response for this form
            existing_response = Response.query.filter_by(
                form_id=form.id, 
                submitted_by=user_id
            ).first()
            
            if existing_response:
                # Calculate score for this response
                questions = Question.query.filter_by(form_id=form.id).all()
                total_possible_points = sum(q.points for q in questions) or 0
                q_points = {q.id: q.points for q in questions}
                earned_points = 0.0
                for ans in existing_response.answers:
                    pts = q_points.get(ans.question_id, 0)
                    earned_points += (float(ans.score_percentage or 0) / 100.0) * pts
                overall_pct = (earned_points / total_possible_points * 100.0) if total_possible_points > 0 else 0.0
                
                # Add to answered forms with response info and calculated score
                answered_forms.append({
                    'form': form,
                    'response': existing_response,
                    'overall_pct': overall_pct,
                    'earned_points': earned_points,
                    'total_points': total_possible_points
                })
            else:
                # Add to unanswered forms
                forms.append(form)
    
    user = get_user(session['user_id'])
    return render_template('index.html', forms=forms, answered_forms=answered_forms, user=user)

@main.route('/form/new', methods=['GET', 'POST'])
@admin_required
def new_form():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        
        if not title:
            flash('Title is required!', 'danger')
            return redirect(url_for('main.new_form'))
        
        form = Form(title=title, description=description)
        db.session.add(form)
        db.session.commit()
        
        return redirect(url_for('main.edit_form', form_id=form.id))
    
    return render_template('new_form.html')

@main.route('/form/<int:form_id>/edit', methods=['GET'])
@admin_required
def edit_form(form_id):
    form = Form.query.get_or_404(form_id)
    questions = Question.query.filter_by(form_id=form_id).order_by(Question.order).all()
    return render_template('edit_form.html', form=form, questions=questions, question_categories=QUESTION_CATEGORY_CHOICES)

@main.route('/form/<int:form_id>/question/new', methods=['POST'])
@admin_required
def add_question(form_id):
    form = Form.query.get_or_404(form_id)
    
    question_text = request.form.get('question_text')
    question_type = request.form.get('question_type')
    correct_answer = request.form.get('correct_answer')
    category = request.form.get('category') or None
    points = request.form.get('points', 1)
    
    # Ensure points is a valid integer
    try:
        points = int(points)
        if points < 1:
            points = 1
    except (ValueError, TypeError):
        points = 1
    
    if not question_text or not question_type:
        flash('Question text and type are required!', 'danger')
        return redirect(url_for('main.edit_form', form_id=form_id))
    
    # Get the highest order and add 1
    highest_order = db.session.query(db.func.max(Question.order)).filter_by(form_id=form_id).scalar() or 0
    new_order = highest_order + 1
    
    question = Question(
        form_id=form_id,
        question_text=question_text,
        question_type=question_type,
        order=new_order,
        correct_answer=correct_answer,
        points=points,
        category=category
    )
    
    # Handle options for multiple choice and checkbox
    if question_type in ['multiple_choice', 'checkbox']:
        options = request.form.getlist('options[]')
        if options:
            question.set_options(options)
        # For checkbox, allow multiple correct answers via correct_answer[] inputs
        if question_type == 'checkbox':
            correct_multi = request.form.getlist('correct_answer[]')
            if correct_multi:
                question.correct_answer = json.dumps(correct_multi)
        question.sample_code = request.form.get('sample_code')
    
    # Handle true/false question
    if question_type == 'true_false':
        # Ensure options are set to True/False for consistency in rendering
        question.options = json.dumps(["True", "False"])  # fixed options
        # Correct answer should be a single string "True" or "False"
        ca = request.form.get('correct_answer')
        question.correct_answer = 'True' if (ca is not None and ca.lower() in ['true', 't', '1', 'yes']) else 'False' if (ca is not None and ca.lower() in ['false', 'f', '0', 'no']) else ca
        question.sample_code = request.form.get('sample_code')
    
    # Handle enumeration question (multiple expected items as correct answers)
    if question_type == 'enumeration':
        # Accept multiple values as correct answers
        correct_multi = request.form.getlist('correct_answer[]')
        if not correct_multi:
            # Fallback: support a single textarea separated by commas/newlines
            raw = request.form.get('correct_answer') or ''
            parts = [p.strip() for p in (raw.replace('\n', ',').split(',')) if p.strip()]
            correct_multi = parts
        question.correct_answer = json.dumps(correct_multi)
        question.sample_code = request.form.get('sample_code')
    
    # Handle coding question fields
    if question_type == 'coding':
        question.sample_code = request.form.get('sample_code')
        # Repurpose expected_output field to store unit tests
        unit_tests = request.form.get('expected_output') or request.form.get('unit_tests')
        question.expected_output = unit_tests
        # If admin wants to append to dataset, add a row to CSV
        try:
            append_flag = request.form.get('append_to_dataset') in ('1', 'true', 'on', 'yes')
            print(f"DEBUG: append_flag={append_flag}, unit_tests length={len(unit_tests) if unit_tests else 0}")
            if append_flag and unit_tests:
                import pandas as pd
                import os
                csv_path = os.path.join(os.path.dirname(__file__), 'data', 'datasets', 'it_olympics_coding.csv')
                print(f"DEBUG: CSV path = {csv_path}")
                print(f"DEBUG: CSV exists = {os.path.exists(csv_path)}")
                # Compute next problem_id safely
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python')
                    next_id = (df['problem_id'].max() + 1) if not df.empty else 1
                    print(f"DEBUG: Current max problem_id = {df['problem_id'].max()}, next_id = {next_id}")
                else:
                    next_id = 1
                # Prepare row
                lang = request.form.get('coding_language') or 'Python'
                hints = request.form.get('hints') or ''
                new_row = {
                    'problem_id': int(next_id),
                    'topic': 'Algorithms',
                    'language': lang,
                    'problem_statement': question_text,
                    'unit_tests': unit_tests,
                    'expected_outputs': '',
                    'scoring_criteria': 'Auto-graded by unit tests',
                    'max_score': 100,
                    'hints': hints,
                }
                print(f"DEBUG: New row = {new_row}")
                # Append
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python')
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                else:
                    df = pd.DataFrame([new_row])
                # Write with proper encoding and quoting
                df.to_csv(csv_path, index=False, encoding='utf-8', quoting=1)  # quoting=1 for QUOTE_ALL
                print(f"DEBUG: Successfully wrote to CSV. New length = {len(df)}")
                flash('Coding problem added to dataset.', 'success')
            else:
                print(f"DEBUG: Not appending - append_flag={append_flag}, unit_tests={bool(unit_tests)}")
        except Exception as e:
            print('Failed to append coding problem to dataset:', e)
            import traceback
            traceback.print_exc()
    
    # Handle sample code for identification questions
    if question_type == 'identification':
        question.sample_code = request.form.get('sample_code')
    
    db.session.add(question)
    db.session.commit()
    
    return redirect(url_for('main.edit_form', form_id=form_id))

# LM Studio integration removed - using custom code evaluation system



# --- Offline fallback: generate questions from local CSV datasets when LM Studio is unavailable ---
def _load_active_datasets_frames(max_rows_per_df=1000):
    """Load active built-in datasets into pandas DataFrames with metadata.
    Returns list of tuples: (dataset, dataframe). Fails gracefully returning [].
    Only loads IT Olympics CSV files, ignores old datasets.
    """
    try:
        import pandas as pd
    except Exception:
        return []
    frames = []
    try:
        # Only load IT Olympics datasets, ignore old ones
        it_olympics_files = [
            'it_olympics_multiple_choice.csv',
            'it_olympics_true_false.csv', 
            'it_olympics_identification.csv',
            'it_olympics_enumeration.csv',
            'it_olympics_checkbox.csv',
            'it_olympics_coding.csv',
            'it_olympics_code_eval.csv'
        ]
        
        active = Dataset.query.filter_by(is_active=True, is_builtin=True).all()
        for ds in active:
            # Only process IT Olympics files
            if ds.filename in it_olympics_files:
                try:
                    df = pd.read_csv(ds.file_path, on_bad_lines='skip', engine='python')
                    if len(df) > max_rows_per_df:
                        df = df.sample(n=max_rows_per_df, random_state=42)
                    frames.append((ds, df))
                except Exception:
                    continue
    except Exception:
        return frames
    return frames

def _select_distractors(correct_item, pool, k=3):
    """Pick up to k distinct distractors from pool that are not equal to correct_item."""
    import random
    choices = [p for p in pool if isinstance(p, str) and p.strip() and p != correct_item]
    random.shuffle(choices)
    return choices[:k]

def generate_question_from_datasets(prompt, question_type):
    """Generate a simple question using local datasets.
    Supports: multiple_choice, identification, true_false (basic), checkbox (basic), enumeration (basic).
    Returns dict matching frontend expectation: {text, options?, correct_answer}.
    Raises Exception on failure.
    """
    import random
    # Don't set a fixed seed - let it be truly random for shuffling

    frames = _load_active_datasets_frames()
    # Only use active datasets - removed fallback that bypassed is_active check

    if not frames:
        raise Exception('No active datasets available. Please activate at least one dataset in the Manage Datasets page to generate questions without AI.')

    # Try to find a dataframe with definition-like columns for simple Q/A
    def find_definition_df():
        for ds, df in frames:
            cols_lower = [str(c).lower() for c in df.columns]
            if any(k in cols_lower for k in ['term', 'concept', 'topic', 'name']):
                if any(k in cols_lower for k in ['definition', 'description', 'meaning', 'explanation']):
                    return ds, df
        return frames[0]

    ds, df = find_definition_df()
    cols = [str(c) for c in df.columns]
    cols_lower = [c.lower() for c in cols]

    # Identify potential columns
    def_col = None
    term_col = None
    for c in cols:
        cl = c.lower()
        if def_col is None and any(k in cl for k in ['definition', 'description', 'meaning', 'explanation']):
            def_col = c
        if term_col is None and any(k in cl for k in ['term', 'concept', 'topic', 'name']):
            term_col = c
    # Fallback: use first two columns if not found
    if term_col is None and len(cols) >= 1:
        term_col = cols[0]
    if def_col is None and len(cols) >= 2:
        def_col = cols[1]

    # Choose a row biased by prompt keyword match if possible
    def pick_row():
        subset = df
        try:
            if prompt:
                mask = None
                for c in [term_col, def_col]:
                    if c in df.columns and df[c].dtype == object:
                        m = df[c].astype(str).str.contains(str(prompt), case=False, na=False)
                        mask = m if mask is None else (mask | m)
                if mask is not None and mask.any():
                    subset = df[mask]
        except Exception:
            subset = df
        try:
            return subset.sample(n=1, random_state=random.randint(0, 10_000)).iloc[0]
        except Exception:
            return df.iloc[random.randrange(0, len(df))]

    row = pick_row()
    term = str(row.get(term_col, '')).strip()
    definition = str(row.get(def_col, '')).strip()

    if question_type in ['multiple_choice', 'checkbox']:
        # If a dedicated CSV exists, use it
        try:
            import pandas as pd
            import os
            base = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
            mc_path = os.path.join(base, 'it_olympics_multiple_choice.csv')
            if os.path.exists(mc_path):
                dfmc = pd.read_csv(mc_path, on_bad_lines='skip', engine='python')
                # Search for questions matching prompt keywords
                if prompt and prompt.strip():
                    prompt_lower = prompt.lower()
                    # Find all relevant questions first
                    relevant_questions = []
                    for idx, row in dfmc.iterrows():
                        score = 0
                        question_text = str(row.get('question', '')).lower()
                        topic = str(row.get('topic', '')).lower()
                        # Higher score for exact topic match, then question text match
                        if any(word in topic for word in prompt_lower.split()):
                            score += 10
                        if any(word in question_text for word in prompt_lower.split()):
                            score += 5
                        if score > 0:
                            relevant_questions.append((score, idx, row))
                    
                    if relevant_questions:
                        # Shuffle relevant questions and pick one randomly
                        random.shuffle(relevant_questions)
                        pick = relevant_questions[0][2]  # Get the row
                    else:
                        # No relevant questions found, pick any random question
                        pick = dfmc.sample(n=1).iloc[0]
                else:
                    # No prompt, pick any random question
                    pick = dfmc.sample(n=1).iloc[0]
                qtext = str(pick.get('question', '')).strip()
                opts = [str(pick.get(k, '')).strip() for k in ['A','B','C','D']]
                # Use raw option texts (no letter prefixes) and set correct_answer to the actual text
                correct_letter = str(pick.get('correct', 'A')).strip()[:1].upper()
                idx = max(0, min(3, ord(correct_letter) - ord('A')))
                correct_text = opts[idx] if idx < len(opts) else (opts[0] if opts else '')
                res = {'text': qtext, 'question_type': 'multiple_choice', 'options': opts, 'correct_answer': correct_text, 'correct_letter': correct_letter.lower()}
                if question_type == 'checkbox':
                    cb_path = os.path.join(base, 'it_olympics_checkbox.csv')
                    if os.path.exists(cb_path):
                        dfcb = pd.read_csv(cb_path, on_bad_lines='skip', engine='python')
                        # Search for checkbox questions matching prompt
                        if prompt and prompt.strip():
                            prompt_lower = prompt.lower()
                            relevant_questions = []
                            for idx, row in dfcb.iterrows():
                                score = 0
                                question_text = str(row.get('question', '')).lower()
                                topic = str(row.get('topic', '')).lower()
                                if any(word in topic for word in prompt_lower.split()):
                                    score += 10
                                if any(word in question_text for word in prompt_lower.split()):
                                    score += 5
                                if score > 0:
                                    relevant_questions.append((score, idx, row))
                            
                            if relevant_questions:
                                random.shuffle(relevant_questions)
                                pick2 = relevant_questions[0][2]
                            else:
                                pick2 = dfcb.sample(n=1).iloc[0]
                        else:
                            pick2 = dfcb.sample(n=1).iloc[0]
                        q2 = str(pick2.get('question','')).strip()
                        opts2 = [str(pick2.get(k,'')).strip() for k in ['A','B','C','D']]
                        correct_multi = str(pick2.get('correct','')).strip()
                        letters = [s.strip().upper() for s in correct_multi.replace('"','').split(',') if s.strip()]
                        idxs = [ord(L)-ord('A') for L in letters]
                        correct_texts = [opts2[i] for i in idxs if 0 <= i < len(opts2)]
                        res = {'text': q2, 'question_type': 'checkbox', 'options': opts2, 'correct_answer': correct_texts}
                return res
        except Exception:
            pass
        # Build distractor definitions from other rows
        pool_defs = [str(v).strip() for v in df[def_col].dropna().astype(str).tolist()] if def_col in df.columns else []
        distractors = _select_distractors(definition, pool_defs, k=3)
        # If not enough distractors, synthesize short ones from other columns
        if len(distractors) < 3:
            for c in df.columns:
                if c == def_col:
                    continue
                extra_pool = [str(v).strip() for v in df[c].dropna().astype(str).tolist()]
                distractors += _select_distractors(definition, extra_pool, k=3-len(distractors))
                if len(distractors) >= 3:
                    break
        options = distractors + [definition]
        random.shuffle(options)
        letters = ['A', 'B', 'C', 'D']
        opts_unlabeled = options[:4]
        correct_letter = letters[opts_unlabeled.index(definition)] if definition in opts_unlabeled else letters[-1]
        text = f"Which of the following best describes {term}?"
        if prompt and prompt.strip():
            text = f"Which of the following best describes {prompt} related to {term}?"
        result = {
            'text': text,
            'question_type': question_type,
            'options': opts_unlabeled,
            'correct_answer': definition,
            'correct_letter': correct_letter.lower()
        }
        if question_type == 'checkbox':
            # For checkbox, keep only one correct for simplicity
            result['correct_answer'] = [definition]
        return result

    if question_type == 'identification':
        try:
            import pandas as pd
            import os
            base = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
            id_path = os.path.join(base, 'it_olympics_identification.csv')
            if os.path.exists(id_path):
                dfid = pd.read_csv(id_path, on_bad_lines='skip', engine='python')
                # Search for identification questions matching prompt
                if prompt and prompt.strip():
                    prompt_lower = prompt.lower()
                    relevant_questions = []
                    for idx, row in dfid.iterrows():
                        score = 0
                        question_text = str(row.get('question', '')).lower()
                        topic = str(row.get('topic', '')).lower()
                        if any(word in topic for word in prompt_lower.split()):
                            score += 10
                        if any(word in question_text for word in prompt_lower.split()):
                            score += 5
                        if score > 0:
                            relevant_questions.append((score, idx, row))
                    
                    if relevant_questions:
                        random.shuffle(relevant_questions)
                        pick = relevant_questions[0][2]
                    else:
                        pick = dfid.sample(n=1).iloc[0]
                else:
                    pick = dfid.sample(n=1).iloc[0]
                return {
                    'text': str(pick.get('question','')).strip(), 
                    'question_type': 'identification', 
                    'options': ['Answer field (text input)'],
                    'correct_answer': str(pick.get('answer','')).strip()
                }
        except Exception:
            pass
        text = f"What is {term}?"
        if prompt and prompt.strip():
            text = f"In the context of {prompt}, what is {term}?"
        return {
            'text': text,
            'question_type': 'identification',
            'options': ['Answer field (text input)'],
            'correct_answer': definition
        }

    if question_type == 'true_false':
        try:
            import pandas as pd
            import os
            base = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
            tf_path = os.path.join(base, 'it_olympics_true_false.csv')
            if os.path.exists(tf_path):
                dftf = pd.read_csv(tf_path, on_bad_lines='skip', engine='python')
                # Search for true/false questions matching prompt
                if prompt and prompt.strip():
                    prompt_lower = prompt.lower()
                    relevant_questions = []
                    for idx, row in dftf.iterrows():
                        score = 0
                        statement = str(row.get('statement', '')).lower()
                        topic = str(row.get('topic', '')).lower()
                        if any(word in topic for word in prompt_lower.split()):
                            score += 10
                        if any(word in statement for word in prompt_lower.split()):
                            score += 5
                        if score > 0:
                            relevant_questions.append((score, idx, row))
                    
                    if relevant_questions:
                        random.shuffle(relevant_questions)
                        pick = relevant_questions[0][2]
                    else:
                        pick = dftf.sample(n=1).iloc[0]
                else:
                    pick = dftf.sample(n=1).iloc[0]
                return {
                    'text': str(pick.get('statement','')).strip(), 
                    'question_type': 'true_false', 
                    'options': ['True', 'False'],
                    'correct_answer': 'True' if str(pick.get('answer','True')).strip().lower()=='true' else 'False'
                }
        except Exception:
            pass
        # Create a simple true statement using definition presence
        statement_true = f"{term} is {definition}" if definition else f"{term} is a concept in computing"
        # Occasionally flip to false by swapping definition
        make_false = random.random() < 0.5
        if make_false and def_col in df.columns and len(df) > 1:
            alt = None
            try:
                alt = df[df[term_col] != row[term_col]].sample(n=1, random_state=random.randint(0, 10_000)).iloc[0]
            except Exception:
                pass
            if alt is not None:
                statement = f"{term} is {str(alt.get(def_col, ''))}"
                return {
                    'text': statement, 
                    'question_type': 'true_false', 
                    'options': ['True', 'False'],
                    'correct_answer': 'False'
                }
        return {
            'text': statement_true, 
            'question_type': 'true_false', 
            'options': ['True', 'False'],
            'correct_answer': 'True'
        }

    if question_type == 'enumeration':
        try:
            import pandas as pd
            import os
            base = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
            en_path = os.path.join(base, 'it_olympics_enumeration.csv')
            if os.path.exists(en_path):
                dfen = pd.read_csv(en_path, on_bad_lines='skip', engine='python')
                # Search for enumeration questions matching prompt
                if prompt and prompt.strip():
                    prompt_lower = prompt.lower()
                    relevant_questions = []
                    for idx, row in dfen.iterrows():
                        score = 0
                        prompt_text = str(row.get('prompt', '')).lower()
                        topic = str(row.get('topic', '')).lower()
                        if any(word in topic for word in prompt_lower.split()):
                            score += 10
                        if any(word in prompt_text for word in prompt_lower.split()):
                            score += 5
                        if score > 0:
                            relevant_questions.append((score, idx, row))
                    
                    if relevant_questions:
                        random.shuffle(relevant_questions)
                        pick = relevant_questions[0][2]
                    else:
                        pick = dfen.sample(n=1).iloc[0]
                else:
                    pick = dfen.sample(n=1).iloc[0]
                answers = [a.strip() for a in str(pick.get('answers','')).split(';') if a.strip()]
                return {
                    'text': str(pick.get('prompt','')).strip(), 
                    'question_type': 'enumeration', 
                    'options': ['List items (separated by commas)'],
                    'correct_answer': answers
                }
        except Exception:
            pass
        # Return 3 related items from the same column as term
        col_for_items = term_col
        items = [str(v).strip() for v in df[col_for_items].dropna().astype(str).tolist()]
        random.shuffle(items)
        answers = [i for i in items[:3] if i]
        text = f"List three items related to {prompt or term}."
        return {
            'text': text, 
            'question_type': 'enumeration', 
            'options': ['List items (separated by commas)'],
            'correct_answer': answers
        }

    if question_type == 'coding':
        # Use problems from IT Olympics coding CSV
        try:
            import pandas as pd
            import os
            base = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
            new_path = os.path.join(base, 'it_olympics_coding.csv')
            if os.path.exists(new_path):
                dfcode = pd.read_csv(new_path, on_bad_lines='skip', engine='python')
                if not dfcode.empty:
                # Search for coding problems matching prompt
                    selected_problem = None
                    
                    # Remove variant suffixes like "(Variant 1)" from prompt
                    clean_prompt = prompt
                    if prompt and prompt.strip():
                        import re
                        clean_prompt = re.sub(r'\s*\(Variant\s+\d+\)', '', prompt).strip()
                    
                    if clean_prompt and clean_prompt.strip():
                        prompt_lower = clean_prompt.lower()
                        scores = []
                        for idx, row in dfcode.iterrows():
                            score = 0
                            problem = str(row.get('problem_statement', '')).lower()
                            topic = str(row.get('topic', '')).lower()
                            language = str(row.get('language', '')).lower()
                            # Higher score for exact language match, then partial match
                            prompt_words = prompt_lower.split()
                            
                            # Handle language aliases
                            language_aliases = {
                                'c++': ['cpp', 'c++', 'c plus plus'],
                                'c': ['c'],
                                'python': ['python', 'py'],
                                'java': ['java']
                            }
                            
                            # Check for exact match or alias match
                            exact_match = False
                            for lang_key, aliases in language_aliases.items():
                                if language == lang_key and any(alias in prompt_words for alias in aliases):
                                    score += 50  # Exact match gets highest score
                                    exact_match = True
                                    break
                            
                            if not exact_match:
                                # Check for partial matches, but avoid C matching C++
                                if 'c' in prompt_words and language == 'c++':
                                    score += 0  # Don't match C to C++
                                elif 'c++' in prompt_words and language == 'c':
                                    score += 0  # Don't match C++ to C
                                elif any(word in language for word in prompt_words):
                                    score += 15
                                
                                # Enhanced concept matching with specific keywords
                                concept_keywords = {
                                    'if': ['if', 'else', 'elif', 'conditional', 'condition'],
                                    'loop': ['loop', 'for', 'while', 'iteration', 'iterate'],
                                    'function': ['function', 'def', 'method', 'procedure'],
                                    'array': ['array', 'list', 'vector', 'collection'],
                                    'string': ['string', 'text', 'char', 'character'],
                                    'algorithm': ['algorithm', 'sort', 'search', 'binary', 'linear'],
                                    'grade': ['grade', 'score', 'mark', 'rating'],
                                    'factorial': ['factorial', 'fact'],
                                    'even': ['even', 'odd', 'parity'],
                                    'max': ['max', 'maximum', 'largest', 'biggest'],
                                    'min': ['min', 'minimum', 'smallest']
                                }
                                
                                # Check for programming concept matches with higher precision
                                for concept, keywords in concept_keywords.items():
                                    if any(keyword in prompt_lower for keyword in keywords):
                                        # If the problem statement contains the exact concept, give high bonus
                                        if any(keyword in problem for keyword in keywords):
                                            score += 25  # Higher bonus for exact concept match
                                        # If the topic matches, give points
                                        if concept in topic:
                                            score += 15
                                        # Special handling for specific concepts
                                        if concept == 'grade' and 'grade' in prompt_lower and 'grade' in problem:
                                            score += 30  # Extra bonus for exact grade match
                                        if concept == 'factorial' and 'factorial' in prompt_lower and 'factorial' in problem:
                                            score += 30  # Extra bonus for exact factorial match
                                
                        if any(word in topic for word in prompt_lower.split()):
                            score += 10
                        if any(word in problem for word in prompt_lower.split()):
                            score += 5
                            
                            # Add random factor to ensure variety when generating multiple questions
                            import random
                            random_factor = random.uniform(0, 5)
                            score += random_factor
                            
                        scores.append((score, idx))
                    scores.sort(reverse=True)
                    if scores and scores[0][0] > 0:
                        selected_problem = dfcode.iloc[scores[0][1]]
                    
                    # If no match found or no prompt, select random
                    if selected_problem is None:
                        import random
                        # If we have a specific language request, try to find that language first
                        if clean_prompt and any(word in clean_prompt.lower() for word in ['python', 'py', 'c', 'c++', 'cpp', 'java']):
                            lang_filtered = dfcode[dfcode['language'].str.lower().isin(['python', 'c', 'c++', 'java'])]
                            if not lang_filtered.empty:
                                selected_problem = lang_filtered.sample(n=1).iloc[0]
                        else:
                            selected_problem = dfcode.sample(n=1).iloc[0]
                    else:
                        selected_problem = dfcode.sample(n=1).iloc[0]
                    
                    # Create sample code with hints
                    hints = selected_problem.get('hints', '')
                    sample_code = f"# Hints: {hints}\n# Write your code below:" if hints else "# Write your code below:"
                    
                    return {
                        'text': selected_problem['problem_statement'],
                        'question_type': 'coding',
                        'sample_code': sample_code,
                        'expected_output': selected_problem['unit_tests'],  # Include unit tests
                        'language': selected_problem['language'],
                        'topic': selected_problem['topic']
                    }
            target_cols = {'problem_statement', 'language', 'sample_code'}
            candidates = []
            for dsm, dfm in frames:
                cols_set = set(str(c).lower() for c in dfm.columns)
                if {'problem_statement', 'language'}.issubset(cols_set):
                    candidates.append((dsm, dfm))
            if candidates:
                dsm, dfm = candidates[0]
                # Filter by language or prompt keywords if possible
                lang_col = next((c for c in dfm.columns if str(c).lower() == 'language'), None)
                ps_col = next((c for c in dfm.columns if str(c).lower() == 'problem_statement'), None)
                sc_col = next((c for c in dfm.columns if str(c).lower() == 'sample_code'), None)
                dfsel = dfm
                try:
                    if prompt and lang_col in dfm.columns:
                        common_langs = ['python', 'java', 'c++', 'c', 'javascript', 'sql']
                        for kw in common_langs:
                            if kw in str(prompt).lower():
                                df_lang = dfm[dfm[lang_col].astype(str).str.lower().str.contains(kw, na=False)]
                                if not df_lang.empty:
                                    dfsel = df_lang
                                    break
                    if prompt and ps_col in dfm.columns and dfsel is dfm:
                        df_ps = dfm[dfm[ps_col].astype(str).str.contains(str(prompt), case=False, na=False)]
                        if not df_ps.empty:
                            dfsel = df_ps
                except Exception:
                    pass
                picked = dfsel.sample(n=1, random_state=random.randint(0, 10_000)).iloc[0]
                text = str(picked.get(ps_col, '')).strip() or f"Write a program related to {prompt or 'coding'}"
                result = {'text': text, 'question_type': 'coding'}
                if sc_col in dfm.columns:
                    result['sample_code'] = str(picked.get(sc_col, '')).strip()
                return result
        except Exception:
            pass
        # Generic fallback if dataset not found
        text = f"Write a program that reads input and produces the expected output related to {prompt or term}."
        return {'text': text, 'question_type': 'coding'}

    # Default fallback to identification
    return {'text': f"What is {term}?", 'question_type': 'identification', 'correct_answer': definition}

@main.route('/execute-code', methods=['POST'])
def execute_code():
    """
    Execute code in various programming languages and return the output.
    """
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        language = data.get('language', '').lower()
        user_inputs = data.get('inputs', [])  # List of user inputs for interactive programs
        
        # Validate and sanitize user inputs
        if user_inputs:
            import re
            sanitized_inputs = []
            for user_input in user_inputs:
                if len(user_input) > 1000:
                    return jsonify({'success': False, 'error': 'Input too long (max 1000 characters)'})
                # Remove potentially dangerous characters but keep most printable characters
                sanitized_input = re.sub(r'[^\w\s\-.,!?@#$%^&*()+=\[\]{}|\\:";\'<>?/~`]', '', user_input)
                sanitized_inputs.append(sanitized_input)
            user_inputs = sanitized_inputs
        
        if not code:
            return jsonify({'success': False, 'error': 'No code provided'})
        
        if not language:
            return jsonify({'success': False, 'error': 'No language specified'})
        
        # Execute code based on language
        if language == 'python':
            result = execute_python_code(code, user_inputs)
        elif language == 'java':
            result = execute_java_code(code, user_inputs)
        elif language == 'cpp':
            result = execute_cpp_code(code, user_inputs)
        elif language == 'c':
            result = execute_c_code(code, user_inputs)
        elif language in ['c#','csharp','cs']:
            result = execute_csharp_code(code, user_inputs)
        else:
            return jsonify({'success': False, 'error': f'Unsupported language: {language}'})
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Execution error: {str(e)}'})

@main.route('/check-input-needed', methods=['POST'])
def check_input_needed():
    """
    Check if code needs input and return information about what input is expected.
    """
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        language = data.get('language', '').lower()
        
        if not code or not language:
            return jsonify({'needs_input': False})
        
        # Check for input patterns based on language
        needs_input = False
        input_prompt = ""
        
        if language == 'python':
            import re
            input_matches = re.findall(r'input\(["\']([^"\']*)["\']?\)', code)
            if input_matches:
                needs_input = True
                input_prompt = input_matches[0] if input_matches[0] else "Enter input:"
        elif language == 'java':
            if 'scanner' in code.lower() and ('nextint' in code.lower() or 'nextline' in code.lower() or 'nextdouble' in code.lower()):
                needs_input = True
                input_prompt = "Enter input:"
        elif language in ['cpp', 'c']:
            if any(pattern in code.lower() for pattern in ['cin', 'scanf', 'fgets', 'getline']):
                needs_input = True
                input_prompt = "Enter input:"
        elif language in ['c#','csharp','cs']:
            if any(pattern in code.lower() for pattern in ['console.readline', 'readline(']):
                needs_input = True
                input_prompt = "Enter input:"
        
        return jsonify({
            'needs_input': needs_input,
            'prompt': input_prompt
        })
        
    except Exception as e:
        return jsonify({'needs_input': False, 'error': str(e)})

def execute_python_code(code, user_inputs=[]):
    """Execute Python code and return output."""
    try:
        # Security check: prevent dangerous operations (but allow input())
        dangerous_patterns = [
            'import os', 'import sys', 'import subprocess', 'import shutil',
            '__import__', 'eval(', 'exec(', 'open(', 'file(',
            'raw_input(', 'compile('
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern in code_lower:
                return {
                    'success': False,
                    'output': '',
                    'error': f'Security restriction: {pattern} is not allowed'
                }
        
        # Add basic static analysis to warn about undefined variables and typos (non-blocking)
        import ast
        try:
            tree = ast.parse(code)
            defined_names = set()
            used_names = set()
            param_names = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    defined_names.add(node.name)
                    # Get function parameters
                    for arg in node.args.args:
                        param_names.add(arg.arg)
                    # Get variables defined within the function
                    for child in ast.walk(node):
                        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                            defined_names.add(child.id)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    used_names.add(node.id)
            
            # Check for undefined variables (used but not defined)
            all_defined = defined_names | param_names
            undefined_vars = used_names - all_defined
            # Remove built-in Python functions
            builtins = {'print', 'input', 'int', 'str', 'float', 'bool', 'len', 'range', 'list', 'dict', 'set', 'tuple', 'abs', 'max', 'min', 'sum', 'sorted', 'reversed', 'enumerate', 'zip', 'open', 'type', 'isinstance', 'hasattr', 'getattr', 'setattr', 'delattr', 'all', 'any', 'iter', 'next', 'filter', 'map', 'reduce'}
            undefined_vars = undefined_vars - builtins
            
            # Look for common typos (similar variable names)
            if undefined_vars:
                suspicious_vars = []
                for var in undefined_vars:
                    # Check if there's a similar defined variable
                    for defined in all_defined:
                        # Check if the undefined var is just a plural/singular variant
                        if var == defined + 's' or var == defined[:-1] or defined == var + 's':
                            suspicious_vars.append(f"{var} (did you mean '{defined}'?)")
                            break
                    else:
                        suspicious_vars.append(var)
                
                analysis_warning = ''
                if suspicious_vars:
                    analysis_warning = '⚠️ Potential undefined variable(s):\n'
                    for var in suspicious_vars:
                        analysis_warning += f'  • {var}\n'
                    analysis_warning += '\nTip: Make sure all variable names are spelled correctly throughout your code.'
        except SyntaxError:
            # If we can't parse, just continue with execution
            pass
        except Exception:
            # If analysis fails, just continue with execution
            pass
        
        # Check if code needs input (has input()) but no input provided
        needs_input = 'input(' in code
        if needs_input and not user_inputs:
            return {
                'success': False,
                'output': '',
                'error': '⚠️ This code requires input but none was provided.\n\nTip: Enter input in the input field above the "Run Code" button.'
            }
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        try:
            # Combine all inputs with newlines
            combined_input = '\n'.join(user_inputs) if user_inputs else ''
            
            # Execute the Python code with restricted environment and input
            result = subprocess.run(
                ['python', temp_file],
                capture_output=True,
                text=True,
                timeout=10,  # 10 second timeout
                cwd=tempfile.gettempdir(),
                env={'PYTHONPATH': '', 'PATH': os.environ.get('PATH', '')},  # Restricted environment
                input=combined_input  # Provide all user inputs
            )
            
            output = result.stdout
            error = result.stderr
            
            if result.returncode == 0:
                # Append non-blocking analysis warnings if available
                try:
                    if analysis_warning:
                        output = (output or '') + ('\n\n' + analysis_warning)
                except Exception:
                    pass
                return {
                    'success': True,
                    'output': output or 'Code executed successfully.',
                    'error': None
                }
            else:
                # Check for common input-related errors
                if 'EOFError' in error or 'NoSuchElementException' in error:
                    return {
                        'success': False,
                        'output': output,
                        'error': f'Input required: {error}\n\nTip: Enter input in the input field above the "Run Code" button.'
                    }
                else:
                    return {
                        'success': False,
                        'output': output,
                        'error': error or 'Code execution failed'
                    }
                
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': 'Code execution timed out (10 seconds)'
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Execution error: {str(e)}'
        }

def execute_java_code(code, user_inputs=[]):
    """Execute Java code and return output."""
    try:
        # Security check: prevent dangerous operations
        dangerous_patterns = [
            'Runtime.getRuntime()', 'ProcessBuilder', 'System.exit',
            'FileInputStream', 'FileOutputStream', 'FileReader', 'FileWriter',
            'Socket', 'ServerSocket', 'URL', 'URLConnection'
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    'success': False,
                    'output': '',
                    'error': f'Security restriction: {pattern} is not allowed'
                }
        
        # Extract class name from code or use a default
        class_name = 'Solution'
        if 'public class' in code:
            import re
            match = re.search(r'public class (\w+)', code)
            if match:
                class_name = match.group(1)
        
        # Create temporary directory for Java files
        temp_dir = tempfile.mkdtemp()
        java_file = os.path.join(temp_dir, f'{class_name}.java')
        
        try:
            # Write Java code to file
            with open(java_file, 'w') as f:
                f.write(code)
            
            # Compile Java code
            compile_result = subprocess.run(
                ['javac', java_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir
            )
            
            if compile_result.returncode != 0:
                error_msg = compile_result.stderr
                # Make error messages more user-friendly
                if 'cannot find symbol' in error_msg or 'variable' in error_msg.lower():
                    error_msg = '⚠️ Compilation Error: Check for undefined variables\n\n' + error_msg
                    error_msg += '\n\nTip: Make sure all variable names are spelled correctly.'
                else:
                    error_msg = '⚠️ Compilation Error:\n\n' + error_msg
                
                return {
                    'success': False,
                    'output': '',
                    'error': error_msg
                }
            
            # Check if code needs input (has Scanner) but no input provided
            needs_input = 'scanner' in code.lower() and ('nextint' in code.lower() or 'nextline' in code.lower() or 'nextdouble' in code.lower())
            if needs_input and not user_inputs:
                return {
                    'success': False,
                    'awaiting_input': True,
                    'output': '',
                    'error': 'Input required. Provide input lines and run again.'
                }
            
            # Combine all inputs with newlines
            combined_input = '\n'.join(user_inputs) if user_inputs else ''
            
            # Execute compiled Java code with input
            exec_result = subprocess.run(
                ['java', class_name],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir,
                input=combined_input  # Provide all user inputs
            )
            
            output = exec_result.stdout
            error = exec_result.stderr
            
            if exec_result.returncode == 0:
                return {
                    'success': True,
                    'output': output or 'Code executed successfully.',
                    'error': None
                }
            else:
                # Check for common input-related errors
                if 'NoSuchElementException' in error or 'InputMismatchException' in error:
                    return {
                        'success': False,
                        'awaiting_input': True,
                        'output': output,
                        'error': 'Input required. Provide next input lines and run again.'
                    }
                else:
                    return {
                        'success': False,
                        'output': output,
                        'error': error or 'Code execution failed'
                    }
                
        finally:
            # Clean up temporary directory
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': 'Code execution timed out (10 seconds)'
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Execution error: {str(e)}'
        }

def execute_cpp_code(code, user_inputs=[]):
    """Execute C++ code and return output."""
    try:
        # Security check: prevent dangerous operations
        dangerous_patterns = [
            '#include <fstream>', '#include <cstdlib>', '#include <unistd.h>',
            'system(', 'exec', 'fork', 'popen', 'fopen', 'fstream',
            'ifstream', 'ofstream', 'FILE*'
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    'success': False,
                    'output': '',
                    'error': f'Security restriction: {pattern} is not allowed'
                }
        
        # Create temporary directory for C++ files
        temp_dir = tempfile.mkdtemp()
        cpp_file = os.path.join(temp_dir, 'main.cpp')
        exe_file = os.path.join(temp_dir, 'main')
        
        try:
            # Write C++ code to file
            with open(cpp_file, 'w') as f:
                f.write(code)
            
            # Compile C++ code
            compile_result = subprocess.run(
                ['g++', '-o', exe_file, cpp_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir
            )
            
            if compile_result.returncode != 0:
                error_msg = compile_result.stderr
                # Make error messages more user-friendly
                if 'not declared' in error_msg or 'variable' in error_msg.lower():
                    error_msg = '⚠️ Compilation Error: Check for undefined variables\n\n' + error_msg
                    error_msg += '\n\nTip: Make sure all variable names are spelled correctly.'
                else:
                    error_msg = '⚠️ Compilation Error:\n\n' + error_msg
                
                return {
                    'success': False,
                    'output': '',
                    'error': error_msg
                }
            
            # Check if code needs input (has scanf/cin) but no input provided
            needs_input = any(pattern in code.lower() for pattern in ['cin', 'scanf'])
            if needs_input and not user_inputs:
                return {
                    'success': False,
                    'awaiting_input': True,
                    'output': '',
                    'error': 'Input required. Provide input lines and run again.'
                }
            
            # Combine all inputs with newlines
            combined_input = '\n'.join(user_inputs) if user_inputs else ''
            
            # Execute compiled C++ code with input
            exec_result = subprocess.run(
                [exe_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir,
                input=combined_input  # Provide all user inputs
            )
            
            output = exec_result.stdout
            error = exec_result.stderr
            
            if exec_result.returncode == 0:
                return {
                    'success': True,
                    'output': output or 'Code executed successfully.',
                    'error': None
                }
            else:
                # Check if it's an input-related error for C++
                if 'EOFError' in error or 'NoSuchElementException' in error or 'scanf' in error.lower():
                    return {
                        'success': False,
                        'awaiting_input': True,
                        'output': output,
                        'error': 'Input required. Provide next input lines and run again.'
                    }
                else:
                    return {
                        'success': False,
                        'output': output,
                        'error': error or 'Code execution failed'
                    }
                
        finally:
            # Clean up temporary directory
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': 'Code execution timed out (10 seconds)'
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Execution error: {str(e)}'
        }

def execute_c_code(code, user_inputs=[]):
    """Execute C code and return output."""
    try:
        # Security check: prevent dangerous operations
        dangerous_patterns = [
            '#include <stdlib.h>', '#include <unistd.h>', '#include <fcntl.h>',
            'system(', 'exec', 'fork', 'popen', 'fopen', 'FILE*'
        ]
        
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    'success': False,
                    'output': '',
                    'error': f'Security restriction: {pattern} is not allowed'
                }
        
        # Create temporary directory for C files
        temp_dir = tempfile.mkdtemp()
        c_file = os.path.join(temp_dir, 'main.c')
        exe_file = os.path.join(temp_dir, 'main')
        
        try:
            # Write C code to file
            with open(c_file, 'w') as f:
                f.write(code)
            
            # Compile C code
            compile_result = subprocess.run(
                ['gcc', '-o', exe_file, c_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir
            )
            
            if compile_result.returncode != 0:
                error_msg = compile_result.stderr
                # Make error messages more user-friendly
                if 'not declared' in error_msg or 'variable' in error_msg.lower():
                    error_msg = '⚠️ Compilation Error: Check for undefined variables\n\n' + error_msg
                    error_msg += '\n\nTip: Make sure all variable names are spelled correctly.'
                else:
                    error_msg = '⚠️ Compilation Error:\n\n' + error_msg
                
                return {
                    'success': False,
                    'output': '',
                    'error': error_msg
                }
            
            # Check if code needs input (has scanf) but no input provided
            needs_input = 'scanf' in code.lower()
            if needs_input and not user_inputs:
                return {
                    'success': False,
                    'awaiting_input': True,
                    'output': '',
                    'error': 'Input required. Provide input lines and run again.'
                }
            
            # Combine all inputs with newlines
            combined_input = '\n'.join(user_inputs) if user_inputs else ''
            
            # Execute compiled C code with input
            exec_result = subprocess.run(
                [exe_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=temp_dir,
                input=combined_input  # Provide all user inputs
            )
            
            output = exec_result.stdout
            error = exec_result.stderr
            
            if exec_result.returncode == 0:
                return {
                    'success': True,
                    'output': output or 'Code executed successfully.',
                    'error': None
                }
            else:
                # Check if it's an input-related error for C
                if 'EOFError' in error or 'NoSuchElementException' in error or 'scanf' in error.lower():
                    return {
                        'success': False,
                        'awaiting_input': True,
                        'output': output,
                        'error': 'Input required. Provide next input lines and run again.'
                    }
                else:
                    return {
                        'success': False,
                        'output': output,
                        'error': error or 'Code execution failed'
                    }
                
        finally:
            # Clean up temporary directory
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': 'Code execution timed out (10 seconds)'
        }

def execute_csharp_code(code, user_inputs=[]):
    """Execute C# code and return output. Requires .NET SDK (csc) or dotnet."""
    try:
        # Basic security check
        dangerous_patterns = [
            'System.IO', 'System.Net', 'Process.Start', 'File.', 'Directory.', 'Socket', 'HttpClient'
        ]
        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                return {
                    'success': False,
                    'output': '',
                    'error': f'Security restriction: {pattern} is not allowed'
                }

        temp_dir = tempfile.mkdtemp()
        cs_file = os.path.join(temp_dir, 'Program.cs')
        exe_file = os.path.join(temp_dir, 'Program.exe')

        # If code does not define a Program/Main, wrap it
        wrapped_code = code
        if 'static void Main' not in code and 'static int Main' not in code:
            wrapped_code = (
                'using System;\nusing System.Linq;\nusing System.Collections.Generic;\n'
                'public class Program {\n'
                '    public static void Main(string[] args) {\n'
                f'        {code}\n'
                '    }\n'
                '}'
            )

        with open(cs_file, 'w', encoding='utf-8') as f:
            f.write(wrapped_code)

        # Try compile with csc (Roslyn); if not available, fallback to dotnet new+run
        compile_result = None
        try:
            compile_result = subprocess.run(['csc', '/nologo', cs_file, '/out:' + exe_file], capture_output=True, text=True, timeout=20, cwd=temp_dir)
            use_dotnet = False
        except FileNotFoundError:
            use_dotnet = True

        if use_dotnet:
            # Create a minimal console project and replace Program.cs
            try:
                init_result = subprocess.run(['dotnet', 'new', 'console', '--force', '--name', 'App', '--output', temp_dir], capture_output=True, text=True, timeout=30)
                if init_result.returncode != 0:
                    return {
                        'success': False,
                        'output': '',
                        'error': 'C# toolchain not found. Please install .NET SDK to run C# code.'
                    }
                # Overwrite Program.cs
                prog_path = os.path.join(temp_dir, 'Program.cs')
                with open(prog_path, 'w', encoding='utf-8') as f:
                    f.write(wrapped_code)
                # Restore packages
                subprocess.run(['dotnet', 'restore'], capture_output=True, text=True, timeout=30, cwd=temp_dir)
                # Build then execute with inputs (avoid missing exe errors)
                build_result = subprocess.run(['dotnet', 'build', '-c', 'Debug'], capture_output=True, text=True, timeout=40, cwd=temp_dir)
                if build_result.returncode != 0:
                    return { 'success': False, 'output': '', 'error': build_result.stderr or 'C# build failed' }
                combined_input = '\n'.join(user_inputs) if user_inputs else ''
                exec_result = subprocess.run(['dotnet', 'run', '-c', 'Debug'], capture_output=True, text=True, timeout=30, cwd=temp_dir, input=combined_input)
                if exec_result.returncode == 0:
                    return { 'success': True, 'output': exec_result.stdout or 'Code executed successfully.', 'error': None }
                else:
                    return { 'success': False, 'output': exec_result.stdout, 'error': exec_result.stderr or 'Code execution failed' }
            except Exception as e:
                return { 'success': False, 'output': '', 'error': f'C# execution error: {str(e)}' }

        if compile_result.returncode != 0:
            return {
                'success': False,
                'output': '',
                'error': '⚠️ Compilation Error:\n\n' + (compile_result.stderr or compile_result.stdout)
            }

        # Combine inputs
        combined_input = '\n'.join(user_inputs) if user_inputs else ''

        # Execute
        exec_cmd = [exe_file]
        exec_result = subprocess.run(exec_cmd, capture_output=True, text=True, timeout=10, cwd=temp_dir, input=combined_input)

        if exec_result.returncode == 0:
            return {
                'success': True,
                'output': exec_result.stdout or 'Code executed successfully.',
                'error': None
            }
        else:
            return {
                'success': False,
                'output': exec_result.stdout,
                'error': exec_result.stderr or 'Code execution failed'
            }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'output': '',
            'error': 'Code execution timed out (10 seconds)'
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Execution error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'output': '',
            'error': f'Execution error: {str(e)}'
        }


@main.route('/question/<int:question_id>/edit', methods=['GET'])
@admin_required
def edit_question_form(question_id):
    question = Question.query.get_or_404(question_id)
    return render_template('edit_question.html', question=question)

@main.route('/question/<int:question_id>/edit', methods=['POST'])
@admin_required
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    
    question.question_text = request.form.get('question_text')
    qtype = (question.question_type or '').lower()
    
    # Handle points
    try:
        points = int(request.form.get('points', 1))
        if points < 1:
            points = 1
        question.points = points
    except (ValueError, TypeError):
        question.points = 1
    
    if qtype == 'multiple_choice':
        options = request.form.getlist('options[]')
        question.set_options(options)
        question.correct_answer = request.form.get('correct_answer')
        question.sample_code = request.form.get('sample_code')
    
    if qtype == 'checkbox':
        options = request.form.getlist('options[]')
        question.set_options(options)
        correct_multi = request.form.getlist('correct_answer[]')
        if correct_multi:
            question.correct_answer = json.dumps(correct_multi)
        else:
            question.correct_answer = json.dumps([])
    
    if qtype == 'true_false':
        ca = request.form.get('correct_answer')
        question.correct_answer = 'True' if (ca and ca.lower() in ['true', 't', '1', 'yes']) else 'False'
    
    if qtype == 'coding':
        question.sample_code = request.form.get('sample_code')
        question.expected_output = request.form.get('expected_output')
        
    if qtype == 'identification':
        question.sample_code = request.form.get('sample_code')
        question.correct_answer = request.form.get('correct_answer')
    
    if qtype == 'enumeration':
        raw = request.form.get('correct_answer') or ''
        parts = [p.strip() for p in (raw.replace('\n', ',').split(',')) if p.strip()]
        question.correct_answer = json.dumps(parts)
    
    db.session.commit()
    flash('Question updated successfully!', 'success')
    return redirect(url_for('main.edit_form', form_id=question.form_id))


@main.route('/question/<int:question_id>/category', methods=['POST'])
@admin_required
def update_question_category(question_id):
    question = Question.query.get_or_404(question_id)
    category = request.form.get('category') or None
    if category and category not in QUESTION_CATEGORY_CHOICES:
        flash('Invalid category selected.', 'danger')
    else:
        question.category = category
        db.session.commit()
        flash('Question category updated.', 'success')
    return redirect(url_for('main.edit_form', form_id=question.form_id))


@main.route('/question/<int:question_id>/delete', methods=['POST'])
@admin_required
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    form_id = question.form_id
    
    db.session.delete(question)
    db.session.commit()
    
    return redirect(url_for('main.edit_form', form_id=form_id))

@main.route('/form/<int:form_id>/delete', methods=['POST'])
@admin_required
def delete_form(form_id):
    form = Form.query.get_or_404(form_id)
    
    # Delete all related data (cascade will handle questions and responses)
    db.session.delete(form)
    db.session.commit()
    
    flash('Form deleted successfully!', 'success')
    return redirect(url_for('main.index'))


@main.route('/form/<int:form_id>/upload', methods=['POST'])
@admin_required
def upload_form(form_id):
    form = Form.query.get_or_404(form_id)
    form.is_visible = True
    form.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Form uploaded and made visible to students.', 'success')
    return redirect(url_for('main.edit_form', form_id=form_id))


@main.route('/form/<int:form_id>/toggle-visibility', methods=['POST'])
@admin_required
def toggle_form_visibility(form_id):
    form = Form.query.get_or_404(form_id)
    form.is_visible = not form.is_visible
    
    status = "visible" if form.is_visible else "hidden"
    db.session.commit()
    
    flash(f'Form is now {status}!', 'success')
    return redirect(url_for('main.index'))

@main.route('/form/<int:form_id>/view', methods=['GET'])
def view_form(form_id):
    form = Form.query.get_or_404(form_id)
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Check if form is visible for non-admin users
    if not form.is_visible and user_role != 'admin':
        flash('This form is not currently available.', 'warning')
        return redirect(url_for('main.index'))
    
    # For students, check if they've already submitted this form
    if user_role == 'student':
        existing_response = Response.query.filter_by(
            form_id=form_id,
            submitted_by=user_id
        ).first()
        
        if existing_response:
            # Redirect to view their submission instead
            flash('You have already submitted this form. Redirecting to your submission...', 'info')
            return redirect(url_for('main.view_my_response', response_id=existing_response.id))
    
    questions = Question.query.filter_by(form_id=form_id).order_by(Question.order).all()
    # Record start time for speed badge
    try:
        from datetime import datetime
        session[f'form_start_{form_id}'] = datetime.utcnow().isoformat()
    except Exception:
        pass
    return render_template('view_form.html', form=form, questions=questions)

@main.route('/form/<int:form_id>/submit', methods=['POST'])
def submit_form(form_id):
    form = Form.query.get_or_404(form_id)
    
    # Check if form is visible for non-admin users
    if not form.is_visible and session.get('role') != 'admin':
        flash('This form is not currently available for submission.', 'warning')
        return redirect(url_for('main.index'))
    
    # Create a new response
    response = Response(form_id=form_id, submitted_by=session.get('user_id'))
    db.session.add(response)
    db.session.flush()  # To get the response ID
    
    # Compute duration (seconds) from when the form was opened
    duration_seconds = None
    try:
        from datetime import datetime
        start_iso = session.get(f'form_start_{form_id}')
        if start_iso:
            start_dt = datetime.fromisoformat(start_iso)
            duration_seconds = (datetime.utcnow() - start_dt).total_seconds()
            session[f'response_duration_{response.id}'] = duration_seconds
    except Exception:
        pass
    
    # Get all questions for this form
    questions = Question.query.filter_by(form_id=form_id).all()
    
    for question in questions:
        answer_text = ''
        is_correct = False
        explanation = None
        score_percentage = 0
        
        if question.question_type in ['multiple_choice', 'identification', 'coding', 'checkbox', 'true_false', 'enumeration']:
            if question.question_type == 'checkbox':
                # Multiple selections possible
                selections = request.form.getlist(f'question_{question.id}')
                answer_text = json.dumps(selections)
            elif question.question_type == 'enumeration':
                # Expect comma/newline separated entries in a textarea
                raw = request.form.get(f'question_{question.id}', '')
                # Normalize into list
                parts = [p.strip() for p in (raw.replace('\n', ',').split(',')) if p.strip()]
                answer_text = json.dumps(parts)
            else:
                answer_text = request.form.get(f'question_{question.id}')
            
            # Check if answer is correct
            if question.question_type in ['multiple_choice', 'identification', 'true_false'] and question.correct_answer:
                if question.question_type == 'identification':
                    # Use fuzzy matching for identification questions
                    is_correct, score_percentage, explanation = calculate_identification_score(
                        answer_text, question.correct_answer
                    )
                elif question.question_type == 'true_false':
                    # Normalize to capitalized True/False
                    normalized = None
                    if isinstance(answer_text, str):
                        low = answer_text.strip().lower() if answer_text else ''
                        if low in ['true', 't', '1', 'yes']:
                            normalized = 'True'
                        elif low in ['false', 'f', '0', 'no']:
                            normalized = 'False'
                    is_correct = (normalized or answer_text) == question.correct_answer
                    score_percentage = 100 if is_correct else 0
                else:
                    # Multiple choice questions use exact matching
                    is_correct = answer_text == question.correct_answer
                    score_percentage = 100 if is_correct else 0
            elif question.question_type == 'checkbox' and question.correct_answer:
                # Checkbox scoring: percentage = intersection / union (or by number of correct answers)
                try:
                    selected = set(json.loads(answer_text) if answer_text else [])
                except Exception:
                    selected = set()
                correct = set(question.get_correct_answers())
                if correct:
                    num_correct_selected = len(selected & correct)
                    num_incorrect_selected = len(selected - correct)
                    # Basic scoring: only correct selections count, penalize over-selections
                    raw = (num_correct_selected / len(correct)) * 100 if correct else 0
                    penalty = min(100, num_incorrect_selected * (100 / max(1, len(question.get_options()))))
                    score_percentage = max(0, round(raw - penalty))
                    is_correct = score_percentage == 100
                else:
                    score_percentage = 0
                    is_correct = False
            elif question.question_type == 'enumeration' and question.correct_answer:
                # Enumeration scoring with fuzzy matching per expected item
                # Score is the average of fuzzy scores (0-100) for best-matching provided items
                try:
                    provided_list = json.loads(answer_text) if answer_text else []
                    if isinstance(provided_list, str):
                        provided_list = [s.strip() for s in provided_list.replace('\n', ',').split(',') if s.strip()]
                    provided_list = [p for p in provided_list if isinstance(p, str) and p.strip()]
                except Exception:
                    provided_list = []
                expected_list = [c for c in question.get_correct_answers() if isinstance(c, str) and c.strip()]
                if expected_list:
                    used_idx = set()
                    total = 0.0
                    for expected in expected_list:
                        # Find best available provided item for this expected term
                        best = 0
                        best_j = None
                        for j, prov in enumerate(provided_list):
                            if j in used_idx:
                                continue
                            _, score, _ = calculate_identification_score(prov, expected)
                            if score > best:
                                best = score
                                best_j = j
                        if best_j is not None:
                            used_idx.add(best_j)
                        total += best
                    score_percentage = round(total / len(expected_list))
                    is_correct = score_percentage == 100
                else:
                    score_percentage = 0
                    is_correct = False
            
            # For coding questions, use custom evaluation system
            elif question.question_type == 'coding' and answer_text:
                is_correct, score_percentage, explanation = evaluate_code_with_custom_system(
                    code_answer=answer_text,
                    question_text=question.question_text,
                    question_unit_tests=question.expected_output,
                    interactive_inputs=None,
                    expected_outputs=None
                )
                print(f"Custom Code Evaluation for Question {question.id}:")
                print(f"Is correct: {is_correct}")
                print(f"Score percentage: {score_percentage}%")
                print(f"Explanation: {explanation}")
        
        # Calculate earned points based on question type and score percentage
        earned_points = 0
        if question.question_type in ['coding', 'identification', 'checkbox', 'enumeration'] and answer_text:
            # Percentage-based scoring
            earned_points = (score_percentage / 100) * question.points
        else:
            # Multiple choice questions use binary scoring
            earned_points = question.points if is_correct else 0
            
        answer = Answer(
            response_id=response.id,
            question_id=question.id,
            answer_text=answer_text,
            is_correct=is_correct,
            score_percentage=score_percentage,
            feedback=explanation
        )
        
        db.session.add(answer)
    
    db.session.commit()
    
    flash('Form submitted successfully!', 'success')
    # Redirect students to their own view page, admins to general view
    if session.get('role') == 'student':
        return redirect(url_for('main.view_my_response', response_id=response.id))
    else:
        return redirect(url_for('main.view_response', response_id=response.id))

@main.route('/form/<int:form_id>/responses', methods=['GET'])
@admin_required
def view_responses(form_id):
    form = Form.query.get_or_404(form_id)
    # Fetch responses for the form
    responses = Response.query.filter_by(form_id=form_id).order_by(Response.created_at.asc()).all()
    
    # Compute total possible points for the form
    form_questions = Question.query.filter_by(form_id=form_id).all()
    total_possible_points = sum(q.points for q in form_questions)
    question_points_by_id = {q.id: q.points for q in form_questions}
    
    # Build ranking entries
    ranking_entries = []
    for resp in responses:
        # Sum earned points across answers: percentage-of-question points
        earned_points = 0.0
        for ans in resp.answers:
            pts = question_points_by_id.get(ans.question_id, 0)
            earned_points += (float(ans.score_percentage or 0) / 100.0) * pts
        percentage = (earned_points / total_possible_points * 100.0) if total_possible_points > 0 else 0.0
        # Resolve student display name
        student_name = None
        try:
            if resp.submitted_by:
                for s in get_all_students():
                    if s.student_id == resp.submitted_by:
                        student_name = s.fullname or resp.submitted_by
                        break
        except Exception:
            student_name = resp.submitted_by
        ranking_entries.append({
            'response': resp,
            'earned_points': earned_points,
            'percentage': percentage,
            'created_at': resp.created_at,
            'student_name': student_name
        })
    
    # Sort by highest earned points, tie-breaker earliest created_at (faster)
    ranking_entries.sort(key=lambda e: (-e['earned_points'], e['created_at']))
    
    # Assign ranks (1-based), stable for ties that sort by time already
    for idx, entry in enumerate(ranking_entries, start=1):
        entry['rank'] = idx
    
    return render_template(
        'responses.html',
        form=form,
        rankings=ranking_entries,
        total_possible_points=total_possible_points
    )

@main.route('/form/<int:form_id>/responses/clear', methods=['POST'])
@admin_required
def clear_form_responses(form_id):
    """Delete all responses (and their answers) for the specified form."""
    form = Form.query.get_or_404(form_id)
    # Delete each response to ensure ORM cascades remove answers as well
    responses = Response.query.filter_by(form_id=form_id).all()
    for resp in responses:
        db.session.delete(resp)
    db.session.commit()
    flash('All responses for this form have been cleared.', 'success')
    return redirect(url_for('main.view_responses', form_id=form.id))

@main.route('/response/<int:response_id>', methods=['GET'])
def view_response(response_id):
    response = Response.query.get_or_404(response_id)
    form = Form.query.get_or_404(response.form_id)
    
    # Check if user is viewing their own response (student) or admin
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Students can only view their own responses
    if user_role == 'student' and response.submitted_by != user_id:
        flash('You can only view your own responses.', 'danger')
        return redirect(url_for('main.index'))
    
    # Compute overall earned points and percentage
    questions = Question.query.filter_by(form_id=form.id).all()
    total_possible_points = sum(q.points for q in questions) or 0
    q_points = {q.id: q.points for q in questions}
    earned_points = 0.0
    for ans in response.answers:
        pts = q_points.get(ans.question_id, 0)
        earned_points += (float(ans.score_percentage or 0) / 100.0) * pts
    overall_pct = (earned_points / total_possible_points * 100.0) if total_possible_points > 0 else 0.0
    
    # Determine duration from session if available
    duration_seconds = session.get(f'response_duration_{response.id}')
    try:
        duration_seconds = float(duration_seconds) if duration_seconds is not None else None
    except Exception:
        duration_seconds = None
    
    # Badge rules
    badges = []
    # High score badge at >= 80%
    if overall_pct >= 80.0:
        badges.append({'name': 'High Score', 'image': url_for('static', filename='images/high-score.png')})
    if overall_pct >= 50.0:
        badges.append({'name': 'Good Score', 'image': url_for('static', filename='images/average.png')})
    # Study more at <= 25%
    if overall_pct <= 25.0:
        badges.append({'name': 'Study More', 'image': url_for('static', filename='images/studymore.png')})
    # Speed badge: compute allowed total time = 60s per MC/ID, 300s per coding; award if allowed/actual >= 0.5
    mc_id_count = sum(1 for q in questions if q.question_type in ('multiple_choice', 'identification', 'checkbox', 'enumeration', 'true_false'))
    coding_count = sum(1 for q in questions if q.question_type == 'coding')
    allowed_total = (60 * mc_id_count) + (300 * coding_count)
    if duration_seconds is not None and duration_seconds > 0 and allowed_total > 0:
        speed_ratio = allowed_total / duration_seconds
        if speed_ratio >= 0.5:
            badges.append({'name': 'Speed', 'image': url_for('static', filename='images/speed.png')})
    
    # Resolve student display name
    student_id = response.submitted_by
    student_name = None
    try:
        if student_id:
            for s in get_all_students():
                if s.student_id == student_id:
                    student_name = s.fullname or student_id
                    break
    except Exception:
        student_name = student_id
    return render_template('view_response.html', form=form, response=response, overall_pct=overall_pct, badges=badges, student_name=student_name, student_id=student_id)

@main.route('/answer/<int:answer_id>/manual', methods=['POST'])
@admin_required
def manual_mark_answer(answer_id):
    """Allow admin to manually mark an answer correct/wrong or set a score percentage."""
    answer = Answer.query.get_or_404(answer_id)
    action = request.form.get('action')  # 'correct' | 'wrong' | None
    pct_raw = request.form.get('score_percentage')

    try:
        if action == 'correct':
            answer.is_correct = True
            answer.score_percentage = 100.0
        elif action == 'wrong':
            answer.is_correct = False
            answer.score_percentage = 0.0

        if pct_raw is not None and pct_raw != '':
            pct = float(pct_raw)
            if pct < 0:
                pct = 0.0
            if pct > 100:
                pct = 100.0
            answer.score_percentage = pct
            answer.is_correct = True if pct >= 99.5 else False

        db.session.commit()
        flash('Answer updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update answer: {e}', 'danger')

    return redirect(url_for('main.view_response', response_id=answer.response_id))

@main.route('/my-response/<int:response_id>', methods=['GET'])
@login_required
def view_my_response(response_id):
    """View-only page for students to see their submitted responses"""
    response = Response.query.get_or_404(response_id)
    form = Form.query.get_or_404(response.form_id)
    user_id = session.get('user_id')
    user_role = session.get('role')
    
    # Only allow students to view their own responses
    if user_role != 'student':
        flash('This page is only for students.', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if this is the student's own response
    if response.submitted_by != user_id:
        flash('You can only view your own responses.', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if form is visible
    if not form.is_visible and user_role != 'admin':
        flash('This form is not currently available.', 'warning')
        return redirect(url_for('main.index'))
    
    # Compute overall earned points and percentage
    questions = Question.query.filter_by(form_id=form.id).all()
    total_possible_points = sum(q.points for q in questions) or 0
    q_points = {q.id: q.points for q in questions}
    earned_points = 0.0
    for ans in response.answers:
        pts = q_points.get(ans.question_id, 0)
        earned_points += (float(ans.score_percentage or 0) / 100.0) * pts
    overall_pct = (earned_points / total_possible_points * 100.0) if total_possible_points > 0 else 0.0
    
    # Determine duration from session if available
    duration_seconds = session.get(f'response_duration_{response.id}')
    try:
        duration_seconds = float(duration_seconds) if duration_seconds is not None else None
    except Exception:
        duration_seconds = None
    
    # Badge rules
    badges = []
    if overall_pct >= 80.0:
        badges.append({'name': 'High Score', 'image': url_for('static', filename='images/high-score.png')})
    if overall_pct >= 50.0:
        badges.append({'name': 'Good Score', 'image': url_for('static', filename='images/average.png')})
    if overall_pct <= 25.0:
        badges.append({'name': 'Study More', 'image': url_for('static', filename='images/studymore.png')})
    
    # Speed badge calculation
    if duration_seconds is not None:
        allowed_time = 0
        for q in questions:
            if q.question_type in ['multiple_choice', 'identification', 'true_false', 'checkbox']:
                allowed_time += 60
            elif q.question_type == 'coding':
                allowed_time += 300
            elif q.question_type == 'enumeration':
                allowed_time += 120
        
        if allowed_time > 0 and duration_seconds <= allowed_time:
            speed_ratio = duration_seconds / allowed_time
            if speed_ratio <= 0.5:
                badges.append({'name': 'Speed', 'image': url_for('static', filename='images/speed.png')})
    
    # Get student info
    student_name = None
    student_id = response.submitted_by
    try:
        from app.models.users import get_all_students
        for s in get_all_students():
            if s.student_id == response.submitted_by:
                student_name = s.fullname or response.submitted_by
                break
    except Exception:
        student_name = response.submitted_by
    
    return render_template('view_response.html', form=form, response=response, overall_pct=overall_pct, badges=badges, student_name=student_name, student_id=student_id, is_student_view=True)

def detect_language_from_submission(code_answer: str, question_text: str = "") -> str:
    """Best-effort language detection for coding submissions without relying on user input."""
    snippet = (code_answer or "").strip()
    question_hint = (question_text or "").lower()
    if not snippet:
        return "python"

    lowered = snippet.lower()

    def contains(*phrases):
        return any(phrase in lowered for phrase in phrases if phrase)

    def regex(pattern: str, flags: int = 0):
        return re.search(pattern, snippet, flags | re.MULTILINE)

    # Strong C++ signals
    if contains('std::', 'using namespace std', 'cout <<', 'cin >>', 'vector<', '<vector>', 'template<'):
        return "cpp"
    if contains('#include'):
        if contains('iostream', 'std::', 'using namespace std', 'vector<'):
            return "cpp"
        return "c"

    # C# markers
    if contains('using system', 'console.write', 'console.writeline', 'using xunit', '[fact]'):
        return "c#"
    if regex(r'\bnamespace\s+[A-Za-z0-9_.]+\s*\{', re.IGNORECASE) and 'class' in lowered:
        return "c#"
    if contains('public class') and 'console.' in lowered:
        return "c#"

    # Java markers
    if contains('system.out.println', 'public static void main', 'import java.', '@test', 'package '):
        return "java"
    if regex(r'\bpublic\s+class\s+\w+', re.IGNORECASE) and contains('public static') and 'console.' not in lowered:
        return "java"

    # Bare C / C++ function definitions
    c_like_match = regex(
        r'^\s*(?:static\s+)?(?:inline\s+)?(?:int|long|float|double|char|short|void)\s+\*?\s*[A-Za-z_]\w*\s*\([^)]*\)\s*\{',
        re.IGNORECASE
    )
    if c_like_match:
        if contains('std::', 'using namespace std', 'vector<', 'cout', 'cin'):
            return "cpp"
        header = c_like_match.group(0).lower()
        if 'public' in header and 'class' in lowered:
            if 'console.' in lowered or 'using system' in lowered:
                return "c#"
            if 'system.out' in lowered or 'package ' in lowered:
                return "java"
        return "c"

    # Python & JavaScript
    if regex(r'^\s*def\s+\w+\s*\(', re.IGNORECASE):
        return "python"
    if regex(r'\bfunction\b', re.IGNORECASE) or contains('console.log', '=>'):
        return "javascript"

    # Fallback to question text hints
    if "python" in question_hint:
        return "python"
    if "c++" in question_hint or "cpp" in question_hint:
        return "cpp"
    if "c#" in question_hint:
        return "c#"
    if " java" in question_hint or question_hint.startswith("java"):
        return "java"
    if " javascript" in question_hint or "js" in question_hint:
        return "javascript"
    if " c " in question_hint or question_hint.startswith("c "):
        return "c"

    return "python"


def evaluate_code_with_custom_system(code_answer, question_text, question_unit_tests=None, interactive_inputs=None, expected_outputs=None):
    """Evaluate code using custom unit testing system and return (is_correct, score_percentage, explanation)."""
    try:
        from app.code_evaluator import code_evaluator
        
        language = detect_language_from_submission(code_answer, question_text)
        
        # Check if we have custom unit tests from the question
        print(f"DEBUG: question_unit_tests = '{question_unit_tests}' (type: {type(question_unit_tests)})")
        has_unit_tests = question_unit_tests and question_unit_tests.strip() and question_unit_tests.strip() != ""
        print(f"DEBUG: has_unit_tests = {has_unit_tests}")
        
        if has_unit_tests:
            # Use the question's own unit tests with the custom evaluator
            print(f"DEBUG: Using custom unit tests from question")
            is_correct, score, feedback = code_evaluator.evaluate_code_with_custom_tests(
                code_answer, question_unit_tests, language, interactive_inputs, expected_outputs
            )
        else:
            # No unit tests provided - delegate directly to AI evaluator so it
            # can use the full question text as context.
            print(f"DEBUG: No unit tests provided, delegating to AI evaluator with question context")
            is_correct, score, feedback = ai_evaluator.evaluate_code(
                code_answer,
                question_text,
                language,
                ""
            )
            
        return is_correct, score, feedback
        
    except Exception as e:
        print(f"Error evaluating code with custom system: {e}")
        import traceback
        traceback.print_exc()
        return False, 0, f"Code evaluation failed: {str(e)}"

def initialize_builtin_datasets():
    """Initialize built-in datasets from CSV files."""
    import os
    import pandas as pd
    
    # Define built-in IT Olympics datasets
    datasets_config = [
        {
            'name': 'IT Olympics Multiple Choice',
            'description': 'Multiple choice questions for IT Olympics topics',
            'filename': 'it_olympics_multiple_choice.csv'
        },
        {
            'name': 'IT Olympics True/False',
            'description': 'True/False questions for IT Olympics topics',
            'filename': 'it_olympics_true_false.csv'
        },
        {
            'name': 'IT Olympics Identification',
            'description': 'Identification questions for IT Olympics topics',
            'filename': 'it_olympics_identification.csv'
        },
        {
            'name': 'IT Olympics Enumeration',
            'description': 'Enumeration questions for IT Olympics topics',
            'filename': 'it_olympics_enumeration.csv'
        },
        {
            'name': 'IT Olympics Checkbox',
            'description': 'Checkbox questions for IT Olympics topics',
            'filename': 'it_olympics_checkbox.csv'
        },
        {
            'name': 'IT Olympics Coding',
            'description': 'Coding problems for IT Olympics topics',
            'filename': 'it_olympics_coding.csv'
        },
    ]
    
    # Get the datasets directory path
    datasets_dir = os.path.join(os.path.dirname(__file__), 'data', 'datasets')
    
    for config in datasets_config:
        # Check if dataset already exists in database
        existing = Dataset.query.filter_by(filename=config['filename'], is_builtin=True).first()
        if existing:
            continue
            
        file_path = os.path.join(datasets_dir, config['filename'])
        
        if os.path.exists(file_path):
            try:
                # Read CSV to get metadata
                df = pd.read_csv(file_path, on_bad_lines='skip', engine='python')
                
                # Get file info
                file_size = os.path.getsize(file_path)
                columns = df.columns.tolist()
                row_count = len(df)
                
                # Create dataset record
                dataset = Dataset(
                    name=config['name'],
                    description=config['description'],
                    filename=config['filename'],
                    file_path=file_path,
                    file_size=file_size,
                    row_count=row_count,
                    is_active=True,
                    is_builtin=True
                )
                dataset.set_columns(columns)
                
                db.session.add(dataset)
                
            except Exception as e:
                print(f"Error processing built-in dataset {config['filename']}: {e}")
    
    db.session.commit()

@main.route('/datasets', methods=['GET'])
@admin_required
def manage_datasets():
    """Display all built-in datasets for management."""
    # Initialize built-in datasets if they don't exist
    initialize_builtin_datasets()
    
    datasets = Dataset.query.filter_by(is_builtin=True).order_by(Dataset.name).all()
    return render_template('manage_datasets.html', datasets=datasets)

@main.route('/datasets/<int:dataset_id>/toggle', methods=['POST'])
@admin_required
def toggle_dataset_status(dataset_id):
    """Toggle dataset active status."""
    dataset = Dataset.query.get_or_404(dataset_id)
    dataset.is_active = not dataset.is_active
    db.session.commit()
    
    # Clear the AI question generator's dataset cache so changes take effect immediately
    try:
        from app.ai_question_generator import ai_question_generator
        ai_question_generator.datasets_cache = {}
    except Exception:
        pass
    
    status = "activated" if dataset.is_active else "deactivated"
    flash(f'Dataset "{dataset.name}" has been {status}!', 'success')
    return redirect(url_for('main.manage_datasets'))



def _get_form_analytics_data(form_id):
    """Compute analytics data for a form and return a dictionary."""
    form = Form.query.get_or_404(form_id)
    responses = Response.query.filter_by(form_id=form_id).all()
    questions = Question.query.filter_by(form_id=form_id).all()
    
    total_responses = len(responses)
    total_questions = len(questions)
    total_possible_points = sum(q.points for q in questions) if questions else 0
    
    response_stats = []
    for response in responses:
        earned_points = 0.0
        for answer in response.answers:
            question = next((q for q in questions if q.id == answer.question_id), None)
            if question:
                earned_points += (float(answer.score_percentage or 0) / 100.0) * question.points
        
        percentage = (earned_points / total_possible_points * 100.0) if total_possible_points > 0 else 0.0
        response_stats.append({
            'response_id': response.id,
            'earned_points': earned_points,
            'percentage': percentage,
            'created_at': response.created_at,
            'submitted_by': response.submitted_by
        })
    
    response_stats.sort(key=lambda x: x['percentage'], reverse=True)
    avg_score = sum(r['percentage'] for r in response_stats) / len(response_stats) if response_stats else 0
    
    question_stats = []
    response_ids = [r.id for r in responses]
    for question in questions:
        answers = [a for a in question.answers if a.response_id in response_ids]
        correct_count = sum(1 for a in answers if a.is_correct)
        total_answers = len(answers)
        accuracy = (correct_count / total_answers * 100) if total_answers > 0 else 0
        
        answer_breakdown = {}
        
        if question.question_type == 'multiple_choice':
            options = question.get_options()
            for i, option in enumerate(options):
                letter = chr(65 + i)
                count = sum(1 for a in answers if a.answer_text == option)
                answer_breakdown[letter] = {
                    'text': option,
                    'count': count,
                    'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                }
        
        elif question.question_type == 'checkbox':
            options = question.get_options()
            for i, option in enumerate(options):
                letter = chr(65 + i)
                count = 0
                for a in answers:
                    try:
                        selected = json.loads(a.answer_text) if a.answer_text else []
                        if option in selected:
                            count += 1
                    except Exception:
                        pass
                answer_breakdown[letter] = {
                    'text': option,
                    'count': count,
                    'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                }
        
        elif question.question_type == 'true_false':
            true_count = sum(1 for a in answers if a.answer_text == 'True')
            false_count = sum(1 for a in answers if a.answer_text == 'False')
            answer_breakdown = {
                'True': {
                    'text': 'True',
                    'count': true_count,
                    'percentage': (true_count / total_answers * 100) if total_answers > 0 else 0
                },
                'False': {
                    'text': 'False',
                    'count': false_count,
                    'percentage': (false_count / total_answers * 100) if total_answers > 0 else 0
                }
            }
        
        elif question.question_type == 'identification':
            answer_groups = {}
            for a in answers:
                answer_text = a.answer_text or ""
                key = answer_text[:20].lower().strip()
                answer_groups.setdefault(key, []).append(answer_text)
            
            for key, group in answer_groups.items():
                answer_breakdown[key] = {
                    'text': group[0][:30] + "..." if len(group[0]) > 30 else group[0],
                    'count': len(group),
                    'percentage': (len(group) / total_answers * 100) if total_answers > 0 else 0
                }
        
        elif question.question_type == 'enumeration':
            score_categories = {
                'Perfect (90-100%)': 0,
                'Good (70-89%)': 0,
                'Fair (50-69%)': 0,
                'Poor (0-49%)': 0
            }
            for a in answers:
                score = a.score_percentage or 0
                if score >= 90:
                    score_categories['Perfect (90-100%)'] += 1
                elif score >= 70:
                    score_categories['Good (70-89%)'] += 1
                elif score >= 50:
                    score_categories['Fair (50-69%)'] += 1
                else:
                    score_categories['Poor (0-49%)'] += 1
            for category, count in score_categories.items():
                if count > 0:
                    answer_breakdown[category] = {
                        'text': category,
                        'count': count,
                        'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                    }
        
        elif question.question_type == 'coding':
            score_categories = {
                'Perfect (100%)': 0,
                'Minor Flaw (90%)': 0,
                'Major Flaw (70%)': 0,
                'So-So (50%)': 0,
                'Effort (25%)': 0,
                'Zero (0%)': 0
            }
            for a in answers:
                score = a.score_percentage or 0
                if score == 100:
                    score_categories['Perfect (100%)'] += 1
                elif score == 90:
                    score_categories['Minor Flaw (90%)'] += 1
                elif score == 70:
                    score_categories['Major Flaw (70%)'] += 1
                elif score == 50:
                    score_categories['So-So (50%)'] += 1
                elif score == 25:
                    score_categories['Effort (25%)'] += 1
                else:
                    score_categories['Zero (0%)'] += 1
            for category, count in score_categories.items():
                if count > 0:
                    answer_breakdown[category] = {
                        'text': category,
                        'count': count,
                        'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                    }
        
        question_stats.append({
            'question_id': question.id,
            'question_text': question.question_text[:50] + "..." if len(question.question_text) > 50 else question.question_text,
            'question_type': question.question_type,
            'points': question.points,
            'total_answers': total_answers,
            'correct_answers': correct_count,
            'accuracy': accuracy,
            'answer_breakdown': answer_breakdown
        })
    
    question_stats.sort(key=lambda x: x['accuracy'])
    
    score_ranges = {
        '90-100': 0,
        '80-89': 0,
        '70-79': 0,
        '60-69': 0,
        '50-59': 0,
        '0-49': 0
    }
    for stat in response_stats:
        score = stat['percentage']
        if score >= 90:
            score_ranges['90-100'] += 1
        elif score >= 80:
            score_ranges['80-89'] += 1
        elif score >= 70:
            score_ranges['70-79'] += 1
        elif score >= 60:
            score_ranges['60-69'] += 1
        elif score >= 50:
            score_ranges['50-59'] += 1
        else:
            score_ranges['0-49'] += 1
    
    def infer_categories(question: Question) -> set:
        text = f"{question.question_text or ''} {question.sample_code or ''}".lower()
        cats = set()
        if any(k in text for k in ['cyber', 'security', 'xss', 'sql injection', 'encryption', 'malware']):
            cats.add('Cybersecurity')
        if any(k in text for k in ['digital electronics', 'logic gate', 'flip-flop', 'flip flop', 'verilog', 'binary', 'combinational', 'sequential circuit']):
            cats.add('Digital Electronics')
        if any(k in text for k in ['linux', 'bash', 'shell', 'systemd', 'apt', 'yum', 'cron']):
            cats.add('Linux Administration')
        if any(k in text for k in ['network', 'tcp', 'udp', 'ip address', 'subnet', 'router', 'switch', 'dns', 'dhcp']):
            cats.add('Networking')
        if any(k in text for k in ['robot', 'arduino', 'raspberry', 'ros', 'sensor', 'motor', 'servo']):
            cats.add('Robotics')
        if any(k in text for k in ['android', 'kotlin', 'android studio', 'apk', 'activity', 'fragment']):
            cats.add('Android App Development')
        if any(k in text for k in ['database', 'sql', 'mysql', 'postgres', 'sqlite', 'mongodb', 'nosql', 'index', 'join']):
            cats.add('Database')
        if 'java' in text:
            cats.add('Java')
        # c# matching: look for c# or csharp
        if 'c#' in text or 'csharp' in text:
            cats.add('C#')
        if 'python' in text or 'def ' in text and question.question_type == 'coding':
            cats.add('Python')
        if any(k in text for k in ['html', 'css', 'javascript', 'react', 'vue', 'web ' , 'frontend', 'front-end']):
            cats.add('Web Design')
        if 'esports' in text or 'tournament' in text or 'league' in text:
            cats.add('Esports')
        # C and C++
        if ' c++' in text or 'cpp' in text or '#include <' in text and 'using namespace std' in text:
            cats.add('C++')
        # crude C detection (avoid matching 'c ' in common words)
        if ' int main(' in text or '#include <stdio.h>' in text:
            cats.add('C')
        return cats

    # Precompute question -> categories (prefer manual selection)
    question_id_to_categories = {}
    for q in questions:
        if q.category:
            question_id_to_categories[q.id] = {q.category}
        else:
            inferred = infer_categories(q)
            question_id_to_categories[q.id] = inferred if inferred else {'General'}

    # Precompute total possible points per category
    categories_order = list(QUESTION_CATEGORY_CHOICES)
    category_total_points = {c: 0.0 for c in categories_order}
    for q in questions:
        for cat in question_id_to_categories.get(q.id, set()):
            if cat not in category_total_points:
                category_total_points[cat] = 0.0
                categories_order.append(cat)
            category_total_points[cat] += float(q.points or 0)

    # Compute per-response earned points per category
    from collections import defaultdict
    category_student_rows = {c: [] for c in categories_order}
    response_id_to_response = {r.id: r for r in responses}
    
    # Build a lookup for student information
    all_students = get_all_students()
    student_lookup = {}
    for s in all_students:
        student_lookup[s.student_id] = {
            'student_id': s.student_id,
            'fullname': s.fullname or s.student_id
        }

    for response in responses:
        per_cat_points = defaultdict(float)
        for answer in response.answers:
            q = next((qq for qq in questions if qq.id == answer.question_id), None)
            if not q:
                continue
            cats = question_id_to_categories.get(q.id, set())
            if not cats:
                continue
            earned = (float(answer.score_percentage or 0) / 100.0) * float(q.points or 0)
            for cat in cats:
                per_cat_points[cat] += earned
        # Convert to percentage per category
        for cat, earned_points in per_cat_points.items():
            total_cat_pts = category_total_points.get(cat, 0.0) or 0.0
            if total_cat_pts <= 0:
                continue
            percentage = (earned_points / total_cat_pts) * 100.0
            # Look up student information
            student_info = student_lookup.get(response.submitted_by, {})
            category_student_rows[cat].append({
                'submitted_by': student_info.get('fullname', response.submitted_by),
                'student_id': student_info.get('student_id', response.submitted_by),
                'percentage': percentage,
                'earned_points': earned_points,
                'response_id': response.id
            })

    # Sort each category by percentage desc
    for cat in categories_order:
        category_student_rows[cat].sort(key=lambda r: r['percentage'], reverse=True)

    category_leaders = {
        cat: rows for cat, rows in category_student_rows.items() if rows
    }

    return {
        'form': form,
        'total_responses': total_responses,
        'total_questions': total_questions,
        'total_possible_points': total_possible_points,
        'response_stats': response_stats,
        'question_stats': question_stats,
        'avg_score': avg_score,
        'score_ranges': score_ranges,
        'category_leaders': category_leaders,
        'categories_order': categories_order
    }


@main.route('/form/<int:form_id>/analytics', methods=['GET'])
@admin_required
def form_analytics(form_id):
    """Display analytics dashboard for a specific form."""
    data = _get_form_analytics_data(form_id)
    return render_template('form_analytics.html', **data)


@main.route('/form/<int:form_id>/analytics/pdf', methods=['GET'])
@admin_required
def download_form_analytics_pdf(form_id):
    """Generate and download a PDF report of the analytics."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.piecharts import Pie
        from reportlab.graphics import renderPDF
        from reportlab.lib import colors
    except ImportError:
        flash('PDF export requires the "reportlab" package. Please install it first.', 'danger')
        return redirect(url_for('main.form_analytics', form_id=form_id))

    data = _get_form_analytics_data(form_id)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 0.75 * inch
    line_height = 0.2 * inch
    y = height - margin

    def write_line(text, font='Helvetica', size=11, extra_gap=0):
        nonlocal y
        if y <= margin:
            pdf.showPage()
            pdf.setFont(font, size)
            y = height - margin
        pdf.setFont(font, size)
        pdf.drawString(margin, y, text)
        y -= (line_height + extra_gap)

    pie_colors = [
        colors.HexColor('#FF6384'),
        colors.HexColor('#36A2EB'),
        colors.HexColor('#FFCE56'),
        colors.HexColor('#4BC0C0'),
        colors.HexColor('#9966FF'),
        colors.HexColor('#FF9F40'),
        colors.HexColor('#2E86AB'),
        colors.HexColor('#F47C7C')
    ]

    def draw_pie_chart(title, labels, values):
        nonlocal y
        if not values or sum(values) == 0:
            return

        chart_height = 2.4 * inch
        legend_height = max(len(labels), 1) * 0.18 * inch
        required_height = chart_height + legend_height + 0.45 * inch

        if y - required_height <= margin:
            pdf.showPage()
            pdf.setFont('Helvetica', 11)
            y = height - margin

        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawString(margin, y, title)
        y -= 0.25 * inch

        drawing = Drawing(3.2 * inch, chart_height)
        pie = Pie()
        pie.x = 20
        pie.y = 5
        pie.width = 2.4 * inch
        pie.height = 2.4 * inch
        pie.data = values
        pie.labels = None
        pie.slices.strokeWidth = 0.5
        for idx in range(len(values)):
            pie.slices[idx].fillColor = pie_colors[idx % len(pie_colors)]
        drawing.add(pie)
        renderPDF.draw(drawing, pdf, margin, y - chart_height)

        legend_x = margin + 3.4 * inch
        legend_y = y - 0.1 * inch
        total = sum(values)
        pdf.setFont('Helvetica', 9)
        for idx, label in enumerate(labels):
            pct = (values[idx] / total * 100) if total else 0
            pdf.setFillColor(pie_colors[idx % len(pie_colors)])
            pdf.rect(legend_x, legend_y - 0.12 * inch, 0.12 * inch, 0.12 * inch, fill=1, stroke=0)
            pdf.setFillColor(colors.black)
            pdf.drawString(legend_x + 0.2 * inch, legend_y - 0.1 * inch, f"{label}: {values[idx]} ({pct:.1f}%)")
            legend_y -= 0.18 * inch

        y -= (chart_height + legend_height + 0.3 * inch)

    pdf.setTitle(f"Analytics - {data['form'].title}")
    write_line(f"Form Analytics Report", 'Helvetica-Bold', 16, extra_gap=0.1 * inch)
    write_line(f"Form: {data['form'].title}", 'Helvetica-Bold', 12)
    write_line(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", 'Helvetica', 9, extra_gap=0.05 * inch)

    write_line("Summary", 'Helvetica-Bold', 13, extra_gap=0.05 * inch)
    summary_rows = [
        ("Total Responses", data['total_responses']),
        ("Total Questions", data['total_questions']),
        ("Average Score", f"{data['avg_score']:.1f}%"),
        ("Total Possible Points", data['total_possible_points'])
    ]
    for label, value in summary_rows:
        write_line(f"• {label}: {value}", 'Helvetica', 11)

    write_line("", extra_gap=0.05 * inch)
    write_line("Score Distribution", 'Helvetica-Bold', 13, extra_gap=0.05 * inch)
    for label, count in data['score_ranges'].items():
        write_line(f"{label}% : {count}", 'Helvetica', 11)

    write_line("", extra_gap=0.05 * inch)
    write_line("Question Accuracy (Top 15)", 'Helvetica-Bold', 13, extra_gap=0.05 * inch)
    for idx, q in enumerate(data['question_stats'][:15], start=1):
        text = q['question_text']
        write_line(f"{idx}. {text} - {q['accuracy']:.1f}% accuracy ({q['correct_answers']}/{q['total_answers']} correct)", 'Helvetica', 10)

    write_line("", extra_gap=0.05 * inch)
    write_line("Category Leaders (Top 3 per category)", 'Helvetica-Bold', 13, extra_gap=0.05 * inch)
    if data['category_leaders']:
        for category, rows in data['category_leaders'].items():
            write_line(f"{category}:", 'Helvetica-Bold', 11)
            for row in rows[:3]:
                name = row.get('submitted_by') or 'Unknown student'
                write_line(f"   - {name}: {row['percentage']:.1f}% ({row['earned_points']:.1f} pts)", 'Helvetica', 10)
    else:
        write_line("No category data available.", 'Helvetica', 11)

    pie_questions = [q for q in data['question_stats'] if q.get('answer_breakdown')]
    if pie_questions:
        write_line("", extra_gap=0.05 * inch)
        write_line("Answer Distribution Charts", 'Helvetica-Bold', 13, extra_gap=0.1 * inch)
        MAX_PIE_CHARTS = 6
        charts_rendered = 0
        for idx, q in enumerate(pie_questions, start=1):
            labels = []
            values = []
            for label, details in q['answer_breakdown'].items():
                count = details.get('count') or 0
                if count > 0:
                    labels.append(label)
                    values.append(count)
            if not values:
                continue
            title_text = f"Q{idx}: {q['question_text']}"
            if len(title_text) > 90:
                title_text = title_text[:87] + '...'
            draw_pie_chart(title_text, labels, values)
            charts_rendered += 1
            if charts_rendered >= MAX_PIE_CHARTS:
                break
        remaining = len(pie_questions) - charts_rendered
        if remaining > 0:
            write_line(f"(+{remaining} additional charts not shown due to space)", 'Helvetica-Oblique', 9)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    filename = f"analytics_form_{form_id}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

@main.route('/generate_ai_question_with_context', methods=['POST'])
def generate_ai_question_with_context():
    """
    Generate a question using AI with dataset context
    This endpoint uses AI (LM Studio) with dataset examples as context
    """
    # Get the prompt from the request
    data = request.get_json() if request.is_json else request.form
    prompt = data.get('prompt')
    language = data.get('language', 'Python')
    question_type = data.get('question_type', 'coding')
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    try:
        # Import AI question generator
        from app.ai_question_generator import ai_question_generator
        
        # Generate question using AI with dataset context
        question_data = ai_question_generator.generate_question(prompt, language)
        
        # Return the generated question data
        return jsonify({
            'success': True,
            'question_data': question_data,
            'message': 'Question generated successfully using AI with dataset context'
        })
    
    except Exception as e:
        print(f"AI question generation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main.route('/form/ai-question', methods=['POST'])
def generate_ai_question_standalone():
    """
    Generate a question using AI with dataset context, or fallback to datasets if AI unavailable
    This endpoint is called directly from the JavaScript frontend
    """
    # Get the prompt from the request
    data = request.get_json() if request.is_json else request.form
    prompt = data.get('prompt')
    language = data.get('language', 'Python')
    question_type = data.get('question_type', 'coding')
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    try:
        # Import the AI question generator
        from app.ai_question_generator import ai_question_generator
        
        # Use AI question generator with LM Studio integration
        question_data = ai_question_generator.generate_question(prompt, language, question_type)
        
        # Convert to the format expected by the frontend
        frontend_data = {
            'text': question_data.get('question_text', ''),
            'sample_code': question_data.get('sample_code', ''),
            'unit_tests': question_data.get('unit_tests', ''),
            # For legacy frontend code paths, also expose unit tests as 'expected_output'
            'expected_output': question_data.get('unit_tests', ''),
            'expected_outputs': question_data.get('expected_outputs', ''),
            'scoring_criteria': question_data.get('scoring_criteria', ''),
            'max_score': question_data.get('max_score', 100),
            'hints': question_data.get('hints', ''),
            'topic': question_data.get('topic', ''),
            'language': question_data.get('language', language),
            'question_type': question_data.get('question_type', question_type),
            'options': question_data.get('options', []),
            'correct_answer': question_data.get('correct_answer', ''),
            'explanation': question_data.get('explanation', '')
        }

        # For coding questions generated by AI, we intentionally do NOT want to
        # expose any starter/sample code to students—only the problem
        # statement, unit tests, and hints. Force sample_code to be empty.
        if frontend_data.get('question_type') == 'coding':
            frontend_data['sample_code'] = ''
        
        # Return the generated question data
        return jsonify(frontend_data)
    
    except Exception as e:
        print(f"AI question generation error: {str(e)}")
        return jsonify({'error': str(e)}), 500