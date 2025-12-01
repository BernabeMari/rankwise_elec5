#!/usr/bin/env python3
"""
AI Question Generator that uses datasets as context for generating questions
"""

import pandas as pd
import os
import re
import requests
import json
from typing import List, Dict, Any, Optional

class AIQuestionGenerator:
    def __init__(self):
        self.datasets_cache = {}
        self.ai_evaluator = None
        self.lm_studio_url = "http://localhost:1234/v1/chat/completions"
        self.model_path = r"C:\Users\Zyb\.lmstudio\models\bartowski\DeepSeek-Coder-V2-Lite-Instruct-GGUF\DeepSeek-Coder-V2-Lite-Instruct-Q8_0_L.gguf"
        self.timeout = 60  # Increased timeout for LM Studio requests
    
    def _check_lm_studio_available(self) -> bool:
        """Check if LM Studio is running and accessible"""
        try:
            response = requests.get("http://localhost:1234/v1/models", timeout=5)
            return response.status_code == 200
        except:
            return False
        
    def _load_datasets(self) -> Dict[str, pd.DataFrame]:
        """Load only active datasets from the database"""
        if self.datasets_cache:
            return self.datasets_cache
            
        datasets = {}
        
        # Import here to avoid circular imports
        try:
            from app.models.models import Dataset
            from app import db
            
            # Only load datasets that are marked as active
            active_datasets = Dataset.query.filter_by(is_active=True, is_builtin=True).all()
            
            for ds in active_datasets:
                if os.path.exists(ds.file_path):
                    try:
                        df = pd.read_csv(ds.file_path, on_bad_lines='skip', engine='python')
                        datasets[ds.filename] = df
                        print(f"Loaded active dataset: {ds.filename} with {len(df)} rows")
                    except Exception as e:
                        print(f"Error loading {ds.filename}: {e}")
        except Exception as e:
            print(f"Error loading active datasets from database: {e}")
            # Fallback: if database query fails, return empty dict
            # This ensures inactive datasets are never used
        
        self.datasets_cache = datasets
        return datasets
    
    def _search_datasets_for_context(self, prompt: str, language: str = None, question_type: str = 'coding') -> List[Dict[str, Any]]:
        """Search datasets for relevant context based on prompt, language, and question type"""
        datasets = self._load_datasets()
        relevant_examples = []
        
        # Extract keywords from prompt
        prompt_lower = prompt.lower()
        keywords = self._extract_keywords(prompt_lower)
        
        # Map question types to relevant dataset files
        question_type_datasets = {
            'coding': ['it_olympics_coding.csv'],
            'multiple_choice': ['it_olympics_multiple_choice.csv'],
            'checkbox': ['it_olympics_checkbox.csv'],
            'true_false': ['it_olympics_true_false.csv'],
            'enumeration': ['it_olympics_enumeration.csv'],
            'identification': ['it_olympics_identification.csv']
        }
        
        # Get relevant dataset files for the question type
        target_datasets = question_type_datasets.get(question_type, ['it_olympics_coding.csv'])
        
        # Normalize language so noisy UI labels like "Java (1)" still map to
        # the clean language values used in the CSV (e.g., "java").
        lang_filter = None
        if language:
            lang_val = str(language).lower()
            language_aliases = {
                'python': ['python', 'py'],
                'java': ['java'],
                'c++': ['c++', 'cpp', 'c plus plus'],
                'c': [' c ', 'c language', 'clang', ' c,', '(c)'],
                'javascript': ['javascript', 'js'],
            }
            for clean_lang, aliases in language_aliases.items():
                if any(alias in lang_val for alias in aliases) or lang_val.strip().startswith(clean_lang):
                    lang_filter = clean_lang
                    break

        for filename, df in datasets.items():
            # Only search in datasets relevant to the question type
            if filename not in target_datasets:
                continue
            
            for _, row in df.iterrows():
                # Check if language matches (if specified)
                row_language = str(row.get('language', '')).lower()
                if lang_filter and row_language and lang_filter not in row_language:
                    continue
                
                # Check relevance based on keywords
                relevance_score = self._calculate_relevance_for_dataset(row, keywords, prompt_lower, filename)

                # For coding questions with a specific language filter, treat any
                # matching-language row as at least minimally relevant so we
                # always get some context (even when the prompt is just "Java (1)"
                # with no other useful keywords).
                if question_type == 'coding' and lang_filter and row_language and lang_filter in row_language:
                    if relevance_score <= 0:
                        relevance_score = 1
                
                if relevance_score > 0:
                    # Map dataset columns to standard format
                    example = self._map_dataset_row_to_example(row, filename, question_type)
                    example['relevance_score'] = relevance_score
                    relevant_examples.append(example)
        
        # Sort by relevance score and return top examples
        relevant_examples.sort(key=lambda x: x['relevance_score'], reverse=True)
        return relevant_examples[:5]  # Return top 5 most relevant examples
    
    def _extract_keywords(self, prompt: str) -> List[str]:
        """Extract relevant keywords from the prompt"""
        # Common programming concepts
        programming_keywords = [
            'function', 'variable', 'loop', 'condition', 'array', 'list', 'string',
            'number', 'integer', 'float', 'boolean', 'class', 'object', 'method',
            'algorithm', 'sort', 'search', 'recursion', 'iteration', 'data structure',
            'even', 'odd', 'prime', 'factorial', 'fibonacci', 'palindrome', 'reverse',
            'maximum', 'minimum', 'average', 'sum', 'count', 'length', 'size',
            'positive', 'negative', 'zero', 'grade', 'score', 'rating', 'mark',
            'machine learning', 'ml', 'ai', 'artificial intelligence', 'neural',
            'deep learning', 'supervised', 'unsupervised', 'reinforcement',
            'cybersecurity', 'security', 'network', 'networking', 'database',
            'sql', 'query', 'join', 'table', 'python', 'java', 'javascript',
            'programming', 'code', 'software', 'hardware', 'computer', 'data',
            'encryption', 'firewall', 'protocol', 'http', 'https', 'ssl', 'tls'
        ]
        
        # Extract keywords that appear in the prompt
        found_keywords = []
        prompt_lower = prompt.lower()
        
        for keyword in programming_keywords:
            if keyword in prompt_lower:
                found_keywords.append(keyword)
        
        # Also extract individual words (including compound words)
        words = re.findall(r'\b\w+\b', prompt)
        found_keywords.extend([word for word in words if len(word) > 2])
        
        # Add partial matches for common tech terms
        tech_terms = ['e-sports', 'esports', 'e-sport', 'ml', 'ai', 'sql', 'http', 'https']
        for term in tech_terms:
            if term.lower() in prompt_lower:
                found_keywords.append(term.lower())
        
        return list(set(found_keywords))  # Remove duplicates
    
    def _calculate_relevance(self, row: Dict, keywords: List[str], prompt: str) -> int:
        """Calculate relevance score for a dataset row"""
        score = 0
        
        # Check problem statement
        problem_statement = str(row.get('problem_statement', '')).lower()
        topic = str(row.get('topic', '')).lower()
        
        # Score based on keyword matches
        for keyword in keywords:
            if keyword in problem_statement:
                score += 10
            if keyword in topic:
                score += 5
        
        # Score based on exact phrase matches
        if 'even' in prompt and 'even' in problem_statement:
            score += 20
        if 'odd' in prompt and 'odd' in problem_statement:
            score += 20
        if 'function' in prompt and 'function' in problem_statement:
            score += 15
        if 'loop' in prompt and ('for' in problem_statement or 'while' in problem_statement):
            score += 15
        if 'condition' in prompt and ('if' in problem_statement or 'else' in problem_statement):
            score += 15
        
        # Language-specific scoring
        if 'python' in prompt and 'python' in str(row.get('language', '')).lower():
            score += 10
        if 'java' in prompt and 'java' in str(row.get('language', '')).lower():
            score += 10
        if 'c++' in prompt and 'c++' in str(row.get('language', '')).lower():
            score += 10
        
        return score
    
    def _calculate_relevance_for_dataset(self, row: Dict, keywords: List[str], prompt: str, filename: str) -> int:
        """Calculate relevance score for a dataset row based on actual column names"""
        score = 0
        prompt_lower = prompt.lower()
        
        # Get the main text content based on dataset type
        if 'identification' in filename:
            question_text = str(row.get('question', '')).lower()
            answer_text = str(row.get('answer', '')).lower()
            topic = str(row.get('topic', '')).lower()
        elif 'multiple_choice' in filename or 'checkbox' in filename:
            question_text = str(row.get('question', '')).lower()
            topic = str(row.get('topic', '')).lower()
            # Also check options A, B, C, D
            option_text = ' '.join([str(row.get(col, '')).lower() for col in ['A', 'B', 'C', 'D'] if col in row])
        elif 'true_false' in filename:
            question_text = str(row.get('statement', '')).lower()
            topic = str(row.get('topic', '')).lower()
        elif 'enumeration' in filename:
            question_text = str(row.get('question', '')).lower()
            topic = str(row.get('topic', '')).lower()
        elif 'coding' in filename:
            question_text = str(row.get('problem_statement', '')).lower()
            topic = str(row.get('topic', '')).lower()
        else:
            # Fallback to common column names
            question_text = str(row.get('question', row.get('problem_statement', ''))).lower()
            topic = str(row.get('topic', '')).lower()
        
        # Topic matching with flexible scoring
        topic_terms = topic.split()
        prompt_terms = prompt_lower.split()
        for pt in prompt_terms:
            for tt in topic_terms:
                # Exact match gets high score
                if pt == tt:
                    score += 15
                # Partial match gets lower score
                elif pt in tt or tt in pt:
                    score += 8
        
        # Score based on keyword matches in question text and topic
        for keyword in keywords:
            if keyword in question_text:
                score += 10
            if keyword in topic:
                score += 8  # Increased from 5
            if keyword in answer_text if 'identification' in filename else keyword in (option_text if 'multiple_choice' in filename or 'checkbox' in filename else ''):
                score += 6
        
        # Score based on exact phrase matches
        if 'machine learning' in prompt_lower or 'ml' in prompt_lower:
            if any(term in question_text for term in ['machine learning', 'ml', 'neural', 'ai', 'artificial']):
                score += 25
            if any(term in topic for term in ['machine learning', 'ml', 'neural', 'ai', 'artificial']):
                score += 20
        if 'ai' in prompt_lower or 'artificial' in prompt_lower:
            if any(term in question_text for term in ['ai', 'artificial', 'intelligence']):
                score += 25
            if any(term in topic for term in ['ai', 'artificial', 'intelligence']):
                score += 20
        if 'e-sports' in prompt_lower or 'esports' in prompt_lower:
            if any(term in question_text for term in ['e-sports', 'esports', 'gaming', 'sport']):
                score += 25
            if any(term in topic for term in ['e-sports', 'esports', 'gaming', 'sport']):
                score += 20
        
        # Standard programming concepts
        if 'even' in prompt and 'even' in question_text:
            score += 20
        if 'odd' in prompt and 'odd' in question_text:
            score += 20
        if 'function' in prompt and 'function' in question_text:
            score += 15
        if 'loop' in prompt and ('for' in question_text or 'while' in question_text):
            score += 15
        if 'condition' in prompt and ('if' in question_text or 'else' in question_text):
            score += 15
        if 'python' in prompt and 'python' in question_text:
            score += 15
        if 'variable' in prompt and 'variable' in question_text:
            score += 15
        if 'data' in prompt and 'data' in question_text:
            score += 10
        if 'type' in prompt and 'type' in question_text:
            score += 10
        
        # For multiple choice, also check options
        if ('multiple_choice' in filename or 'checkbox' in filename) and 'option_text' in locals():
            for keyword in keywords:
                if keyword in option_text:
                    score += 5
        
        # For identification, also check answer
        if 'identification' in filename and 'answer_text' in locals():
            for keyword in keywords:
                if keyword in answer_text:
                    score += 8
        
        # Language-specific scoring
        if 'python' in prompt and 'python' in str(row.get('language', '')).lower():
            score += 10
        if 'java' in prompt and 'java' in str(row.get('language', '')).lower():
            score += 10
        if 'c++' in prompt and 'c++' in str(row.get('language', '')).lower():
            score += 10
        
        return score
    
    def _map_dataset_row_to_example(self, row: Dict, filename: str, question_type: str) -> Dict[str, Any]:
        """Map dataset row to standard example format"""
        if 'identification' in filename:
            return {
                'problem_id': '',
                'topic': row.get('topic', ''),
                'language': 'Python',
                'problem_statement': row.get('question', ''),
                'unit_tests': '',
                'expected_outputs': row.get('answer', ''),
                'scoring_criteria': 'Correct answer: 100 points',
                'max_score': 100,
                'hints': '',
                'source_dataset': filename,
                'question_type': question_type
            }
        elif 'multiple_choice' in filename:
            options = [row.get('A', ''), row.get('B', ''), row.get('C', ''), row.get('D', '')]
            # Clean up the correct letter; some CSVs may contain things like " A" or "B ".
            raw_correct = str(row.get('correct', 'A') or 'A')
            raw_correct = raw_correct.strip()
            letter = raw_correct[0].upper() if raw_correct else 'A'
            correct_idx = ord(letter) - ord('A')
            correct_answer = options[correct_idx] if 0 <= correct_idx < len(options) else options[0]
            return {
                'problem_id': '',
                'topic': row.get('topic', ''),
                'language': 'Python',
                'problem_statement': row.get('question', ''),
                'unit_tests': '',
                'expected_outputs': correct_answer,
                'scoring_criteria': 'Correct answer: 100 points',
                'max_score': 100,
                'hints': '',
                'source_dataset': filename,
                'question_type': question_type,
                'options': options,
                'correct_answer': correct_answer
            }
        elif 'true_false' in filename:
            return {
                'problem_id': '',
                'topic': row.get('topic', ''),
                'language': 'Python',
                'problem_statement': row.get('statement', ''),
                'unit_tests': '',
                'expected_outputs': row.get('answer', 'True'),
                'scoring_criteria': 'Correct answer: 100 points',
                'max_score': 100,
                'hints': '',
                'source_dataset': filename,
                'question_type': question_type,
                'options': ['True', 'False'],
                'correct_answer': row.get('answer', 'True')
            }
        elif 'enumeration' in filename:
            return {
                'problem_id': '',
                'topic': row.get('topic', ''),
                'language': 'Python',
                'problem_statement': row.get('question', ''),
                'unit_tests': '',
                'expected_outputs': row.get('answer', ''),
                'scoring_criteria': 'Correct answer: 100 points',
                'max_score': 100,
                'hints': '',
                'source_dataset': filename,
                'question_type': question_type
            }
        elif 'coding' in filename:
            return {
                'problem_id': row.get('problem_id', ''),
                'topic': row.get('topic', ''),
                'language': row.get('language', 'Python'),
                'problem_statement': row.get('problem_statement', ''),
                'unit_tests': row.get('unit_tests', ''),
                'expected_outputs': row.get('expected_outputs', ''),
                'scoring_criteria': row.get('scoring_criteria', 'Correct implementation: 100 points'),
                'max_score': row.get('max_score', 100),
                'hints': row.get('hints', ''),
                'source_dataset': filename,
                'question_type': question_type
            }
        else:
            # Fallback
            return {
                'problem_id': '',
                'topic': row.get('topic', ''),
                'language': 'Python',
                'problem_statement': row.get('question', row.get('problem_statement', '')),
                'unit_tests': '',
                'expected_outputs': '',
                'scoring_criteria': 'Correct answer: 100 points',
                'max_score': 100,
                'hints': '',
                'source_dataset': filename,
                'question_type': question_type
            }
    
    def _create_ai_prompt(self, user_prompt: str, context_examples: List[Dict[str, Any]], language: str = None) -> str:
        """Create AI prompt with dataset context"""
        
        # Build context section
        context_section = "DATASET CONTEXT (examples from existing questions):\n\n"
        
        for i, example in enumerate(context_examples, 1):
            context_section += f"Example {i}:\n"
            context_section += f"Topic: {example['topic']}\n"
            context_section += f"Language: {example['language']}\n"
            context_section += f"Problem: {example['problem_statement']}\n"
            if example['unit_tests']:
                context_section += f"Unit Tests: {example['unit_tests'][:200]}...\n"
            if example['hints']:
                context_section += f"Hints: {example['hints']}\n"
            context_section += f"Scoring: {example['scoring_criteria']}\n"
            context_section += f"Max Score: {example['max_score']}\n\n"
        
        # Create the main prompt
        prompt = f"""You are an expert programming instructor. Generate a coding question based on the user's request and the context from existing questions in our dataset.

USER REQUEST: {user_prompt}

{context_section}

INSTRUCTIONS:
1. Generate a coding question that matches the user's request
2. Use the dataset examples as inspiration for:
   - Question structure and format
   - Difficulty level
   - Unit test patterns
   - Scoring criteria
   - Hints format
3. Make the question clear, specific, and educational
4. Include appropriate unit tests
5. Provide helpful hints
6. Set reasonable scoring criteria

REQUIRED OUTPUT FORMAT (JSON):
{{
    "question_text": "The main question/problem statement",
    "sample_code": "Optional sample code or hints",
    "unit_tests": "Unit tests for the question",
    "expected_outputs": "Expected outputs for the unit tests",
    "scoring_criteria": "How the question should be scored",
    "max_score": 100,
    "hints": "Helpful hints for students",
    "topic": "Topic category (e.g., Algorithms, Conditionals, Loops)",
    "language": "{language or 'Python'}"
}}

Generate a question that follows the patterns from the dataset examples but is unique and educational."""

        return prompt
    
    def _create_ai_prompt_with_type(self, user_prompt: str, context_examples: List[Dict[str, Any]], language: str = None, question_type: str = 'coding') -> str:
        """Create AI prompt with dataset context and question type specification"""
        
        # Build context section
        context_section = "DATASET CONTEXT (examples from existing questions):\n\n"
        
        for i, example in enumerate(context_examples, 1):
            context_section += f"Example {i}:\n"
            context_section += f"Topic: {example['topic']}\n"
            context_section += f"Language: {example['language']}\n"
            context_section += f"Problem: {example['problem_statement']}\n"
            
            # Add options and correct answers for multiple choice and checkbox
            if 'options' in example and example['options']:
                context_section += f"Options: {example['options']}\n"
            if 'correct_answer' in example and example['correct_answer']:
                context_section += f"Correct Answer: {example['correct_answer']}\n"
            
            if example['unit_tests']:
                context_section += f"Unit Tests: {example['unit_tests'][:200]}...\n"
            if example.get('expected_outputs'):
                context_section += f"Expected Outputs: {example['expected_outputs'][:150]}...\n"
            if example['hints']:
                context_section += f"Hints: {example['hints']}\n"
            context_section += f"Scoring: {example['scoring_criteria']}\n"
            context_section += f"Max Score: {example['max_score']}\n\n"
        
        # Define question type specific instructions
        question_type_instructions = {
            'coding': {
                'description': 'a coding question',
                'format': '''{
    "question_text": "The main question/problem statement",
    "sample_code": "Optional sample code or hints",
    "unit_tests": "Unit tests for the question",
    "expected_outputs": "Expected outputs for the unit tests",
    "scoring_criteria": "How the question should be scored",
    "max_score": 100,
    "hints": "Helpful hints for students",
    "topic": "Topic category (e.g., Algorithms, Conditionals, Loops)",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Include appropriate unit tests",
                    "Provide helpful hints",
                    "Set reasonable scoring criteria",
                    "Make the question clear, specific, and educational"
                ]
            },
            'multiple_choice': {
                'description': 'a multiple choice question',
                'format': '''{
    "question_text": "The main question",
    "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
    "correct_answer": "The complete text of the correct option (e.g., 'Option B text', NOT just 'B')",
    "explanation": "Explanation of why this answer is correct",
    "topic": "Topic category",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Provide 4 options with full text descriptions",
                    "Make sure only one option is correct",
                    "The correct_answer field MUST contain the COMPLETE TEXT of the correct option, NOT just the letter (e.g., use 'Machine Learning' not 'B')",
                    "Include an explanation for the correct answer",
                    "Make distractors plausible but incorrect"
                ]
            },
            'true_false': {
                'description': 'a true/false question',
                'format': '''{
    "question_text": "The statement to evaluate",
    "options": ["True", "False"],
    "correct_answer": "True or False",
    "explanation": "Explanation of why the answer is correct",
    "topic": "Topic category",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Create a clear statement that can be evaluated as true or false",
                    "Include an explanation for the correct answer",
                    "Make the statement unambiguous"
                ]
            },
            'identification': {
                'description': 'an identification question',
                'format': '''{
    "question_text": "The question asking for identification",
    "options": ["Answer field (text input)"],
    "correct_answer": "The expected answer",
    "explanation": "Explanation of the correct answer",
    "topic": "Topic category",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Ask for identification of a concept, term, or code element",
                    "Provide the correct answer",
                    "Include an explanation"
                ]
            },
            'enumeration': {
                'description': 'an enumeration question',
                'format': '''{
    "question_text": "The question asking for enumeration",
    "options": ["Answer field (text input)"],
    "correct_answer": ["Answer 1", "Answer 2", "Answer 3"],
    "explanation": "Explanation of the correct answers",
    "topic": "Topic category",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Ask for multiple items to be listed",
                    "Provide all correct answers",
                    "Include an explanation"
                ]
            },
            'checkbox': {
                'description': 'a checkbox question',
                'format': '''{
    "question_text": "The main question",
    "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
    "correct_answer": ["Complete text of correct option 1", "Complete text of correct option 2"],
    "explanation": "Explanation of why these answers are correct",
    "topic": "Topic category",
    "language": "Python"
}''',
                'specific_instructions': [
                    "Provide 4 options with full text descriptions",
                    "Allow multiple correct answers",
                    "The correct_answer array MUST contain the COMPLETE TEXT of each correct option, NOT just letters (e.g., use ['Machine Learning', 'Deep Learning'] not ['B', 'D'])",
                    "Include an explanation for the correct answers",
                    "Make sure incorrect options are clearly wrong"
                ]
            }
        }
        
        type_info = question_type_instructions.get(question_type, question_type_instructions['coding'])
        
        # Create the main prompt
        prompt = f"""You are an expert programming instructor. Generate {type_info['description']} based on the user's request and the context from existing questions in our dataset.

USER REQUEST: {user_prompt}
QUESTION TYPE: {question_type.upper()}

{context_section}

INSTRUCTIONS:
1. Generate {type_info['description']} that matches the user's request
2. IMPORTANT: If the user request is about a specific topic (like "E-sports ML"), generate a question that is DIRECTLY related to that topic, not just a generic question
3. Use the dataset examples as a STRICT template for:
   - Question structure and format
   - Difficulty level  
   - Answer patterns
   - Topic categorization
4. {chr(10).join(f"   - {instruction}" for instruction in type_info['specific_instructions'])}

REQUIRED OUTPUT FORMAT (JSON):
{type_info['format']}

Generate a question that follows the EXACT patterns from the dataset examples and is DIRECTLY relevant to the user's request."""

        return prompt
    
    def _send_lm_studio_request(self, prompt: str, max_retries: int = 2) -> Optional[str]:
        """Send request to LM Studio and return response with retry logic"""
        for attempt in range(max_retries + 1):
            try:
                payload = {
                    "model": "local-model",  # LM Studio uses this for local models
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,  # Higher temperature for creative question generation
                    "max_tokens": 1000,
                    "stream": False
                }
                
                print(f"Sending request to LM Studio (attempt {attempt + 1}/{max_retries + 1})...")
                response = requests.post(
                    self.lm_studio_url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        print("LM Studio request successful!")
                        return content
                    else:
                        print("LM Studio returned empty response")
                        return None
                else:
                    print(f"LM Studio API error: {response.status_code} - {response.text}")
                    if attempt < max_retries:
                        print(f"Retrying in 2 seconds...")
                        import time
                        time.sleep(2)
                        continue
                    return None
                    
            except requests.exceptions.Timeout:
                print(f"LM Studio request timed out (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    print(f"Retrying in 2 seconds...")
                    import time
                    time.sleep(2)
                    continue
                return None
            except Exception as e:
                print(f"Error sending request to LM Studio (attempt {attempt + 1}/{max_retries + 1}): {e}")
                if attempt < max_retries:
                    print(f"Retrying in 2 seconds...")
                    import time
                    time.sleep(2)
                    continue
                return None
        
        return None
    
    def _fix_correct_answer(self, question_data: Dict[str, Any], question_type: str) -> Dict[str, Any]:
        """Fix correct_answer if it's just a letter (e.g., 'B') and convert it to the actual option text"""
        if question_type not in ['multiple_choice', 'checkbox', 'true_false']:
            return question_data
        
        options = question_data.get('options', [])
        if not options or len(options) == 0:
            return question_data
        
        correct_answer = question_data.get('correct_answer', '')
        
        if question_type == 'checkbox':
            # Handle list of correct answers
            if isinstance(correct_answer, list):
                fixed_answers = []
                for ans in correct_answer:
                    # If answer is a single letter like 'B', convert to option text
                    if len(str(ans).strip()) == 1 and str(ans).strip().upper() in ['A', 'B', 'C', 'D', 'E']:
                        idx = ord(str(ans).strip().upper()) - ord('A')
                        if 0 <= idx < len(options):
                            fixed_answers.append(options[idx])
                        else:
                            fixed_answers.append(str(ans))
                    else:
                        fixed_answers.append(str(ans))
                question_data['correct_answer'] = fixed_answers
        else:
            # Handle single correct answer
            if len(str(correct_answer).strip()) == 1 and str(correct_answer).strip().upper() in ['A', 'B', 'C', 'D', 'E', 'T', 'F']:
                # It's a letter, convert to text
                letter = str(correct_answer).strip().upper()
                if question_type == 'true_false':
                    if letter == 'T':
                        question_data['correct_answer'] = 'True'
                    elif letter == 'F':
                        question_data['correct_answer'] = 'False'
                else:
                    # For multiple choice, convert letter to option text
                    idx = ord(letter) - ord('A')
                    if 0 <= idx < len(options):
                        question_data['correct_answer'] = options[idx]
        
        return question_data
    
    def _normalize_question_output(self, question_data: Dict[str, Any], question_type: str) -> Dict[str, Any]:
        """Force the returned payload to match the requested question type structure."""
        if not isinstance(question_data, dict):
            return question_data
        
        question_data['question_type'] = question_type
        
        if question_type == 'checkbox':
            options = question_data.get('options', [])
            # Convert dicts/strings into a clean list of option strings
            if isinstance(options, dict):
                options = list(options.values())
            elif isinstance(options, str):
                options = re.split(r'[\n;,]+', options)
            options = [str(opt).strip() for opt in options if str(opt).strip()]
            question_data['options'] = options
            
            correct_answer = question_data.get('correct_answer', [])
            if isinstance(correct_answer, str):
                parts = re.split(r'[\n;,]+', correct_answer)
                correct_answer = [part.strip() for part in parts if part.strip()]
            elif isinstance(correct_answer, (set, tuple)):
                correct_answer = [str(part).strip() for part in correct_answer if str(part).strip()]
            elif isinstance(correct_answer, list):
                correct_answer = [str(part).strip() for part in correct_answer if str(part).strip()]
            else:
                correct_answer = []
            
            # If the answers are still single letters, convert them using options
            if options:
                converted = []
                for ans in correct_answer:
                    if len(ans) == 1 and ans.upper() in ['A', 'B', 'C', 'D', 'E']:
                        idx = ord(ans.upper()) - ord('A')
                        if 0 <= idx < len(options):
                            converted.append(options[idx])
                        else:
                            converted.append(ans)
                    else:
                        converted.append(ans)
                correct_answer = converted
            
            question_data['correct_answer'] = correct_answer
        
        return question_data

    def _finalize_question_output(self, question_data: Dict[str, Any], question_type: str) -> Dict[str, Any]:
        """Apply all post-processing steps before returning AI output."""
        question_data = self._fix_correct_answer(question_data, question_type)
        return self._normalize_question_output(question_data, question_type)
    
    def generate_question(self, prompt: str, language: str = None, question_type: str = 'coding') -> Dict[str, Any]:
        """Generate a question using LM Studio with dataset context, or fallback to datasets if LM Studio unavailable"""
        context_examples: List[Dict[str, Any]] = []
        try:
            # Search for relevant context from datasets based on question type
            print(f"Searching datasets for context related to: '{prompt}' (type: {question_type})")
            context_examples = self._search_datasets_for_context(prompt, language, question_type)
            
            if context_examples:
                print(f"Found {len(context_examples)} relevant examples from datasets")
                for i, example in enumerate(context_examples[:3], 1):
                    print(f"  {i}. {example['topic']} - {example['problem_statement'][:50]}...")
            else:
                print("No relevant examples found in datasets")
            
            # Check if LM Studio is available
            if self._check_lm_studio_available():
                print("LM Studio is available, using AI generation with dataset context...")
                question_data = self._generate_with_lm_studio(prompt, context_examples, language, question_type)
            else:
                print("LM Studio not available, using dataset-based fallback generation...")
                question_data = self._generate_from_datasets(prompt, context_examples, language, question_type)
                
        except Exception as e:
            error_msg = str(e)
            # If it's a "no active datasets" error, re-raise it so the user sees the message
            if "No active datasets available" in error_msg:
                print(f"No active datasets available: {error_msg}")
                raise
            print(f"Error in question generation: {e}")
            # Ensure we have a safe default for context_examples even if the
            # failure happened before they were populated.
            context_examples = context_examples or []
            question_data = self._create_fallback_question(prompt, context_examples, language, question_type)

        # Post-process: for coding questions we do NOT want to send any sample
        # starter code back to the frontend. Keep only the question text,
        # tests, hints, etc.
        if question_type == 'coding' and isinstance(question_data, dict):
            question_data['sample_code'] = ""

        return question_data
    
    def _generate_with_lm_studio(self, prompt: str, context_examples: List[Dict[str, Any]], language: str = None, question_type: str = 'coding') -> Dict[str, Any]:
        """Generate question using LM Studio with dataset context"""
        try:
            # Create AI prompt with context and question type
            ai_prompt = self._create_ai_prompt_with_type(prompt, context_examples, language, question_type)
            
            # Generate question using LM Studio with retries
            print("Generating question using LM Studio...")
            ai_response = self._send_lm_studio_request(ai_prompt)
            
            if ai_response:
                # Parse AI response
                try:
                    question_data = json.loads(ai_response)
                    print("Successfully generated question using LM Studio")
                    
                    # Fix correct_answer if it's just a letter (convert to actual text)
                    return self._finalize_question_output(question_data, question_type)
                except json.JSONDecodeError as e:
                    print(f"Error parsing LM Studio response: {e}")
                    print("Response content:", ai_response[:200] + "..." if len(ai_response) > 200 else ai_response)
                    # Try to extract JSON from the response
                    json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                    if json_match:
                        try:
                            question_data = json.loads(json_match.group(0))
                            print("Successfully extracted JSON from LM Studio response")
                            
                            # Fix correct_answer if it's just a letter (convert to actual text)
                            return self._finalize_question_output(question_data, question_type)
                        except json.JSONDecodeError:
                            pass
                    
                    # If all parsing fails, create a question based on the AI response
                    return self._create_question_from_ai_response(ai_response, prompt, context_examples, language, question_type)
            else:
                # LM Studio failed completely, check if it's still available
                if self._check_lm_studio_available():
                    print("LM Studio is still available but request failed, retrying with simpler prompt...")
                    # Try with a simpler prompt
                    simple_prompt = f"""Generate a {question_type} question based on this request: "{prompt}"

Use this example as a template:
{context_examples[0]['problem_statement'] if context_examples else 'Write a Python function'}

Return JSON format based on question type: {question_type}"""
                    
                    retry_response = self._send_lm_studio_request(simple_prompt)
                    if retry_response:
                        try:
                            question_data = json.loads(retry_response)
                            print("Successfully generated question using LM Studio (retry)")
                            
                            # Fix correct_answer if it's just a letter (convert to actual text)
                            return self._finalize_question_output(question_data, question_type)
                        except json.JSONDecodeError:
                            return self._create_question_from_ai_response(retry_response, prompt, context_examples, language, question_type)
                
                print("LM Studio generation failed completely, using dataset fallback")
                return self._generate_from_datasets(prompt, context_examples, language, question_type)
                
        except Exception as e:
            print(f"Error in LM Studio generation: {e}")
            return self._generate_from_datasets(prompt, context_examples, language, question_type)
    
    def _generate_from_datasets(self, prompt: str, context_examples: List[Dict[str, Any]], language: str = None, question_type: str = 'coding') -> Dict[str, Any]:
        """Generate question directly from dataset examples when LM Studio is not available"""
        try:
            # Import the existing dataset generation function
            from app.routes import generate_question_from_datasets
            
            print(f"Using dataset fallback for {question_type} question...")

            # For coding questions, strengthen language awareness by explicitly
            # including the language name in the prompt so that
            # generate_question_from_datasets() can filter by the CSV
            # 'language' column (e.g., only Java problems when language='Java').
            ds_prompt = prompt
            if question_type == 'coding' and language:
                try:
                    lang_lower = str(language).lower()
                    if lang_lower not in str(prompt or "").lower():
                        ds_prompt = f"{language} {prompt or ''}".strip()
                except Exception:
                    ds_prompt = prompt
            
            # Use the existing dataset generation function
            dataset_result = generate_question_from_datasets(ds_prompt, question_type)
            
            # Convert to the expected format
            return {
                "question_text": dataset_result.get('text', ''),
                "sample_code": "",
                "unit_tests": "",
                "expected_outputs": "",
                "scoring_criteria": "Correct answer: 100 points",
                "max_score": 100,
                "hints": "",
                "topic": "Programming",
                "language": language or "Python",
                "question_type": question_type,
                "options": dataset_result.get('options', []),
                "correct_answer": dataset_result.get('correct_answer', ''),
                "explanation": dataset_result.get('explanation', '')
            }
                
        except Exception as e:
            error_msg = str(e)
            # Check if it's the "no active datasets" error
            if "No active datasets available" in error_msg or "No datasets available" in error_msg:
                print(f"No active datasets available: {error_msg}")
                # Re-raise with a clear message that will be shown to the user
                raise Exception("No active datasets available. Please activate at least one dataset in the Manage Datasets page to generate questions without AI.")
            print(f"Error in dataset generation: {e}")
            return self._create_fallback_question(prompt, context_examples, language, question_type)
    
    def _create_question_from_template(self, prompt: str, template: Dict[str, Any], language: str = None) -> str:
        """Create a question by modifying a template based on the user's prompt"""
        # Extract key concepts from the prompt
        prompt_lower = prompt.lower()
        
        # Get the template problem statement
        template_problem = template.get('problem_statement', '')
        
        # Modify the template based on the prompt
        if 'even' in prompt_lower and 'odd' in prompt_lower:
            return f"Write a {language or 'Python'} function that determines if a number is even or odd based on the user's request: {prompt}"
        elif 'even' in prompt_lower:
            return f"Write a {language or 'Python'} function that works with even numbers: {prompt}"
        elif 'odd' in prompt_lower:
            return f"Write a {language or 'Python'} function that works with odd numbers: {prompt}"
        elif 'function' in prompt_lower:
            return f"Write a {language or 'Python'} function that: {prompt}"
        elif 'loop' in prompt_lower or 'iteration' in prompt_lower:
            return f"Write a {language or 'Python'} program using loops to: {prompt}"
        elif 'condition' in prompt_lower or 'if' in prompt_lower:
            return f"Write a {language or 'Python'} program using conditional statements to: {prompt}"
        else:
            # Use the template but modify it with the user's request
            return f"Write a {language or 'Python'} program that {prompt.lower()}. Use the following as inspiration: {template_problem[:100]}..."
    
    def _create_question_from_ai_response(self, ai_response: str, prompt: str, context_examples: List[Dict[str, Any]], language: str = None, question_type: str = 'coding') -> Dict[str, Any]:
        """Create a question from AI response when JSON parsing fails"""
        try:
            # Extract question text from the response
            lines = ai_response.split('\n')
            question_text = ""
            unit_tests = ""
            hints = ""
            options = []
            correct_answer = ""
            
            # Try to extract structured information
            for line in lines:
                line = line.strip()
                if 'question' in line.lower() and ':' in line:
                    question_text = line.split(':', 1)[1].strip()
                elif 'test' in line.lower() and ':' in line:
                    unit_tests = line.split(':', 1)[1].strip()
                elif 'hint' in line.lower() and ':' in line:
                    hints = line.split(':', 1)[1].strip()
                elif 'option' in line.lower() and ':' in line:
                    options.append(line.split(':', 1)[1].strip())
                elif 'answer' in line.lower() and ':' in line:
                    correct_answer = line.split(':', 1)[1].strip()
            
            # If no structured info found, use the first meaningful line as question
            if not question_text:
                for line in lines:
                    if line.strip() and len(line.strip()) > 10:
                        question_text = line.strip()
                        break
            
            # Fallback to prompt-based question
            if not question_text:
                question_text = f"Write a {language or 'Python'} function that: {prompt}"
            
            # Use context examples for additional fields
            template = context_examples[0] if context_examples else {}
            
            # Set default options based on question type
            if not options:
                if question_type == 'multiple_choice' or question_type == 'checkbox':
                    options = ['Option A', 'Option B', 'Option C', 'Option D']
                elif question_type == 'true_false':
                    options = ['True', 'False']
                elif question_type in ['identification', 'enumeration']:
                    options = ['Answer field (text input)']
            
            return self._finalize_question_output({
                "question_text": question_text,
                "sample_code": hints or template.get('hints', ''),
                "unit_tests": unit_tests or template.get('unit_tests', ''),
                "expected_outputs": template.get('expected_outputs', ''),
                "scoring_criteria": template.get('scoring_criteria', 'Correct implementation: 100 points'),
                "max_score": template.get('max_score', 100),
                "hints": hints or template.get('hints', ''),
                "topic": template.get('topic', 'Programming'),
                "language": language or template.get('language', 'Python'),
                "question_type": question_type,
                "options": options,
                "correct_answer": correct_answer or template.get('correct_answer', ''),
                "explanation": ""
            }, question_type)
            
        except Exception as e:
            print(f"Error creating question from AI response: {e}")
            return self._create_fallback_question(prompt, context_examples, language, question_type)
    
    def _create_fallback_question(self, prompt: str, context_examples: List[Dict[str, Any]], language: str = None, question_type: str = 'coding') -> Dict[str, Any]:
        """Create a fallback question when AI generation fails"""
        
        # Use the most relevant example as a template
        if context_examples:
            template = context_examples[0]
            
            # Modify the template based on the prompt
            question_text = f"Write a {language or 'Python'} function that {prompt.lower()}"
            
            return self._normalize_question_output({
                "question_text": question_text,
                "sample_code": template.get('hints', ''),
                "unit_tests": template.get('unit_tests', ''),
                "expected_outputs": template.get('expected_outputs', ''),
                "scoring_criteria": template.get('scoring_criteria', 'Correct implementation: 100 points'),
                "max_score": template.get('max_score', 100),
                "hints": template.get('hints', ''),
                "topic": template.get('topic', 'Programming'),
                "language": language or template.get('language', 'Python'),
                "question_type": question_type,
                "options": [],
                "correct_answer": "",
                "explanation": ""
            }, question_type)
        else:
            # Create a basic question
            return self._normalize_question_output({
                "question_text": f"Write a {language or 'Python'} function that {prompt.lower()}",
                "sample_code": "",
                "unit_tests": "",
                "expected_outputs": "",
                "scoring_criteria": "Correct implementation: 100 points",
                "max_score": 100,
                "hints": "",
                "topic": "Programming",
                "language": language or "Python",
                "question_type": question_type,
                "options": [],
                "correct_answer": "",
                "explanation": ""
            }, question_type)

# Create global instance
ai_question_generator = AIQuestionGenerator()