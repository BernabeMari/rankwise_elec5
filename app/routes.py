from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app import db
from app.models.models import Form, Question, Response, Answer, Dataset
from app.models.users import login_required, admin_required, get_user, get_all_students
from datetime import datetime
import requests, time
from rapidfuzz import fuzz
import json

main = Blueprint('main', __name__)


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
    else:
        # For students: show only visible forms they haven't completed yet
        user_id = session.get('user_id')
        
        # Get all visible forms
        visible_forms = Form.query.filter_by(is_visible=True).order_by(Form.created_at.desc()).all()
        
        # Filter out forms that this student has already answered
        forms = []
        for form in visible_forms:
            # Check if this student has already submitted a response for this form
            existing_response = Response.query.filter_by(
                form_id=form.id, 
                submitted_by=user_id
            ).first()
            
            # Only include forms that haven't been answered yet
            if not existing_response:
                forms.append(form)
    
    user = get_user(session['user_id'])
    return render_template('index.html', forms=forms, user=user)

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
    return render_template('edit_form.html', form=form, questions=questions)

@main.route('/form/<int:form_id>/question/new', methods=['POST'])
@admin_required
def add_question(form_id):
    form = Form.query.get_or_404(form_id)
    
    question_text = request.form.get('question_text')
    question_type = request.form.get('question_type')
    correct_answer = request.form.get('correct_answer')
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
        points=points
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
    
    # Handle sample code for identification questions
    if question_type == 'identification':
        question.sample_code = request.form.get('sample_code')
    
    db.session.add(question)
    db.session.commit()
    
    return redirect(url_for('main.edit_form', form_id=form_id))

def query_lm_studio(prompt, max_tokens=1500, timeout=60, model_path=None):
    """
    Query the LM Studio API with a prompt - Optimized for DeepSeek-Coder-V2-Lite-Instruct
    """
    # Using the confirmed working endpoint
    endpoint = "http://localhost:1234/v1/completions"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Parameters optimized for the model
    data = {
        "prompt": prompt,
        "temperature": 0.6,  # Slightly lower temperature for more focused responses
        "max_tokens": max_tokens,
        "stop": ["###"],
        "top_p": 0.9,        # Add top_p sampling for better quality
        "frequency_penalty": 0.1,  # Slight penalty to reduce repetition
        "presence_penalty": 0.1    # Slight penalty to encourage more diverse outputs
    }
    
    # Use custom model path if provided
    if model_path:
        data["model"] = model_path
    
    # Increased timeout and added retry logic
    max_retries = 3
    current_retry = 0
    
    while current_retry < max_retries:
        try:
            print(f"Calling LM Studio API at: {endpoint} (attempt {current_retry + 1}/{max_retries})")
            response = requests.post(endpoint, headers=headers, json=data, timeout=timeout)
            response.raise_for_status()
            response_json = response.json()
            
            # Handle response from OpenAI-compatible API
            if 'choices' in response_json and len(response_json['choices']) > 0:
                if 'text' in response_json['choices'][0]:
                    return response_json['choices'][0]['text']
                elif 'message' in response_json['choices'][0]:
                    return response_json['choices'][0]['message']['content']
            
            return "Failed to parse response from LM Studio"
        except requests.exceptions.RequestException as e:
            current_retry += 1
            if current_retry >= max_retries:
                print(f"Error calling LM Studio API after {max_retries} attempts: {e}")
                raise Exception(f"Failed to connect to LM Studio API: {str(e)}. Is LM Studio running?")
            print(f"Retry {current_retry}/{max_retries} due to: {e}")
            time.sleep(2)  # Wait 2 seconds before retrying

def clean_short_answer(raw_answer: str, question_text: str = "", preserve_full: bool = False) -> str:
    """Return a concise, answer-only string by stripping explanations.
    Uses simple heuristics plus fuzzy overlap checks against the question text.
    If preserve_full is True, keeps the full answer without truncation.
    """
    try:
        import re
        from difflib import SequenceMatcher
        if not raw_answer:
            return raw_answer
        text = raw_answer.strip()
        # Remove leading labels
        text = re.sub(r"^(correct\s*answer\s*[:\-]|answer\s*[:\-])\s*", "", text, flags=re.I)
        # Take first line/sentence
        first_line = text.split("\n", 1)[0]
        sentence = re.split(r"(?<=[.!?])\s+", first_line)[0]
        # Cut at common explanation joiners
        sentence = re.split(r"\b(because|which|that|who|so that|therefore|hence|as it|as this)\b", sentence, flags=re.I)[0]
        # Remove parenthetical notes
        sentence = re.sub(r"\([^)]*\)", "", sentence)
        # Remove trailing punctuation and extra spaces
        sentence = re.sub(r"[\s,;:]+$", "", sentence).strip()
        
        # If preserve_full is True, don't truncate (for multiple choice options)
        if not preserve_full:
            # If still very long, keep up to first 6 words
            words = sentence.split()
            if len(words) > 6:
                sentence = " ".join(words[:6])
            # Avoid repeating the question; if 80%+ similar to question, attempt to trim trailing words
            if question_text:
                ratio = SequenceMatcher(None, sentence.lower(), question_text.lower()).ratio()
                if ratio > 0.8 and len(words) > 1:
                    sentence = words[-1]
        
        return sentence.strip()
    except Exception:
        return raw_answer.strip()

def parse_ai_response(content, question_type):
    """
    Parse the AI model response into a structured question format in a concise way.
    """
    try:
        import re
        lines = [ln.strip() for ln in content.strip().splitlines() if ln.strip()]
        lower_lines = [ln.lower() for ln in lines]
        ans_idx = next((i for i, l in enumerate(lower_lines) if l.startswith("answer") or "correct answer" in l or "correct answers" in l), None)
        # Build question text from leading lines before options/answer
        qtext_parts = []
        for i, ln in enumerate(lines):
            if question_type in ['multiple_choice', 'checkbox'] and re.match(r'^[A-D][.).]\s+', ln):
                break
            if ans_idx is not None and i >= ans_idx:
                break
            qtext_parts.append(ln)
        question_text = ' '.join(qtext_parts).strip()
        data = {'text': question_text, 'question_type': question_type}
        if question_type == 'multiple_choice':
            options = [clean_short_answer(m.group(2).strip(), question_text, preserve_full=True)
                       for m in re.finditer(r'^([A-D])[.).]\s+(.+)$', content, flags=re.M)]
            if not options:
                options = ["Option A", "Option B", "Option C", "Option D"]
            m = re.search(r'(?:correct\s+answer|answer)[:\s]+([A-D])', content, flags=re.I)
            if m:
                idx = ord(m.group(1).upper()) - ord('A')
                correct = options[idx] if 0 <= idx < len(options) else options[0]
            else:
                correct = options[0]
            data.update({'options': options, 'correct_answer': clean_short_answer(correct, question_text, preserve_full=True)})
        elif question_type == 'checkbox':
            # Expect options A-D and possibly multiple correct letters like "Correct answers: A,C" or "A and C"
            options = [clean_short_answer(m.group(2).strip(), question_text, preserve_full=True)
                       for m in re.finditer(r'^([A-D])[.).]\s+(.+)$', content, flags=re.M)]
            if not options:
                options = ["Option A", "Option B", "Option C", "Option D"]
            # Look for letters list
            m = re.search(r'(?:correct\s+answers?|answers?)[:\s]+([A-D](?:\s*,\s*[A-D])*(?:\s*(?:and|&)\s*[A-D])?)', content, flags=re.I)
            letters = []
            if m:
                raw = m.group(1)
                # Normalize separators
                raw = re.sub(r'\s*(?:and|&)\s*', ',', raw, flags=re.I)
                letters = [ch.strip().upper() for ch in raw.split(',') if ch.strip()]
            elif any("correct answer" in l for l in lower_lines):
                # Fallback: single letter
                m2 = re.search(r'(?:correct\s+answer|answer)[:\s]+([A-D])', content, flags=re.I)
                if m2:
                    letters = [m2.group(1).upper()]
            # Map letters to option texts
            idxs = [ord(L) - ord('A') for L in letters]
            correct_list = [options[i] for i in idxs if 0 <= i < len(options)]
            if not correct_list:
                # Default to first two options as a placeholder
                correct_list = options[:2]
            data.update({'options': options, 'correct_answer': correct_list})
        elif question_type == 'identification':
            m = re.search(r'(?:correct\s+answer|answer)[:\s]+(.+)$', content, flags=re.I|re.M)
            extracted = m.group(1).strip() if m else (lines[-1] if lines else "")
            cleaned = clean_short_answer(extracted, question_text)
            if cleaned.lower() == question_text.lower() and lines:
                cleaned = clean_short_answer(next((ln for ln in reversed(lines) if ln.lower() != question_text.lower()), extracted), question_text)
            data['correct_answer'] = cleaned or extracted or "Please provide a correct answer for this question"
        elif question_type == 'true_false':
            # Expect a line like "Correct answer: True" or "Correct answer: False"
            m = re.search(r'(?:correct\s+answer|answer)[:\s]+(true|false)', content, flags=re.I)
            ans = (m.group(1).strip().capitalize() if m else 'True')
            data['options'] = ['True', 'False']
            data['correct_answer'] = 'True' if ans.lower() == 'true' else 'False'
        elif question_type == 'enumeration':
            # Expect a line: "Correct answers: a, b, c"
            m = re.search(r'(?:correct\s+answers?)[:\s]+(.+)$', content, flags=re.I|re.M)
            items = []
            if m:
                raw = m.group(1)
                items = [clean_short_answer(p.strip(), question_text, preserve_full=True) for p in raw.replace('\n', ',').split(',') if p.strip()]
            if not items and lines:
                # fallback: last non-question line split by commas
                fallback = lines[-1]
                items = [clean_short_answer(p.strip(), question_text, preserve_full=True) for p in fallback.split(',') if p.strip()]
            data['correct_answer'] = items
        elif question_type == 'coding':
            m = re.search(r"Problem:\s*(.*?)\n\s*(?:Sample Code:|```|$)", content, flags=re.S|re.I)
            problem = (m.group(1).strip() if m else '')
            if not problem:
                # Fallback: first non-empty paragraph
                paragraph = []
                for ln in content.split('\n'):
                    ln = ln.strip()
                    if ln:
                        paragraph.append(ln)
                    elif paragraph:
                        break
                problem = ' '.join(paragraph).strip()
            if problem:
                data['text'] = problem
            data['sample_code'] = None
            data['expected_output'] = None
        return data
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        return {
            'text': content[:100] + "..." if len(content) > 100 else content,
            'question_type': question_type,
            'options': ["Option A", "Option B", "Option C", "Option D"] if question_type in ['multiple_choice', 'checkbox'] else None,
        }

@main.route('/form/ai-question', methods=['POST'])
def generate_ai_question_standalone():
    """
    Generate an AI question without requiring a form_id
    This endpoint is called directly from the JavaScript frontend
    """
    # Get the prompt from the request
    data = request.get_json() if request.is_json else request.form
    prompt = data.get('prompt')
    question_type = data.get('question_type', 'multiple_choice')
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    try:
        # Create a specific prompt for the DeepSeek Coder 7b Instruct v1.5 model
        instructions = ""
        if question_type == 'multiple_choice':
            instructions = """
            - Provide exactly 4 options labeled A, B, C, D
            - Each option should be on a separate line starting with the letter
            - Clearly mark the correct answer at the end as "Correct answer: [letter]"
            - Options should be distinct and unambiguous
            - YOU MUST ALWAYS specify the correct answer - this is required
            - The correct answer must be factually accurate
            """
        elif question_type == 'identification':
            instructions = """
            - The answer should be a specific word, phrase, or term
            - Make the question focused and specific
            - Clearly separate the question from the answer
            - After writing the question, include "Correct answer: [your answer]" on a new line
            - The answer should be different from the question itself
            - YOU MUST ALWAYS provide the correct answer - this is required
            - The correct answer must be factually accurate
            - Example format:
              What is the programming language that was created as an extension to Python 2.x in 1991?
              Correct answer: Python++
            """
        elif question_type == 'checkbox':
            instructions = """
            - Provide exactly 4 options labeled A, B, C, D
            - More than one option may be correct
            - Each option should be on its own line starting with the letter
            - At the end, include a line like: "Correct answers: A, C" (one or more letters separated by commas or 'and')
            - Options should be distinct and unambiguous
            - YOU MUST ALWAYS specify at least one correct answer
            """
        elif question_type == 'true_false':
            instructions = """
            - Write a statement that is clearly either True or False
            - At the end, include a line: "Correct answer: True" or "Correct answer: False"
            - Do NOT include multiple choice letters
            """
        elif question_type == 'enumeration':
            instructions = """
            - Ask for multiple items (e.g., list programming paradigms of Python)
            - At the end, include a line: "Correct answers: item1, item2, item3" (comma-separated)
            - Keep items short (single terms/short phrases)
            """
        elif question_type == 'coding':
            instructions = """
            Output EXACTLY in this format (no extra text):
            <single-paragraph coding problem statement describing the required program and inputs/outputs>
            
            Rules:
            - Do NOT include any code, sample code, solution, tests, or explanations.
            - Keep the problem clear and self-contained.
            """
        
        # Get dataset context for AI
        dataset_context = ""
        try:
            active_datasets = Dataset.query.filter_by(is_active=True, is_builtin=True).all()
            if active_datasets:
                dataset_context = "\n\nAvailable datasets for context:\n"
                for dataset in active_datasets:
                    try:
                        sample_data = dataset.get_sample_data(2)  # First 2 rows
                        columns = dataset.get_columns()
                        dataset_context += f"- {dataset.name}: {dataset.description or 'No description'}\n"
                        dataset_context += f"  Columns: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}\n"
                        if sample_data:
                            dataset_context += f"  Sample data: {str(sample_data)[:200]}...\n"
                    except Exception as e:
                        print(f"Error processing dataset {dataset.name}: {e}")
                        continue
        except Exception as e:
            print(f"Error getting dataset context: {e}")

        ai_prompt = f"""You are a teacher generating an easy and student friendly questions about {prompt}.

Create a {question_type} question about '{prompt}' following these guidelines:

Requirements:
1. Question should be clear, specific, and 1-2 sentences
2. Focus on key concepts related to {prompt}
3. Appropriate difficulty level for learning assessment
4. You MUST provide a factually accurate correct answer
5. Question should have the {prompt} in it
6. If relevant, you may reference the available datasets below for context and examples

{instructions}

{dataset_context}

Return only the question with no additional explanation. Do not include any rationale or explanation after the answer; keep the answer concise (a single term/phrase).

Question:
"""
        
        # Call the LM Studio API
        ai_response = query_lm_studio(ai_prompt)
        
        if not ai_response:
            raise Exception("Failed to get a response from the AI model")
        
        # Parse the AI response into our question format
        question_data = parse_ai_response(ai_response, question_type)
        
        # Return the generated question data
        return jsonify(question_data)
    
    except Exception as e:
        print(f"AI question generation error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        question.correct_answer = request.form.get('correct_answer')
        
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
    
    # Check if form is visible for non-admin users
    if not form.is_visible and session.get('role') != 'admin':
        flash('This form is not currently available.', 'warning')
        return redirect(url_for('main.index'))
    
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
            
            # For coding questions, use AI to evaluate the answer
            elif question.question_type == 'coding' and answer_text:
                model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\bartowski\\DeepSeek-Coder-V2-Lite-Instruct-GGUF\\DeepSeek-Coder-V2-Lite-Instruct-Q8_0_L.gguf"
                is_correct, score_percentage, explanation = evaluate_code_with_ai(
                    code_answer=answer_text,
                    question_text=question.question_text
                )
                print(f"AI Code Evaluation for Question {question.id}:")
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

def evaluate_code_with_ai(code_answer, question_text):
    """Evaluate code with AI and return (is_correct, score_percentage, explanation)."""
    try:
        # Get coding evaluation samples for context
        evaluation_context = ""
        try:
            active_datasets = Dataset.query.filter_by(is_active=True, is_builtin=True).all()
            for dataset in active_datasets:
                if 'coding_evaluation_samples' in dataset.filename:
                    sample_data = dataset.get_sample_data(3)  # First 3 samples
                    columns = dataset.get_columns()
                    evaluation_context += f"\n\nCoding Evaluation Examples:\n"
                    for sample in sample_data:
                        evaluation_context += f"- Problem: {sample.get('problem_statement', '')[:100]}...\n"
                        evaluation_context += f"  Sample Solution: {sample.get('sample_code', '')[:150]}...\n"
                        evaluation_context += f"  Scoring Criteria: {sample.get('scoring_criteria', '')}\n"
                        evaluation_context += f"  Common Mistakes: {sample.get('common_mistakes', '')}\n"
                    break
        except Exception as e:
            print(f"Error getting evaluation context: {e}")
        
        prompt = f"""You are a programming evaluator.
First, analyze the student's code for the given task. Then output a single final verdict line.

IMPORTANT: Ignore use of variable names, naming conventions, and coding style. Focus ONLY on whether the code works and solves the task correctly.

If the problem statement specifies a programming language (e.g., Python, JavaScript, C#, etc.) and the student's code is written in a different language, you MUST assign ZERO (0) and clearly state the mismatch in the analysis.

Question:
{question_text}

Student Code:
{code_answer}

{evaluation_context}

Scoring rubric (pick ONE):
- PERFECT (100): Runs correctly, fully solves the task
- MINOR_FLAW (90): Small issues (syntax, variables, minor logic). Example: "The code runs correctly, but the variable names used are exchanged(Ex. instead of using num the student used num1)."
- MAJOR_FLAW (70): Major issues (wrong data types). Example: "The code runs correctly, but the data types are incorrect."
- SO_SO (50): Code is mostly wrong but has some correct parts. 
- EFFORT (25): Input some coding but mostly wrong. 
- ZERO (0): No meaningful attempt OR the code is written in a different programming language than required by the problem.

Output format (exact):
1) An "Analysis:" section (1-5 short sentences or bullets) explaining correctness and issues
2) A single last line: SCORE_VERDICT: <PERFECT|MINOR_FLAW|MAJOR_FLAW|SO_SO|EFFORT|ZERO>
"""
        
        model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\bartowski\\DeepSeek-Coder-V2-Lite-Instruct-GGUF\\DeepSeek-Coder-V2-Lite-Instruct-Q8_0_L.gguf"
        ai_resp = query_lm_studio(prompt, max_tokens=400, timeout=60, model_path=model_path) or ""
        
        scores = {'PERFECT': 100, 'MINOR_FLAW': 90, 'MAJOR_FLAW': 70, 'SO_SO': 50, 'EFFORT': 25, 'ZERO': 0}
        text = (ai_resp or '').strip()
        analysis = None
        try:
            import re
            # Prefer explicit SCORE_VERDICT line; take the last occurrence if multiple
            pattern = re.compile(r"SCORE_VERDICT\s*:\s*(PERFECT|MINOR_FLAW|MAJOR_FLAW|SO_SO|EFFORT|ZERO)", re.I)
            matches = pattern.findall(text)
            if matches:
                category = matches[-1].upper()
                # Extract analysis as everything before the last verdict line
                last_verdict_match = list(pattern.finditer(text))[-1]
                analysis = text[:last_verdict_match.start()].strip()
            else:
                # Fallback: choose the category that appears latest in the text
                upper = text.upper()
                positions = [(upper.rfind(k), k) for k in scores.keys() if upper.rfind(k) != -1]
                category = max(positions)[1] if positions else 'ZERO'
                analysis = text.strip()
        except Exception:
            category = 'ZERO'
            analysis = text.strip()
        score = scores[category]
        
        feedback_lines = []
        if analysis:
            feedback_lines.append("Analysis:\n" + analysis)
        feedback_lines.append(f"SCORE_VERDICT: {category} ({score}%)")
        feedback = "\n\n".join(feedback_lines)
        
        return score >= 75, score, feedback
    except Exception as e:
        print(f"Error evaluating code: {e}")
        return False, 0, "SCORE_VERDICT: N/A Please contact the coordinator."

# Built-in Dataset Management Routes

def initialize_builtin_datasets():
    """Initialize built-in datasets from CSV files."""
    import os
    import pandas as pd
    
    # Define built-in programming datasets
    datasets_config = [
        {
            'name': 'Programming Languages',
            'description': 'Syntax examples and paradigms for Python, C, C++, and Java',
            'filename': 'programming_languages.csv'
        },
        {
            'name': 'Programming Concepts',
            'description': 'Core programming concepts with examples and complexity levels',
            'filename': 'programming_concepts.csv'
        },
        {
            'name': 'Algorithms Data',
            'description': 'Common algorithms with time/space complexity and implementation hints',
            'filename': 'algorithms_data.csv'
        },
        {
            'name': 'Coding Evaluation Samples',
            'description': 'Sample coding questions with solutions, test cases, and scoring criteria',
            'filename': 'coding_evaluation_samples.csv'
        }
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
                df = pd.read_csv(file_path)
                
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
    
    status = "activated" if dataset.is_active else "deactivated"
    flash(f'Dataset "{dataset.name}" has been {status}!', 'success')
    return redirect(url_for('main.manage_datasets'))


@main.route('/datasets/context', methods=['GET'])
@admin_required
def get_datasets_context():
    """Get active datasets for AI context (API endpoint)."""
    try:
        active_datasets = Dataset.query.filter_by(is_active=True, is_builtin=True).all()
        
        context_data = []
        for dataset in active_datasets:
            try:
                # Get sample data for context
                sample_data = dataset.get_sample_data(3)  # First 3 rows
                columns = dataset.get_columns()
                
                context_data.append({
                    'name': dataset.name,
                    'description': dataset.description,
                    'columns': columns,
                    'sample_data': sample_data,
                    'row_count': dataset.row_count
                })
            except Exception as e:
                print(f"Error processing dataset {dataset.name}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'datasets': context_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/form/<int:form_id>/analytics', methods=['GET'])
@admin_required
def form_analytics(form_id):
    """Display analytics for a specific form."""
    form = Form.query.get_or_404(form_id)
    
    # Get all responses for this form
    responses = Response.query.filter_by(form_id=form_id).all()
    
    # Get all questions for this form
    questions = Question.query.filter_by(form_id=form_id).all()
    
    # Calculate analytics
    total_responses = len(responses)
    total_questions = len(questions)
    
    # Calculate total possible points
    total_possible_points = sum(q.points for q in questions) if questions else 0
    
    # Response analytics
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
    
    # Sort by percentage (highest first)
    response_stats.sort(key=lambda x: x['percentage'], reverse=True)
    
    # Calculate average score
    avg_score = sum(r['percentage'] for r in response_stats) / len(response_stats) if response_stats else 0
    
    # Question analytics with detailed answer breakdowns
    question_stats = []
    for question in questions:
        answers = [a for a in question.answers if a.response_id in [r.id for r in responses]]
        correct_count = sum(1 for a in answers if a.is_correct)
        total_answers = len(answers)
        accuracy = (correct_count / total_answers * 100) if total_answers > 0 else 0
        
        # Analyze answer choices for different question types
        answer_breakdown = {}
        
        if question.question_type == 'multiple_choice':
            # Count each option (A, B, C, D)
            options = question.get_options()
            for i, option in enumerate(options):
                letter = chr(65 + i)  # A, B, C, D
                count = sum(1 for a in answers if a.answer_text == option)
                answer_breakdown[letter] = {
                    'text': option,
                    'count': count,
                    'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                }
        
        elif question.question_type == 'checkbox':
            # Count each selected option
            options = question.get_options()
            for i, option in enumerate(options):
                letter = chr(65 + i)  # A, B, C, D
                count = 0
                for a in answers:
                    try:
                        import json
                        selected = json.loads(a.answer_text) if a.answer_text else []
                        if option in selected:
                            count += 1
                    except:
                        pass
                answer_breakdown[letter] = {
                    'text': option,
                    'count': count,
                    'percentage': (count / total_answers * 100) if total_answers > 0 else 0
                }
        
        elif question.question_type == 'true_false':
            # Count True vs False
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
            # Group similar answers together
            answer_groups = {}
            for a in answers:
                answer_text = a.answer_text or ""
                # Group by first 20 characters to handle variations
                key = answer_text[:20].lower().strip()
                if key not in answer_groups:
                    answer_groups[key] = []
                answer_groups[key].append(answer_text)
            
            # Convert to breakdown format
            for key, group in answer_groups.items():
                answer_breakdown[key] = {
                    'text': group[0][:30] + "..." if len(group[0]) > 30 else group[0],
                    'count': len(group),
                    'percentage': (len(group) / total_answers * 100) if total_answers > 0 else 0
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
    
    # Sort questions by accuracy (lowest first - most problematic)
    question_stats.sort(key=lambda x: x['accuracy'])
    
    # Score distribution
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
    
    return render_template('form_analytics.html', 
                         form=form,
                         total_responses=total_responses,
                         total_questions=total_questions,
                         total_possible_points=total_possible_points,
                         response_stats=response_stats,
                         question_stats=question_stats,
                         avg_score=avg_score,
                         score_ranges=score_ranges)