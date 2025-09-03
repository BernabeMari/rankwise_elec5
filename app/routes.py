from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app import db
from app.models.models import Form, Question, Response, Answer
from app.models.users import login_required, admin_required, get_user, get_all_students
from datetime import datetime
import requests, time
from rapidfuzz import fuzz

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
        forms = Form.query.filter_by(is_visible=True).order_by(Form.created_at.desc()).all()
    
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
    
    # Handle options for multiple choice
    if question_type == 'multiple_choice':
        options = request.form.getlist('options[]')
        if options:
            question.set_options(options)
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
    Query the LM Studio API with a prompt - Optimized for CodeLlama-13B-Instruct
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
        ans_idx = next((i for i, l in enumerate(lower_lines) if l.startswith("answer") or "correct answer" in l), None)
        # Build question text from leading lines before options/answer
        qtext_parts = []
        for i, ln in enumerate(lines):
            if question_type == 'multiple_choice' and re.match(r'^[A-D][.).]\s+', ln):
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
        elif question_type == 'identification':
            m = re.search(r'(?:correct\s+answer|answer)[:\s]+(.+)$', content, flags=re.I|re.M)
            extracted = m.group(1).strip() if m else (lines[-1] if lines else "")
            cleaned = clean_short_answer(extracted, question_text)
            if cleaned.lower() == question_text.lower() and lines:
                cleaned = clean_short_answer(next((ln for ln in reversed(lines) if ln.lower() != question_text.lower()), extracted), question_text)
            data['correct_answer'] = cleaned or extracted or "Please provide a correct answer for this question"
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
            'options': ["Option A", "Option B", "Option C", "Option D"] if question_type == 'multiple_choice' else None,
            'correct_answer': None
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
        elif question_type == 'coding':
            instructions = """
            Output EXACTLY in this format (no extra text):
            Problem:
            <single-paragraph problem statement describing the required program/algorithm and inputs/outputs>
            
            Rules:
            - Do NOT include any code, sample code, solution, tests, or explanations.
            - Keep the problem clear and self-contained.
            """
        
        ai_prompt = f"""You are a teacher generating student friendly questions about {prompt}.

Create a {question_type} question about '{prompt}' following these guidelines:

Requirements:
1. Question should be clear, specific, and 1-2 sentences
2. Focus on key concepts related to {prompt}
3. Appropriate difficulty level for learning assessment
4. You MUST provide a factually accurate correct answer

{instructions}

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
    question.correct_answer = request.form.get('correct_answer')
    
    # Handle points
    try:
        points = int(request.form.get('points', 1))
        if points < 1:
            points = 1
        question.points = points
    except (ValueError, TypeError):
        question.points = 1
    
    if question.question_type == 'multiple_choice':
        options = request.form.getlist('options[]')
        question.set_options(options)
        question.sample_code = request.form.get('sample_code')
    
    if question.question_type == 'coding':
        question.sample_code = request.form.get('sample_code')
        
    if question.question_type == 'identification':
        question.sample_code = request.form.get('sample_code')
    
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
        
        if question.question_type in ['multiple_choice', 'identification', 'coding']:
            answer_text = request.form.get(f'question_{question.id}')
            
            # Check if answer is correct
            if question.question_type in ['multiple_choice', 'identification'] and question.correct_answer:
                if question.question_type == 'identification':
                    # Use fuzzy matching for identification questions
                    is_correct, score_percentage, explanation = calculate_identification_score(
                        answer_text, question.correct_answer
                    )
                else:
                    # Multiple choice questions use exact matching
                    is_correct = answer_text == question.correct_answer
                    score_percentage = 100 if is_correct else 0
            
            # For coding questions, use AI to evaluate the answer
            elif question.question_type == 'coding' and answer_text:
                # Use the CodeLlama model path provided by the user
                model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\LoneStriker\\CodeLlama-13B-Instruct-GGUF\\codellama-13b-instruct.Q5_K_M.gguf"
                
                # Let the AI evaluate the code
                is_correct, score_percentage, explanation = evaluate_code_with_ai(
                    code_answer=answer_text,
                    question_text=question.question_text
                )
                
                # Log the evaluation result
                print(f"AI Code Evaluation for Question {question.id}:")
                print(f"Is correct: {is_correct}")
                print(f"Score percentage: {score_percentage}%")
                print(f"Explanation: {explanation}")
        
        # Calculate earned points based on question type and score percentage
        earned_points = 0
        if question.question_type in ['coding', 'identification'] and answer_text:
            # Both coding and identification questions use percentage-based scoring
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
            feedback=explanation  # Store AI explanation in the feedback field
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
        ranking_entries.append({
            'response': resp,
            'earned_points': earned_points,
            'percentage': percentage,
            'created_at': resp.created_at
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
    mc_id_count = sum(1 for q in questions if q.question_type in ('multiple_choice', 'identification'))
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
    """
    Evaluate code with AI and return (is_correct, score_percentage, explanation).
    This optimized version requests only a verdict and omits long explanations.
    """
    try:
        prompt = f"""You are a programming evaluator.
Question: {question_text}
StudentCode:
{code_answer}

Scoring policy:
- PERFECT (100): The code solves the task and would run as-is (no syntax or name errors). Do NOT penalize for stylistic differences, formatting/whitespace, comments/docstrings, or type hints.
- MINOR_FLAW (75): There is a small issue that is trivial to fix, such as a variable naming/mismatch
- SO_SO (50): Multiple issues; partial logic correct but fails on key cases.
- EFFORT (25): Attempted but largely incorrect.
- NO_TRY (0): No meaningful attempt.

If there is any minor syntactic or name error like referencing the wrong variable name once (e.g., 'num1' vs 'num') or wrong letter case, choose MINOR_FLAW.

Respond with exactly one line in this format:
SCORE_VERDICT: <CATEGORY>
"""
        model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\LoneStriker\\CodeLlama-13B-Instruct-GGUF\\codellama-13b-instruct.Q5_K_M.gguf"
        ai_resp = query_lm_studio(prompt, max_tokens=200, timeout=60, model_path=model_path) or ""
        resp = ai_resp.strip().upper()
        category_map = {
            'PERFECT': 100,
            'MINOR_FLAW': 75,
            'SO_SO': 50,
            'EFFORT': 25,
            'NO_TRY': 0,
        }
        cat = None
        if "SCORE_VERDICT:" in resp:
            line = resp.splitlines()[0]
            cat = next((k for k in category_map if k in line), None)
        if cat is None:
            cat = next((k for k in category_map if k in resp), None)
        score = category_map.get(cat, 0)
        is_correct = score >= 75
        explanation = f"SCORE_VERDICT: {cat or 'UNKNOWN'} ({score}%)"
        return is_correct, score, explanation
    except Exception as e:
        print(f"Error evaluating code with AI: {e}")
        return False, 0, "SCORE_VERDICT: NO_TRY (0%)"