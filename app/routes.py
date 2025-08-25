from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app import db
from app.models.models import Form, Question, Response, Answer
from app.models.users import login_required, admin_required, get_user
import json
from datetime import datetime
import requests
import os
import time
import subprocess
import tempfile
import uuid
import sys
import re
import threading
import queue
import shlex
import signal
import pandas as pd
import platform
from subprocess import Popen, PIPE

main = Blueprint('main', __name__)

# Define compiler paths with defaults
C_COMPILER_PATH = 'gcc'
CPP_COMPILER_PATH = 'g++'
CSHARP_COMPILER_PATH = 'csc'
VB_COMPILER_PATH = 'vbc'

# Dictionary to store active execution processes
active_executions = {}

@main.route('/')
@login_required
def index():
    forms = Form.query.order_by(Form.created_at.desc()).all()
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
        question.expected_output = request.form.get('expected_output')
    
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

def clean_short_answer(raw_answer: str, question_text: str = "") -> str:
    """Return a concise, answer-only string by stripping explanations.
    Uses simple heuristics plus fuzzy overlap checks against the question text.
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
    Parse the AI model response into a structured question format
    Optimized for DeepSeek Coder 7b Instruct v1.5
    """
    try:
        # Default structure
        question_data = {
            'text': '',
            'question_type': question_type
        }
        
        # For demonstration, we'll try to extract information from the AI response
        lines = content.strip().split('\n')
        
        # Find the question text - look for the first paragraph before options or answers
        question_text_lines = []
        found_answer_line = False
        answer_line_index = -1
        
        # First, locate the answer line to properly separate question from answer
        for i, line in enumerate(lines):
            if line.strip() and ("correct answer" in line.lower() or "answer:" in line.lower()):
                found_answer_line = True
                answer_line_index = i
                break
        
        # Now extract question text - everything before the answer line
        for i, line in enumerate(lines):
            if line.strip():
                # Stop when we hit what looks like an option in multiple choice or an answer
                if (question_type == 'multiple_choice' and 
                    (line.strip().startswith('A)') or line.strip().startswith('A.') or 
                     line.strip().startswith('B)') or line.strip().startswith('B.') or
                     line.strip().startswith('C)') or line.strip().startswith('C.') or
                     line.strip().startswith('D)') or line.strip().startswith('D.'))):
                    break
                # Stop at the answer line
                if found_answer_line and i >= answer_line_index:
                    break
                question_text_lines.append(line.strip())
        
        if question_text_lines:
            question_data['text'] = ' '.join(question_text_lines)
        
        if question_type == 'multiple_choice':
            options = []
            correct_answer = None
            
            # Look for options in the DeepSeek Coder 7b Instruct v1.5 format (A, B, C, D)
            option_pattern = r'^([A-D])[.):]\s+(.+)$'
            import re
            
            for line in lines:
                line = line.strip()
                match = re.match(option_pattern, line)
                if match:
                    # Store just the option text without prefix and trim explanations
                    option_text = match.group(2).strip()
                    option_text = clean_short_answer(option_text, question_data.get('text', ''))
                    options.append(option_text)
            
            # Look for the correct answer
            correct_pattern = r'(?:correct\s+answer|answer)[:\s]+([A-D])'
            for line in lines:
                match = re.search(correct_pattern, line.lower())
                if match:
                    correct_letter = match.group(1).upper()
                    # Convert the letter to the array index (0-3)
                    correct_index = ord(correct_letter) - ord('A')
                    if 0 <= correct_index < len(options):
                        correct_answer = options[correct_index]
                        break
            
            # If still no correct answer but we have options, use the first
            if correct_answer is None and options:
                correct_answer = options[0]
                print("Warning: No correct answer specified in AI response for multiple choice, using first option as default")
            
            # Ensure we always have both options and a correct answer
            if not options:
                options = ["Option A", "Option B", "Option C", "Option D"]
                print("Warning: No options found in AI response, using default options")
            
            if correct_answer is None:
                correct_answer = options[0]
                print("Warning: No correct answer could be determined, using first option as default")
            
            # Final trim of correct answer
            correct_answer = clean_short_answer(correct_answer, question_data.get('text', ''))
            
            question_data['options'] = options
            question_data['correct_answer'] = correct_answer
            
        elif question_type == 'identification':
            # Look for a line with "answer:" or "correct answer:"
            answer_pattern = r'(?:correct\s+answer|answer)[:\s]+(.+)$'
            import re
            
            extracted_answer = None
            for line in lines:
                match = re.search(answer_pattern, line.lower())
                if match:
                    extracted_answer = match.group(1).strip()
                    break
            
            # If we didn't find a clearly marked answer, check the last non-empty line
            if not extracted_answer:
                for line in reversed(lines):
                    if line.strip() and not line.lower().startswith(("question", "prompt")):
                        extracted_answer = line.strip()
                        break
            
            # Make sure there is always a correct answer
            if not extracted_answer:
                print("Warning: No correct answer found in AI response for identification question")
                extracted_answer = "Please provide a correct answer for this question"
            
            # Make sure the correct answer isn't just repeating the question
            cleaned = clean_short_answer(extracted_answer, question_data.get('text', ''))
            if cleaned.lower() == (question_data.get('text', '').lower()):
                # Try to find a different answer from content
                for line in reversed(lines):
                    if line.strip() and line.lower() != question_data.get('text', '').lower():
                        cleaned = clean_short_answer(line.strip(), question_data.get('text', ''))
                        break
            question_data['correct_answer'] = cleaned or extracted_answer
        
        elif question_type == 'coding':
            # Extract Problem: section
            raw_text = content
            problem_text = ''
            try:
                import re
                # Capture text after 'Problem:' until a blank line or 'Sample Code:'
                prob_match = re.search(r"Problem:\s*(.*?)\n\s*(?:Sample Code:|```|$)", raw_text, flags=re.S|re.I)
                if prob_match:
                    problem_text = prob_match.group(1).strip()
                else:
                    # Fallback: first non-empty paragraph
                    lines_iter = [ln.strip() for ln in raw_text.split('\n')]
                    paragraph = []
                    for ln in lines_iter:
                        if ln:
                            paragraph.append(ln)
                        elif paragraph:
                            break
                    problem_text = ' '.join(paragraph).strip()
            except Exception:
                problem_text = ''
            if problem_text:
                question_data['text'] = problem_text
            
            # Extract first code fence as sample_code (optional)
            code_blocks = []
            in_code_block = False
            current_block = []
            for line in content.split('\n'):
                if line.strip().startswith("```"):
                    if in_code_block:
                        in_code_block = False
                        if current_block:
                            code_blocks.append("\n".join(current_block))
                            current_block = []
                    else:
                        in_code_block = True
                elif in_code_block:
                    current_block.append(line)
            # For coding generation, sample code must not be included
            question_data['sample_code'] = None
            question_data['expected_output'] = None
        
        return question_data
    
    except Exception as e:
        print(f"Error parsing AI response: {e}")
        return {
            'text': content[:100] + "..." if len(content) > 100 else content,
            'question_type': question_type,
            'options': ["Option A", "Option B", "Option C", "Option D"] if question_type == 'multiple_choice' else None,
            'correct_answer': None
        }

@main.route('/form/<int:form_id>/ai-question', methods=['POST'])
def generate_ai_question(form_id):
    form = Form.query.get_or_404(form_id)
    
    # Get the prompt from the request
    data = request.get_json() if request.is_json else request.form
    prompt = data.get('prompt')
    question_type = data.get('question_type', 'multiple_choice')
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    try:
        # Create a specific prompt for the DeepSeek Coder model
        instructions = ""
        if question_type == 'multiple_choice':
            instructions = """
            - Provide exactly 4 options labeled 1-4 or A-D
            - Clearly indicate the correct answer
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
            <1-2 sentence problem statement describing the required program/algorithm and expected inputs/outputs>
    
    
            Rules:
            - Do NOT include any code, sample code, solution, tests, or explanations.
            - Keep the problem clear and self-contained in 1-2 sentences maximum.
            """
        
        ai_prompt = f"""You are an expert educator creating a {question_type} question about {prompt}.

Requirements:
1. Question should be clear and specific
2. {prompt} should be the central topic
3. You MUST provide a factually accurate correct answer
4. For coding questions, only include sample code if truly necessary to explain the problem

For this {question_type} question:
{instructions}

Return only the question with no additional explanation. Do not include any rationale or explanation after the answer; keep the answer concise (a single term/phrase).

QUESTION:
"""
        
        # Call the LM Studio API
        ai_response = query_lm_studio(ai_prompt)
        
        if not ai_response:
            raise Exception("Failed to get a response from the AI model")
        
        # Parse the AI response into our question format
        question_data = parse_ai_response(ai_response, question_type)
        
        return jsonify(question_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
        
        ai_prompt = f"""You are an teacher generating student friendly questions about {prompt}.

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
        question.expected_output = request.form.get('expected_output')
        
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

@main.route('/form/<int:form_id>/view', methods=['GET'])
def view_form(form_id):
    form = Form.query.get_or_404(form_id)
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
    
    # Create a new response
    response = Response(form_id=form_id)
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
                # Case-insensitive comparison for identification
                if question.question_type == 'identification':
                    is_correct = answer_text and answer_text.lower().strip() == question.correct_answer.lower().strip()
                else:
                    is_correct = answer_text == question.correct_answer
                # Set percentage for non-coding questions
                score_percentage = 100 if is_correct else 0
            
            # For coding questions, use AI to evaluate the answer
            elif question.question_type == 'coding' and answer_text:
                # Use the CodeLlama model path provided by the user
                model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\LoneStriker\\deepseek-coder-7b-instruct-v1.5-GGUF\\deepseek-coder-7b-instruct-v1.5-Q5_K_M.gguf"
                
                # Let the AI evaluate the code
                is_correct, score_percentage, explanation = evaluate_code_with_ai(
                    code_answer=answer_text,
                    expected_output=question.expected_output or "",
                    question_text=question.question_text
                )
                
                # Log the evaluation result
                print(f"AI Code Evaluation for Question {question.id}:")
                print(f"Is correct: {is_correct}")
                print(f"Score percentage: {score_percentage}%")
                print(f"Explanation: {explanation}")
        
        # For coding questions, calculate points based on the percentage score
        earned_points = 0
        if question.question_type == 'coding' and answer_text:
            earned_points = (score_percentage / 100) * question.points
        else:
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
    
    return render_template('view_response.html', form=form, response=response, overall_pct=overall_pct, badges=badges)

@main.route('/form/test-lm-studio', methods=['GET'])
def test_lm_studio_connection():
    """
    Test if we can connect to LM Studio
    """
    try:
        # Simple connection test
        endpoint = "http://localhost:1234/v1/completions"
        headers = {"Content-Type": "application/json"}
        data = {
            "prompt": "Hello",
            "max_tokens": 5,
            "temperature": 0.7
        }
        
        # Increased timeout to 60 seconds to match the query function
        response = requests.post(endpoint, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        
        # If we got here, connection is successful
        return jsonify({
            "success": True,
            "message": "Successfully connected to LM Studio"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "Failed to connect to LM Studio. Make sure it's running with the DeepSeek Coder model loaded."
        })

def evaluate_code_with_ai(code_answer, expected_output, question_text):
    """
    Use the AI model to evaluate a code answer
    Returns (bool, float, str): (is_correct, score_percentage, explanation)
    """
    try:
        # Create a prompt for code evaluation that ensures the question is sent exactly as is
        ai_prompt = f"""You are an expert programming teacher evaluating a student's code.

IMPORTANT: First, carefully read and understand the question before evaluating the student's code.

Question (EVALUATE EXACTLY AS WRITTEN): {question_text}

CRITICAL INSTRUCTION: Do NOT modify, simplify, or reinterpret the question above. Use the EXACT question as provided to evaluate the student's code. The question should be taken verbatim as written above.

STUDENT-FRIENDLY CODE ANALYSIS: Evaluate the code fairly and encouragingly. Follow these steps:

1. Check if the code successfully meets the task requirements
2. Look for understanding of the problem and appropriate solution approach
3. Consider effort and attempt to solve the problem
4. Mentally trace through the code execution to verify it works
5. Check for logical correctness and proper implementation
6. Recognize good programming practices and problem-solving skills
7. Be encouraging while still being honest about issues

Student's Code:
{code_answer}

Task: Evaluate the student's code and assign a percentage score based on code quality and correctness.
Your evaluation should be organized as follows:

1. Question Analysis: Briefly restate what the question is asking for
2. Expected Approach: Summarize the expected solution approach
3. Code Analysis: Evaluate the student's implementation with these criteria:
   - Check if the code successfully addresses the problem requirements
   - Verify the solution approach is appropriate for the task
   - Trace through the code execution to ensure it works correctly
   - Look for proper use of programming concepts and logic
   - Check for good coding practices and readability
   - Consider the student's understanding and effort level
   - Provide constructive feedback for improvement

STUDENT-FRIENDLY APPROACH: Focus on understanding and effort. If the code successfully solves the problem, award full points. Be encouraging and recognize good attempts, even if there are minor issues. The goal is to support learning and growth.

Based on your evaluation, categorize the code into one of these student-friendly categories:
- PERFECT (100% score): Code successfully meets the task requirements and produces correct output
- MINOR_FLAW (75% score): Code meets the task but has minor errors, syntax issues, or small logical flaws
- SO_SO (50% score): Code attempts the task but has significant issues or doesn't fully work as intended
- EFFORT (25% score): Code shows some effort and understanding but doesn't really solve the problem
- NO_TRY (0% score): Code shows minimal effort or doesn't attempt to solve the problem at all

SCORING GUIDELINES: Be fair and encouraging while still being honest about the quality of the solution. Recognize effort and understanding, not just perfect execution.

Provide your score verdict in this exact format on its own line:
"SCORE_VERDICT: [CATEGORY]"

Example: "SCORE_VERDICT: MINOR_FLAW"

IMPORTANT: After your verdict, provide ONLY 1-2 sentences explaining your reasoning. Be concise and encouraging.
Focus on the key points and provide constructive feedback.

Example complete response:
"SCORE_VERDICT: MINOR_FLAW
The code correctly implements a binary search algorithm with the right logic but has a minor indexing error on line 5 that would cause off-by-one errors."

Evaluation:
"""
        
        # Use the CodeLlama model path
        model_path = "C:\\Users\\Zyb\\.lmstudio\\models\\LoneStriker\\deepseek-coder-7b-instruct-v1.5-GGUF\\deepseek-coder-7b-instruct-v1.5-Q5_K_M.gguf"
        
        # Include system instructions for better organization
        system_prompt = """You are a supportive and encouraging code assessment expert. Always:
1. Start by understanding the question exactly
2. Use the EXACT question as provided without any modifications, simplifications, or reinterpretations
3. Be fair and encouraging - recognize good attempts and understanding
4. Award full points for code that successfully solves the problem
5. Verify that code addresses the problem requirements appropriately
6. Perform thoughtful code analysis to understand the student's approach
7. Trace through the logic to verify correctness
8. Provide CONSTRUCTIVE feedback - only 1-2 sentences total
9. Focus on the most important aspects in your brief explanation
10. Be encouraging while still being honest about issues"""
        
        # Prepend the system prompt to enhance the model response
        enhanced_prompt = f"{system_prompt}\n\n{ai_prompt}"
        
        # Call the LM Studio API with a longer timeout for complex code analysis
        ai_response = query_lm_studio(enhanced_prompt, max_tokens=300, timeout=120, model_path=model_path)
        
        if not ai_response:
            return False, 0, "AI evaluation failed: No response from AI model"
        
        # Normalize response for parsing
        raw_response = ai_response
        ai_response = ai_response.strip()
        upper_resp = ai_response.upper()
        
        # Parse score category and determine percentage
        score_percentage = 0
        is_correct = False
        score_verdict_pos = upper_resp.find("SCORE_VERDICT:")
        category = None
        
        def clamp_to_allowed(percent_value: int) -> int:
            allowed = [0, 25, 50, 75, 100]
            # Choose the closest allowed value
            return min(allowed, key=lambda v: abs(v - percent_value))
        
        if score_verdict_pos >= 0:
            # Extract the score category from the response line
            score_line = ai_response[score_verdict_pos:].split("\n")[0].strip()
            upper_line = score_line.upper()
            if "PERFECT" in upper_line:
                category = "PERFECT"; score_percentage = 100; is_correct = True
            elif "MINOR_FLAW" in upper_line:
                category = "MINOR_FLAW"; score_percentage = 75; is_correct = True
            elif "SO_SO" in upper_line:
                category = "SO_SO"; score_percentage = 50; is_correct = False
            elif "EFFORT" in upper_line:
                category = "EFFORT"; score_percentage = 25; is_correct = False
            elif "NO_TRY" in upper_line:
                category = "NO_TRY"; score_percentage = 0; is_correct = False
        else:
            # Fallbacks if the exact tag is missing
            if "PERFECT" in upper_resp:
                category = "PERFECT"; score_percentage = 100; is_correct = True
            elif "MINOR FLAW" in upper_resp or "MINOR_FLAW" in upper_resp:
                category = "MINOR_FLAW"; score_percentage = 75; is_correct = True
            elif "SO-SO" in upper_resp or "SO SO" in upper_resp or "SO_SO" in upper_resp:
                category = "SO_SO"; score_percentage = 50; is_correct = False
            elif "EFFORT" in upper_resp:
                category = "EFFORT"; score_percentage = 25; is_correct = False
            elif "NO TRY" in upper_resp or "NO_TRY" in upper_resp:
                category = "NO_TRY"; score_percentage = 0; is_correct = False
            else:
                # Try to parse an explicit percentage like 75% or 50 percent
                import re
                m = re.search(r"(100|75|50|25|0)\s*%", upper_resp)
                if m:
                    score_percentage = clamp_to_allowed(int(m.group(1)))
                    is_correct = score_percentage >= 75
                else:
                    # Legacy binary fallback: require the whole word CORRECT and not INCORRECT
                    has_correct = re.search(r"\bCORRECT\b", upper_resp) is not None
                    has_incorrect = "INCORRECT" in upper_resp
                    is_correct = has_correct and not has_incorrect
                    score_percentage = 100 if is_correct else 0
        
        # Build concise explanation
        explanation = raw_response
        if category is not None or score_verdict_pos >= 0 or score_percentage in (0, 25, 50, 75, 100):
            score_class = "verdict-correct" if score_percentage >= 75 else "verdict-partial" if score_percentage >= 50 else "verdict-incorrect"
            label = f"SCORE_VERDICT: {category}" if category else "Score"
            styled_score = f"<strong class='{score_class}'>{label} ({score_percentage}%)</strong>"
            # Try to grab 1 short sentence after the first line, skipping boilerplate like 'Expected Approach'
            short_explanation = ""
            for line in ai_response.split("\n")[1:]:
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("expected approach"):
                    continue
                short_explanation = line
                break
            explanation = f"{styled_score}<br>{short_explanation}".strip()
        else:
            # If we couldn't determine a category, still present a compact explanation
            score_class = "verdict-correct" if score_percentage >= 75 else "verdict-partial" if score_percentage >= 50 else "verdict-incorrect"
            styled_score = f"<strong class='{score_class}'>Score: {score_percentage}%</strong>"
            explanation = f"{styled_score}"
        
        return is_correct, score_percentage, explanation
    
    except Exception as e:
        print(f"Error evaluating code with AI: {e}")
        return False, 0, f"AI evaluation error: {str(e)}"