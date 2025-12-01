"""
Custom Code Evaluation System
Replaces LM Studio AI with automated unit testing and scoring
Now integrates AI evaluation as initial checker
"""

import os
import sys
import tempfile
import subprocess
import shutil
import glob
import re
from typing import Tuple, List, Dict, Any, Optional
import pandas as pd

# Import AI evaluator
try:
    from .ai_evaluator import ai_evaluator
    # Check if AI is actually available by testing LM Studio
    AI_AVAILABLE = ai_evaluator._check_lm_studio_available()
    if not AI_AVAILABLE:
        print("AI evaluator available but LM Studio is not running - using unit tests only")
except (ImportError, AttributeError):
    AI_AVAILABLE = False
    print("AI evaluator not available - running without AI integration")


class CodeEvaluator:
    """Custom code evaluation system that uses unit tests and expected outputs"""
    
    def __init__(self):
        self.supported_languages = {
            'python': self._evaluate_python,
            'c': self._evaluate_c,
            'c++': self._evaluate_cpp,
            'cpp': self._evaluate_cpp,
            'java': self._evaluate_java,
            'c#': self._evaluate_csharp,
            'csharp': self._evaluate_csharp,
            'javascript': self._evaluate_javascript,
            'js': self._evaluate_javascript
        }
    
    def evaluate_code(self, code: str, problem_id: int, language: str) -> Tuple[bool, int, str]:
        """
        Evaluate student code using AI analysis first, then unit tests
        
        Args:
            code: Student's code submission
            problem_id: ID of the problem from the dataset
            language: Programming language of the code
            
        Returns:
            Tuple of (is_correct, score_percentage, feedback)
        """
        try:
            # Load problem data from CSV
            problem_data = self._load_problem_data(problem_id)
            if not problem_data:
                return False, 0, "Problem not found in dataset"
            
            # Normalize language name
            lang_key = language.lower().strip()
            if lang_key not in self.supported_languages:
                return False, 0, f"Unsupported language: {language}"

            has_unit_tests = bool(problem_data.get('unit_tests') and str(problem_data.get('unit_tests')).strip())
            if not has_unit_tests:
                return self._evaluate_ai_only_general(code, problem_data, language)
            
            # Step 1: AI Evaluation (if available)
            ai_available = self._ai_available()
            ai_correct = None
            ai_confidence = 0
            ai_feedback = ""
            
            if ai_available:
                try:
                    ai_correct, ai_confidence, ai_feedback = ai_evaluator.evaluate_code(
                        code, 
                        problem_data['problem_statement'], 
                        language,
                        problem_data.get('unit_tests', '')
                    )
                    print(f"AI Evaluation: Correct={ai_correct}, Confidence={ai_confidence}")
                except Exception as e:
                    print(f"AI evaluation failed: {e}")
                    ai_feedback = f"AI evaluation unavailable: {str(e)}"
            
            # Step 2: Unit Test Evaluation
            eval_func = self.supported_languages[lang_key]
            unit_correct, unit_score, unit_feedback = eval_func(code, problem_data)
            
            # Step 3: Combine Results
            return self._combine_evaluation_results(
                ai_available, ai_correct, ai_confidence, ai_feedback,
                unit_correct, unit_score, unit_feedback,
                problem_data
            )
            
        except Exception as e:
            return False, 0, f"Evaluation error: {str(e)}"
    
    def evaluate_code_with_custom_tests(self, code: str, unit_tests: str, language: str, interactive_inputs: str = None, expected_outputs: str = None) -> Tuple[bool, int, str]:
        """Evaluate code using custom unit tests provided directly with AI analysis"""
        try:
            # Create a mock problem data structure
            problem_data = {
                'problem_id': 'custom',
                'topic': 'Custom',
                'language': language,
                'problem_statement': 'Custom problem',
                'unit_tests': unit_tests,
                'expected_outputs': expected_outputs or '',
                'scoring_criteria': 'Auto-graded by custom unit tests',
                'max_score': 100,
                'interactive_inputs': interactive_inputs or ''
            }
            
            # Detect language and get appropriate evaluator
            lang_key = language.lower()
            if lang_key not in self.supported_languages:
                return False, 0, f"Unsupported language: {language}"

            has_unit_tests = bool(unit_tests and unit_tests.strip())
            if not has_unit_tests:
                return self._evaluate_ai_only_general(code, problem_data, language)
            
            # Step 1: AI Evaluation (if available)
            ai_available = self._ai_available()
            ai_correct = None
            ai_confidence = 0
            ai_feedback = ""
            
            if ai_available:
                try:
                    ai_correct, ai_confidence, ai_feedback = ai_evaluator.evaluate_code(
                        code, 
                        problem_data['problem_statement'], 
                        language,
                        unit_tests
                    )
                    print(f"AI Evaluation (Custom): Correct={ai_correct}, Confidence={ai_confidence}")
                except Exception as e:
                    print(f"AI evaluation failed: {e}")
                    ai_feedback = f"AI evaluation unavailable: {str(e)}"
            
            # Step 2: Unit Test Evaluation
            eval_func = self.supported_languages[lang_key]
            unit_correct, unit_score, unit_feedback = eval_func(code, problem_data)
            
            # Step 3: Combine Results
            return self._combine_evaluation_results(
                ai_available, ai_correct, ai_confidence, ai_feedback,
                unit_correct, unit_score, unit_feedback,
                problem_data
            )
            
        except Exception as e:
            return False, 0, f"Custom evaluation error: {str(e)}"
    
    def _combine_evaluation_results(self, ai_available: bool, ai_correct: bool, ai_confidence: int, ai_feedback: str,
                                  unit_correct: bool, unit_score: int, unit_feedback: str,
                                  problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """
        Combine AI evaluation and unit test results according to the specified logic:
        - If AI and unit test both say correct: perfect score
        - If AI says wrong but unit test says right: go with unit test
        - If AI says right but unit test says wrong: go with unit test (unit test is authoritative)
        - If both say wrong: go with unit test score
        """
        max_score = int(problem_data['max_score'])
        
        # Build comprehensive feedback
        feedback_parts = []

        # Detect "AI-only" path where there are no unit tests and the unit feedback
        # already contains an AI evaluation header. In that case, avoid duplicating
        # analysis sections and just return the single AI-only block.
        unit_fb_lower = (unit_feedback or "").lower()
        ai_only = ("no unit tests provided" in unit_fb_lower) or unit_fb_lower.strip().startswith("ai evaluation")

        if not ai_only:
            # Add AI feedback if available
            if ai_available and ai_feedback:
                feedback_parts.append(f"AI Analysis (Confidence: {ai_confidence}%):")
                feedback_parts.append(ai_feedback)
                feedback_parts.append("")  # Empty line for separation
            
            # Add unit test feedback section
            feedback_parts.append(f"Unit Test Results:")
            feedback_parts.append(unit_feedback)
        else:
            # Single consolidated block when no unit tests exist
            feedback_parts.append(unit_feedback)
        
        # Determine final result based on the specified logic
        if ai_only:
            # AI-only evaluation path - unit_score already contains the converted AI score
            final_score = unit_score
            # No additional status messages needed, feedback already complete
        elif ai_correct is not None:
            # AI evaluation available
            if unit_correct:
                # Unit test says correct - this is authoritative
                if ai_correct:
                    # Both AI and unit test say correct - perfect score
                    final_score = max_score
                    feedback_parts.append(f"\nSUCCESS: Both AI and unit tests confirm correctness!")
                else:
                    # AI says wrong, unit test says right - go with unit test
                    final_score = max_score
                    feedback_parts.append(f"\nSUCCESS: Unit tests confirm correctness (AI disagreed)")
            else:
                # Unit test says wrong - go with unit test score regardless of AI
                final_score = unit_score
                if ai_correct:
                    feedback_parts.append(f"\nISSUES: Unit tests found issues (AI was incorrect)")
                else:
                    feedback_parts.append(f"\nISSUES: Both AI and unit tests found issues")
        else:
            # No AI evaluation available - use unit test results
            final_score = unit_score
            if not ai_only:
                feedback_parts.append(f"\nINFO: Evaluation based on unit tests only (AI unavailable)")
        
        # Determine if code is correct (score >= 75%)
        is_correct = final_score >= int(0.75 * max_score)
        
        # Combine all feedback
        combined_feedback = "\n".join(feedback_parts)
        
        return is_correct, final_score, combined_feedback
    
    def _load_problem_data(self, problem_id: int) -> Dict[str, Any]:
        """Load problem data from the coding CSV file"""
        try:
            # Get the absolute path to the CSV file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up one level from app/ to project root, then into data/datasets
            project_root = os.path.dirname(current_dir)
            csv_path = os.path.join(project_root, 'app', 'data', 'datasets', 'it_olympics_coding.csv')
            
            if not os.path.exists(csv_path):
                return None
                
            df = pd.read_csv(csv_path)
            problem_row = df[df['problem_id'] == problem_id]
            
            if problem_row.empty:
                return None
                
            row = problem_row.iloc[0]
            
            return {
                'problem_id': row['problem_id'],
                'topic': row['topic'],
                'language': row['language'],
                'problem_statement': row['problem_statement'],
                'unit_tests': row['unit_tests'],
                'expected_outputs': row['expected_outputs'],
                'scoring_criteria': row['scoring_criteria'],
                'max_score': int(row['max_score'])
            }
            
        except Exception as e:
            print(f"Error loading problem data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _evaluate_python(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate Python code using parsed unit tests with partial scoring and name aliasing"""
        try:
            mismatch = self._detect_language_mismatch(code, 'python')
            if mismatch:
                return False, 0, mismatch
            
            # Check if we have interactive inputs
            interactive_inputs = problem_data.get('interactive_inputs', '')
            
            if interactive_inputs and interactive_inputs.strip():
                # Use interactive input evaluation
                return self._evaluate_python_interactive(code, problem_data)
            
            # Extract assert lines from unit tests
            unit_tests_text = problem_data['unit_tests'] or ''
            print(f"DEBUG: unit_tests_text = '{unit_tests_text}' (length: {len(unit_tests_text)})")
            assert_lines: List[str] = []
            
            # Handle different unit test formats
            for raw_line in unit_tests_text.splitlines():
                line = raw_line.strip()
                # Look for assert statements in various formats
                if (line.startswith('assert ') or 
                    line.startswith('assert(') or
                    'assert ' in line or
                    'assert(' in line):
                    # Extract just the assert part
                    if 'assert ' in line:
                        assert_part = line[line.find('assert '):]
                    elif 'assert(' in line:
                        assert_part = line[line.find('assert('):]
                    else:
                        assert_part = line
                    
                    # Clean up the assert statement
                    assert_part = assert_part.strip()
                    if assert_part.endswith(','):
                        assert_part = assert_part[:-1]
                    if assert_part.endswith(';'):
                        assert_part = assert_part[:-1]
                    
                    assert_lines.append(assert_part)
            
            total_asserts = len(assert_lines)
            if total_asserts == 0:
                # No unit tests provided - use AI-only evaluation
                print(f"DEBUG: No unit tests provided, using AI-only evaluation. Unit tests text: '{unit_tests_text}'")
                return self._evaluate_python_ai_only(code, problem_data)
            
            # Determine expected function name from first assert
            expected_func_name = None
            if assert_lines:
                m = re.match(r"assert\s+(\w+)\(", assert_lines[0])
                if m:
                    expected_func_name = m.group(1)
            
            # Determine student's defined function names
            student_func_names = re.findall(r"^def\s+(\w+)\(", code, flags=re.M)
            
            # Replace function name in assert statements with student's function name
            # Use the first function defined by the student
            modified_assert_lines = []
            func_name_replaced = False
            if student_func_names and expected_func_name:
                for a in assert_lines:
                    # Replace expected function name with student's function name
                    modified_a = a.replace(expected_func_name, student_func_names[0])
                    modified_assert_lines.append(modified_a)
                    if modified_a != a:
                        func_name_replaced = True
            else:
                modified_assert_lines = assert_lines
            
            # Build a deterministic test harness for counting passes
            with tempfile.NamedTemporaryFile(mode='w', suffix='_py_eval.py', delete=False) as f:
                # Write student's code
                f.write(code)
                f.write("\n\n")
                
                if total_asserts > 0:
                    # Write runner for assert statements
                    f.write("def __run_asserts__():\n")
                    f.write("    total = 0\n")
                    f.write("    passed = 0\n")
                    f.write("    errors = []\n")
                    for a in modified_assert_lines:
                        safe = a.replace('\\', '\\\\').replace('"', '\\"')
                        f.write("    total += 1\n")
                        f.write("    try:\n")
                        f.write(f"        {a}\n")
                        f.write("        passed += 1\n")
                        f.write("    except Exception as e:\n")
                        f.write(f"        errors.append(\"{safe} -> { '{'}type(e).__name__{'}'}: { '{'}str(e){'}'}\")\n")
                    f.write("    return total, passed, errors\n\n")
                else:
                    # Fallback: execute the entire unit_tests block
                    print(f"DEBUG: Executing fallback - unit_tests_text: '{unit_tests_text}'")
                    f.write("def __run_asserts__():\n")
                    f.write("    total = 1\n")
                    f.write("    passed = 0\n")
                    f.write("    errors = []\n")
                    f.write("    try:\n")
                    # Write the unit tests directly
                    for line in unit_tests_text.splitlines():
                        if line.strip():
                            f.write(f"        {line}\n")
                    f.write("        passed = 1\n")
                    f.write("    except Exception as e:\n")
                    f.write(f"        errors.append(f\"Unit test execution failed: { '{'}str(e){'}'}\")\n")
                    f.write("    return total, passed, errors\n\n")
                
                f.write("if __name__ == '__main__':\n")
                f.write("    t, p, errs = __run_asserts__()\n")
                f.write("    import json, sys\n")
                f.write("    print(json.dumps({'total': t, 'passed': p, 'errors': errs}))\n")
                test_file = f.name
            
            try:
                # Run the harness
                result = subprocess.run(
                    [sys.executable, test_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                stdout = (result.stdout or '').strip()
                # Default if runner failed unexpectedly
                if not stdout:
                    return False, 0, f"No output from test harness. Stderr: {result.stderr}"
                try:
                    import json
                    data = json.loads(stdout.splitlines()[-1])
                    total = int(data.get('total', 0)) or total_asserts
                    passed = int(data.get('passed', 0))
                    errors = data.get('errors', [])
                except Exception:
                    # Fallback parse
                    total = total_asserts
                    passed = 0
                    errors = [result.stderr]
                
                max_score = int(problem_data['max_score'])
                
                # Apply flexible scoring based on test results
                if total == 0:
                    score = 0
                elif passed == total:
                    # Perfect score for all tests passed
                    score = max_score
                else:
                    # Calculate score based on percentage of tests passed
                    # Use a more generous scoring scale that rewards partial success
                    percentage = passed / total
                    
                    if percentage >= 0.8:  # 80% or more
                        score = int(round(0.9 * max_score))  # 90% of max score
                    elif percentage >= 0.6:  # 60-79%
                        score = int(round(0.75 * max_score))  # 75% of max score
                    elif percentage >= 0.4:  # 40-59%
                        score = int(round(0.5 * max_score))   # 50% of max score
                    elif percentage >= 0.2:  # 20-39%
                        score = int(round(0.25 * max_score))  # 25% of max score
                    else:  # Less than 20%
                        score = 0
                
                is_correct = score >= 75
                # Build feedback
                fb_lines = [
                    f"Tests passed: {passed}/{total}",
                ]
                if func_name_replaced:
                    fb_lines.append("Note: Function name adjusted to match your code.")
                if errors:
                    fb_lines.append("Errors:\n" + "\n".join(errors[:5]))
                feedback = "\n".join(fb_lines)
                return is_correct, score, feedback
            finally:
                os.unlink(test_file)
        except subprocess.TimeoutExpired:
            return False, 0, "Code execution timed out"
        except Exception as e:
            return False, 0, f"Python evaluation error: {str(e)}"
    
    def _evaluate_python_interactive(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate Python code using interactive input tests"""
        try:
            interactive_inputs = problem_data.get('interactive_inputs', '')
            expected_outputs = problem_data.get('expected_outputs', '')
            
            # Parse interactive inputs and expected outputs
            input_lines = [line.strip() for line in interactive_inputs.splitlines() if line.strip()]
            expected_lines = [line.strip() for line in expected_outputs.splitlines() if line.strip()]
            
            if not input_lines or not expected_lines:
                return False, 0, "Interactive inputs or expected outputs not provided"
            
            if len(input_lines) != len(expected_lines):
                return False, 0, "Number of inputs must match number of expected outputs"
            
            # Create separate files for student code and test harness
            with tempfile.NamedTemporaryFile(mode='w', suffix='_student.py', delete=False) as student_file:
                student_file.write(code)
                student_file_path = student_file.name
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='_test.py', delete=False) as test_file:
                # Write test harness
                test_file.write("import sys\n")
                test_file.write("from io import StringIO\n")
                test_file.write("import subprocess\n")
                test_file.write("\n")
                test_file.write("def __run_interactive_tests__():\n")
                test_file.write("    total_tests = 0\n")
                test_file.write("    passed_tests = 0\n")
                test_file.write("    errors = []\n")
                test_file.write("    \n")
                
                # Generate test cases
                for i, (input_line, expected_line) in enumerate(zip(input_lines, expected_lines)):
                    test_file.write(f"    # Test case {i+1}\n")
                    test_file.write(f"    total_tests += 1\n")
                    test_file.write(f"    try:\n")
                    test_file.write(f"        # Run student code with input\n")
                    test_file.write(f"        result = subprocess.run(\n")
                    test_file.write(f"            [sys.executable, r'{student_file_path}'],\n")
                    test_file.write(f"            input='{input_line}\\n',\n")
                    test_file.write(f"            capture_output=True,\n")
                    test_file.write(f"            text=True,\n")
                    test_file.write(f"            timeout=5\n")
                    test_file.write(f"        )\n")
                    test_file.write(f"        \n")
                    test_file.write(f"        actual_output = result.stdout.strip()\n")
                    test_file.write(f"        \n")
                    test_file.write(f"        # Check if output matches expected\n")
                    test_file.write(f"        if actual_output == '{expected_line}':\n")
                    test_file.write(f"            passed_tests += 1\n")
                    test_file.write(f"        else:\n")
                    test_file.write(f"            errors.append(f'Test {i+1}: Expected \"{expected_line}\", got \"{{actual_output}}\"')\n")
                    test_file.write(f"    except Exception as e:\n")
                    test_file.write(f"        errors.append(f'Test {i+1}: Error - {{str(e)}}')\n")
                    test_file.write(f"    \n")
                
                test_file.write("    return total_tests, passed_tests, errors\n\n")
                test_file.write("if __name__ == '__main__':\n")
                test_file.write("    t, p, errs = __run_interactive_tests__()\n")
                test_file.write("    import json\n")
                test_file.write("    print(json.dumps({'total': t, 'passed': p, 'errors': errs}))\n")
                test_file_path = test_file.name
            
            try:
                # Run the interactive test harness
                result = subprocess.run(
                    [sys.executable, test_file_path],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                stdout = (result.stdout or '').strip()
                if not stdout:
                    return False, 0, f"No output from interactive test harness. Stderr: {result.stderr}"
                
                try:
                    import json
                    data = json.loads(stdout.splitlines()[-1])
                    total = int(data.get('total', 0))
                    passed = int(data.get('passed', 0))
                    errors = data.get('errors', [])
                except Exception:
                    # Fallback parse
                    total = len(input_lines)
                    passed = 0
                    errors = [result.stderr]
                
                max_score = int(problem_data['max_score'])
                
                # Calculate score based on test results
                if total == 0:
                    score = 0
                elif passed == total:
                    score = max_score
                else:
                    percentage = passed / total
                    if percentage >= 0.8:
                        score = int(round(0.9 * max_score))
                    elif percentage >= 0.6:
                        score = int(round(0.75 * max_score))
                    elif percentage >= 0.4:
                        score = int(round(0.5 * max_score))
                    elif percentage >= 0.2:
                        score = int(round(0.25 * max_score))
                    else:
                        score = 0
                
                is_correct = score >= 75
                
                # Build feedback
                fb_lines = [
                    f"Interactive tests passed: {passed}/{total}",
                ]
                if errors:
                    fb_lines.append("Errors:")
                    fb_lines.extend(errors[:5])  # Show first 5 errors
                
                feedback = "\n".join(fb_lines)
                return is_correct, score, feedback
                
            finally:
                # Clean up files
                if os.path.exists(student_file_path):
                    os.unlink(student_file_path)
                if os.path.exists(test_file_path):
                    os.unlink(test_file_path)
                
        except subprocess.TimeoutExpired:
            return False, 0, "Interactive test execution timed out"
        except Exception as e:
            return False, 0, f"Interactive Python evaluation error: {str(e)}"
    
    def _evaluate_python_ai_only(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate Python code using AI-only scoring when no unit tests are provided"""
        has_input = 'input(' in code
        has_print = 'print(' in code

        is_correct, score, feedback = self._evaluate_ai_only_general(code, problem_data, "python")

        notes = []
        if has_input:
            notes.append("Note: Code contains input() calls which cannot be tested without interactive input.")
        if has_print and not has_input:
            notes.append("Note: Code uses print() instead of return statements - consider returning values for better function design.")

        if notes and feedback:
            feedback = f"{feedback}\n" + "\n".join(notes)

        return is_correct, score, feedback

    def _evaluate_ai_only_general(self, code: str, problem_data: Dict[str, Any], language: str) -> Tuple[bool, int, str]:
        """Use AI evaluator exclusively when no unit tests exist.

        If LM Studio / the AI backend is not available, we NO LONGER try to
        score the submission heuristically – we instead return a 0 score and
        explain that automatic grading is unavailable for this question.
        """
        try:
            if not self._ai_available():
                # When there are no unit tests AND the AI evaluator is not
                # reachable, we cannot reliably grade the code. Return 0 with
                # a clear explanation instead of guessing a score.
                return (
                    False,
                    0,
                    "AI Evaluation (No unit tests provided): LM Studio/AI evaluator is unavailable "
                    "and there are no unit tests, so this code cannot be scored automatically."
                )
            
            ai_correct, ai_confidence, ai_feedback = ai_evaluator.evaluate_code(
                code,
                problem_data.get('problem_statement', ''),
                language,
                ""
            )

            code_stripped = code.strip()
            if not code_stripped or len(code_stripped) < 10:
                score = 0
            else:
                if ai_correct:
                    # Default: full credit when AI says the solution is correct.
                    score = 100

                    # If AI explicitly complains about variable naming, optionally drop to 90,
                    # but only when there are non‑single‑letter variable identifiers.
                    feedback_lower = ai_feedback.lower()
                    variable_issue_keywords = [
                        "variable name", "variable naming", "naming", "rename",
                        "more descriptive", "meaningful name"
                    ]
                    has_var_issue = any(k in feedback_lower for k in variable_issue_keywords)

                    if has_var_issue:
                        # Heuristic: collect identifiers and see if any are longer than 1 char
                        import keyword
                        identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code_stripped)
                        python_keywords = set(keyword.kwlist)
                        common_builtins = {"print", "range", "len", "int", "str", "float", "list", "dict", "set"}
                        simple_ok_letters = {"i", "j", "k", "n", "m", "x", "y", "z", "a", "b", "c"}

                        user_vars = [
                            name for name in identifiers
                            if name not in python_keywords
                            and name not in common_builtins
                        ]

                        has_long_var = any(len(name) > 1 for name in user_vars if name not in simple_ok_letters)

                        if has_long_var:
                            score = 90  # Penalize only when there are "real" badly named variables
                else:
                    # AI says the solution is not correct: partial credit only
                    score = 50

            is_correct = score >= 75
            feedback = f"AI Evaluation (No unit tests provided):\n{ai_feedback}"
            return is_correct, score, feedback
        except Exception as e:
            return False, 0, f"AI-only evaluation error: {str(e)}"
    
    def _convert_ai_confidence_to_score(self, ai_confidence: int, ai_feedback: str, code: str) -> int:
        """Convert AI confidence and feedback to score based on the specified rubric"""
        try:
            feedback_lower = ai_feedback.lower()
            code_lower = code.lower().strip()

            # Explicit rubric when AI-only grading is used
            perfect_keywords = [
                "fully correct", "works correctly", "meets requirements",
                "solves the problem", "passes all tests", "no issues found",
                "implementation is correct", "logic is correct", "output is correct"
            ]
            variable_issue_keywords = [
                "variable", "typo", "naming", "style", "minor issue",
                "cosmetic", "small issue", "rename", "clean up"
            ]
            logic_issue_keywords = [
                "logic error", "wrong output", "incorrect result", "fails case",
                "wrong logic", "does not handle", "bug", "major flaw", "incorrect logic"
            ]

            if any(word in feedback_lower for word in logic_issue_keywords):
                return 50

            if any(word in feedback_lower for word in perfect_keywords):
                return 100

            if any(word in feedback_lower for word in variable_issue_keywords):
                return 90
            
            # Check for interactive code issues
            has_input = 'input(' in code
            has_print = 'print(' in code
            has_return = 'return' in code
            
            # Check if student didn't try at all
            if (len(code.strip()) < 10 or 
                code.strip() in ['', 'pass', 'return', 'print()'] or
                'didn\'t try' in feedback_lower or
                'no attempt' in feedback_lower or
                'empty' in feedback_lower):
                return 0
            
            # Check if student started but didn't complete
            incomplete_indicators = [
                'incomplete', 'not complete', 'unfinished', 'partial',
                'missing', 'syntax error', 'indentation error',
                'nameerror', 'not defined', 'undefined'
            ]
            
            if any(indicator in feedback_lower for indicator in incomplete_indicators):
                return 25
            
            # Check for interactive code issues
            if has_input and not has_return:
                return 75  # Major flaw: using input() when function expected
            
            if has_print and not has_return:
                return 90  # Minor flaw: using print() instead of return
            
            # Check if logic is there but not executed properly
            logic_but_wrong_indicators = [
                'logic is correct', 'algorithm is right', 'approach is good',
                'concept is correct', 'right idea', 'correct thinking',
                'but', 'however', 'except', 'wrong implementation'
            ]
            
            if any(indicator in feedback_lower for indicator in logic_but_wrong_indicators):
                return 50
            
            # Check for major flaws
            major_flaw_indicators = [
                'data type', 'type error', 'wrong type', 'incorrect type',
                'major flaw', 'significant issue', 'fundamental error',
                'completely wrong', 'totally incorrect'
            ]
            
            if any(indicator in feedback_lower for indicator in major_flaw_indicators):
                return 75
            
            # Check for minor flaws
            minor_flaw_indicators = [
                'minor', 'small', 'typo', 'variable name', 'naming',
                'slight', 'small issue', 'minor issue', 'small error'
            ]
            
            if any(indicator in feedback_lower for indicator in minor_flaw_indicators):
                return 90
            
            # If AI confidence is very high and no major issues mentioned
            if ai_confidence >= 90 and 'correct' in feedback_lower:
                return 100
            
            # Default scoring based on AI confidence
            if ai_confidence >= 80:
                return 100
            elif ai_confidence >= 70:
                return 90
            elif ai_confidence >= 60:
                return 75
            elif ai_confidence >= 40:
                return 50
            elif ai_confidence >= 20:
                return 25
            else:
                return 0
                
        except Exception as e:
            print(f"Error in score conversion: {e}")
            # Fallback to AI confidence
            return max(0, min(100, ai_confidence))
    
    def _evaluate_python_fallback_scoring(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Fallback rule-based scoring when AI is not available"""
        try:
            code_stripped = code.strip()
            
            # 0%: Didn't try
            if (len(code_stripped) < 10 or 
                code_stripped in ['', 'pass', 'return', 'print()', '# TODO', '# Write your code here'] or
                code_stripped.count('\n') < 2):
                return False, 0, "No substantial code provided - student didn't attempt the problem"
            
            # Check for syntax errors by trying to compile
            try:
                compile(code, '<string>', 'exec')
                has_syntax_error = False
            except SyntaxError as e:
                has_syntax_error = True
                syntax_error_msg = str(e)
            
            # 25%: Started but incomplete (syntax errors, undefined variables)
            if has_syntax_error:
                return False, 25, f"Code has syntax errors: {syntax_error_msg}. Student started but didn't complete properly."
            
            # Check for basic structure
            has_function_def = 'def ' in code
            has_return = 'return' in code
            has_loops = any(keyword in code for keyword in ['for ', 'while '])
            has_conditionals = any(keyword in code for keyword in ['if ', 'elif ', 'else:'])
            has_input = 'input(' in code
            has_print = 'print(' in code
            
            # Check for common issues
            has_undefined_vars = any(var in code for var in ['numm', 'numb', 'numbe'])  # Common typos
            has_type_issues = (any(issue in code for issue in ['str(', 'int(', 'float(']) and 
                              'input' in code and 
                              'max(' not in code and
                              'if not' not in code)
            has_string_comparison = '"' in code and any(op in code for op in ['>', '<', '==', '!='])
            
            # Check for interactive code issues first
            if has_input and not has_function_def:
                return False, 75, "AI Evaluation (No unit tests provided): Code uses input() but doesn't define a function as requested - major structural issue."
            
            if has_print and not has_return and has_function_def:
                return True, 90, "AI Evaluation (No unit tests provided): Code defines function correctly but uses print() instead of return statements."
            
            # 100%: All correct, perfect implementation
            if (has_function_def and has_return and not has_undefined_vars and 
                not has_type_issues and not has_string_comparison):
                return True, 100, "Code appears to be correct and complete"
            
            # 90%: Minor flaw (typo, variable naming issue, small syntax error)
            if has_function_def and has_return and (has_undefined_vars or has_type_issues):
                return True, 90, "Code is mostly correct with minor issues (typos or type errors)"
            
            # 75%: Major flaw (wrong data type, significant logic error)
            if has_function_def and has_return and has_string_comparison:
                return False, 75, "Code has major logic issues (string comparison with numbers)"
            
            # Default fallback for other cases
            return False, 50, "Code has some structure but needs improvement"
            
        except Exception as e:
            return False, 0, f"Fallback scoring error: {str(e)}"
    
    def _evaluate_c(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate C code using unit tests"""
        try:
            # Extract test logic from unit_tests (which is a complete program)
            unit_tests_text = problem_data['unit_tests'] or ''
            
            # Create a proper test harness by combining student code with test logic
            with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
                # Check if student code already has a main function
                has_main = 'int main(' in code or 'main(' in code
                
                if has_main:
                    # Student provided complete program, modify it to include test counting
                    # Write includes first
                    f.write("#include <assert.h>\n")
                    f.write("#include <stdio.h>\n")
                    
                    # Extract test logic
                    test_lines = []
                    in_main = False
                    for line in unit_tests_text.splitlines():
                        line = line.strip()
                        if line.startswith('int main()'):
                            in_main = True
                            continue
                        elif in_main and line == '}':
                            break
                        elif in_main and line:
                            test_lines.append(line)
                    
                    # Modify student's code to add test counting
                    lines = code.splitlines()
                    in_student_main = False
                    brace_count = 0
                    
                    for line in lines:
                        if 'int main(' in line or 'main(' in line:
                            in_student_main = True
                            f.write(line + "\n")
                            # Add test counting variables
                            f.write("    int tests_passed = 0;\n")
                            f.write("    int total_tests = 0;\n")
                            f.write("    int test_results[10];\n")
                            f.write("    \n")
                            
                            # Add variable declarations (only if not already declared in student code)
                            student_vars = set()
                            for line in lines:
                                if 'int arr' in line and '[]' in line and '=' in line:
                                    var_name = line.split('[')[0].split()[-1]
                                    student_vars.add(var_name)
                            
                            for test_line in test_lines:
                                if 'int arr' in test_line and '[]' in test_line:
                                    var_name = test_line.split('[')[0].split()[-1]
                                    if var_name not in student_vars:
                                        f.write(f"    {test_line};\n")
                            f.write("    \n")
                        elif in_student_main:
                            # Replace assert statements with test counting
                            if 'assert(' in line:
                                test_condition = line.replace('assert(', '').replace(');', '').strip()
                                f.write(f"    total_tests++;\n")
                                f.write(f"    if ({test_condition}) {{\n")
                                f.write(f"        test_results[total_tests-1] = 1;\n")
                                f.write(f"        tests_passed++;\n")
                                f.write(f"    }} else {{\n")
                                f.write(f"        test_results[total_tests-1] = 0;\n")
                                f.write(f"    }}\n")
                            elif 'return 0;' in line:
                                # Replace return with test result output
                                f.write("    printf(\"%d/%d tests passed\\n\", tests_passed, total_tests);\n")
                                f.write("    return (tests_passed == total_tests) ? 0 : 1;\n")
                            else:
                                f.write(line + "\n")
                            
                            # Track braces to know when main function ends
                            if '{' in line:
                                brace_count += line.count('{')
                            if '}' in line:
                                brace_count -= line.count('}')
                                if brace_count == 0:
                                    in_student_main = False
                        else:
                            f.write(line + "\n")
                else:
                    # Student provided just functions, create complete program
                    f.write("#include <assert.h>\n")
                    f.write("#include <stdio.h>\n")
                    f.write(code)
                    f.write("\n\n")
                    
                    # Extract and write test logic (remove the main function wrapper)
                    test_lines = []
                    in_main = False
                    for line in unit_tests_text.splitlines():
                        line = line.strip()
                        if line.startswith('int main()'):
                            in_main = True
                            continue
                        elif in_main and line == '}':
                            break
                        elif in_main and line:
                            test_lines.append(line)
                    
                    # Write test harness
                    f.write("int main() {\n")
                    f.write("    int tests_passed = 0;\n")
                    f.write("    int total_tests = 0;\n")
                    f.write("    int test_results[10];\n")
                    f.write("    \n")
                    
                    # First, write all variable declarations
                    for test_line in test_lines:
                        if 'int arr' in test_line and '[]' in test_line:
                            f.write(f"    {test_line};\n")
                    
                    f.write("    \n")
                    
                    for i, test_line in enumerate(test_lines):
                        if 'assert(' in test_line:
                            # Convert assert to test counting
                            test_condition = test_line.replace('assert(', '').replace(');', '')
                            f.write(f"    total_tests++;\n")
                            f.write(f"    if ({test_condition}) {{\n")
                            f.write(f"        test_results[{i}] = 1;\n")
                            f.write(f"        tests_passed++;\n")
                            f.write(f"    }} else {{\n")
                            f.write(f"        test_results[{i}] = 0;\n")
                            f.write(f"    }}\n")
                    
                    f.write("    \n")
                    f.write("    printf(\"%d/%d tests passed\\n\", tests_passed, total_tests);\n")
                    f.write("    return (tests_passed == total_tests) ? 0 : 1;\n")
                    f.write("}\n")
                
                c_file = f.name
            
            # Compile and run
            try:
                # Compile
                compile_result = subprocess.run(
                    ['gcc', '-o', c_file.replace('.c', ''), c_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if compile_result.returncode != 0:
                    return False, 0, f"Compilation error: {compile_result.stderr}"
                
                # Run
                run_result = subprocess.run(
                    [c_file.replace('.c', '')],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Parse test results
                output = run_result.stdout.strip()
                if "tests passed" in output:
                    # Extract test count from output like "4/5 tests passed"
                    match = re.search(r'(\d+)/(\d+) tests passed', output)
                    if match:
                        passed = int(match.group(1))
                        total = int(match.group(2))
                        score = self._calculate_score_from_tests(passed, total, problem_data)
                        is_correct = score >= 75
                        feedback = f"Tests passed: {passed}/{total}"
                        return is_correct, score, feedback
                
                # Fallback scoring
                if run_result.returncode == 0:
                    score = problem_data['max_score']
                    feedback = f"All tests passed! Score: {score}/{problem_data['max_score']}"
                    return True, score, feedback
                else:
                    score = self._calculate_partial_score(run_result.stderr, problem_data)
                    feedback = f"Some tests failed. Score: {score}/{problem_data['max_score']}\nErrors: {run_result.stderr}"
                    return score >= 75, score, feedback
                    
            finally:
                # Clean up
                os.unlink(c_file)
                if os.path.exists(c_file.replace('.c', '')):
                    os.unlink(c_file.replace('.c', ''))
                    
        except subprocess.TimeoutExpired:
            return False, 0, "Code execution timed out"
        except Exception as e:
            return False, 0, f"C evaluation error: {str(e)}"
    
    def _evaluate_cpp(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate C++ code using unit tests"""
        try:
            # Extract test logic from unit_tests (which is a complete program)
            unit_tests_text = problem_data['unit_tests'] or ''
            
            # Create a proper test harness by combining student code with test logic
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
                # Check if student code already has a main function
                has_main = 'int main(' in code or 'main(' in code
                
                if has_main:
                    # Student provided complete program, modify it to include test counting
                    # Write includes first
                    f.write("#include <vector>\n")
                    f.write("#include <cassert>\n")
                    f.write("#include <iostream>\n")
                    
                    # Extract test logic
                    test_lines = []
                    in_main = False
                    for line in unit_tests_text.splitlines():
                        line = line.strip()
                        if line.startswith('int main()'):
                            in_main = True
                            continue
                        elif in_main and line == '}':
                            break
                        elif in_main and line:
                            test_lines.append(line)
                    
                    # Modify student's code to add test counting
                    lines = code.splitlines()
                    in_student_main = False
                    brace_count = 0
                    
                    for line in lines:
                        if 'int main(' in line or 'main(' in line:
                            in_student_main = True
                            f.write(line + "\n")
                            # Add test counting variables
                            f.write("    int tests_passed = 0;\n")
                            f.write("    int total_tests = 0;\n")
                            f.write("    int test_results[10];\n")
                            f.write("    \n")
                            
                            # Add variable declarations (only if not already declared in student code)
                            student_vars = set()
                            for line in lines:
                                if 'std::vector' in line and '=' in line:
                                    var_name = line.split('=')[0].split()[-1]
                                    student_vars.add(var_name)
                            
                            for test_line in test_lines:
                                if 'std::vector' in test_line and '=' in test_line:
                                    var_name = test_line.split('=')[0].split()[-1]
                                    if var_name not in student_vars:
                                        f.write(f"    {test_line};\n")
                            f.write("    \n")
                        elif in_student_main:
                            # Replace assert statements with test counting
                            if 'assert(' in line:
                                test_condition = line.replace('assert(', '').replace(');', '').strip()
                                f.write(f"    total_tests++;\n")
                                f.write(f"    if ({test_condition}) {{\n")
                                f.write(f"        test_results[total_tests-1] = 1;\n")
                                f.write(f"        tests_passed++;\n")
                                f.write(f"    }} else {{\n")
                                f.write(f"        test_results[total_tests-1] = 0;\n")
                                f.write(f"    }}\n")
                            elif 'return 0;' in line:
                                # Replace return with test result output
                                f.write("    std::cout << tests_passed << \"/\" << total_tests << \" tests passed\" << std::endl;\n")
                                f.write("    return (tests_passed == total_tests) ? 0 : 1;\n")
                            else:
                                f.write(line + "\n")
                            
                            # Track braces to know when main function ends
                            if '{' in line:
                                brace_count += line.count('{')
                            if '}' in line:
                                brace_count -= line.count('}')
                                if brace_count == 0:
                                    in_student_main = False
                        else:
                            f.write(line + "\n")
                else:
                    # Student provided just functions, create complete program
                    f.write("#include <vector>\n")
                    f.write("#include <cassert>\n")
                    f.write("#include <iostream>\n")
                    f.write(code)
                    f.write("\n\n")
                    
                    # Extract and write test logic (remove the main function wrapper)
                    test_lines = []
                    in_main = False
                    for line in unit_tests_text.splitlines():
                        line = line.strip()
                        if line.startswith('int main()'):
                            in_main = True
                            continue
                        elif in_main and line == '}':
                            break
                        elif in_main and line:
                            test_lines.append(line)
                    
                    # Write test harness
                    f.write("int main() {\n")
                    f.write("    int tests_passed = 0;\n")
                    f.write("    int total_tests = 0;\n")
                    f.write("    int test_results[10];\n")
                    f.write("    \n")
                    
                    # First, write all variable declarations
                    for test_line in test_lines:
                        if 'std::vector' in test_line and '=' in test_line:
                            f.write(f"    {test_line};\n")
                    
                    f.write("    \n")
                    
                    for i, test_line in enumerate(test_lines):
                        if 'assert(' in test_line:
                            # Convert assert to test counting
                            test_condition = test_line.replace('assert(', '').replace(');', '')
                            f.write(f"    total_tests++;\n")
                            f.write(f"    if ({test_condition}) {{\n")
                            f.write(f"        test_results[{i}] = 1;\n")
                            f.write(f"        tests_passed++;\n")
                            f.write(f"    }} else {{\n")
                            f.write(f"        test_results[{i}] = 0;\n")
                            f.write(f"    }}\n")
                    
                    f.write("    \n")
                    f.write("    std::cout << tests_passed << \"/\" << total_tests << \" tests passed\" << std::endl;\n")
                    f.write("    return (tests_passed == total_tests) ? 0 : 1;\n")
                    f.write("}\n")
                
                cpp_file = f.name
            
            # Compile and run
            try:
                # Compile
                compile_result = subprocess.run(
                    ['g++', '-o', cpp_file.replace('.cpp', ''), cpp_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if compile_result.returncode != 0:
                    return False, 0, f"Compilation error: {compile_result.stderr}"
                
                # Run
                run_result = subprocess.run(
                    [cpp_file.replace('.cpp', '')],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Parse test results
                output = run_result.stdout.strip()
                if "tests passed" in output:
                    # Extract test count from output like "4/5 tests passed"
                    match = re.search(r'(\d+)/(\d+) tests passed', output)
                    if match:
                        passed = int(match.group(1))
                        total = int(match.group(2))
                        score = self._calculate_score_from_tests(passed, total, problem_data)
                        is_correct = score >= 75
                        feedback = f"Tests passed: {passed}/{total}"
                        return is_correct, score, feedback
                
                # Fallback scoring
                if run_result.returncode == 0:
                    score = problem_data['max_score']
                    feedback = f"All tests passed! Score: {score}/{problem_data['max_score']}"
                    return True, score, feedback
                else:
                    score = self._calculate_partial_score(run_result.stderr, problem_data)
                    feedback = f"Some tests failed. Score: {score}/{problem_data['max_score']}\nErrors: {run_result.stderr}"
                    return score >= 75, score, feedback
                    
            finally:
                # Clean up
                os.unlink(cpp_file)
                if os.path.exists(cpp_file.replace('.cpp', '')):
                    os.unlink(cpp_file.replace('.cpp', ''))
                    
        except subprocess.TimeoutExpired:
            return False, 0, "Code execution timed out"
        except Exception as e:
            return False, 0, f"C++ evaluation error: {str(e)}"
    
    def _evaluate_java(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate Java code using unit tests"""
        try:
            javac_cmd = self._resolve_java_tool('javac')
            if not javac_cmd:
                return False, 0, (
                    "Java compiler (javac) not found. Install a JDK or set JAVA_HOME so the evaluator can compile tests."
                )
            
            java_cmd = self._resolve_java_tool('java')
            if not java_cmd:
                return False, 0, (
                    "Java runtime (java) not found. Install a JDK/JRE or set JAVA_HOME so the evaluator can run tests."
                )
            
            # Extract test logic from unit_tests (which is a complete program)
            unit_tests_text = problem_data['unit_tests'] or ''
            
            # Create a proper test harness by combining student code with test logic
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                java_file = f.name
                class_name = os.path.basename(java_file).replace('.java', '')
                
                # For Java, always create a single class with the student's method and test harness
                # Extract method name from student code
                method_name = "sumArray"  # Default
                method_pattern = re.compile(r'(?:public\s+)?static\s+[^\s]+\s+(\w+)\s*\(', re.IGNORECASE)
                if code.strip().startswith('public class'):
                    # Extract method name from complete class
                    for line in code.splitlines():
                        match = method_pattern.search(line)
                        if match:
                            candidate = match.group(1)
                            if candidate.lower() != 'main':
                                method_name = candidate
                                break
                else:
                    # Extract method name from method definition
                    for line in code.splitlines():
                        match = method_pattern.search(line)
                        if match:
                            candidate = match.group(1)
                            if candidate.lower() != 'main':
                                method_name = candidate
                                break
                
                # Write complete Java class with student code and test harness
                f.write(f"public class {class_name} {{\n")
                
                # Write student code as a static method
                if code.strip().startswith('public class'):
                    # Extract just the method from the complete class
                    in_method = False
                    brace_count = 0
                    method_found = False
                    for line in code.splitlines():
                        raw_line = line.rstrip()
                        stripped = raw_line.strip()
                        match = method_pattern.search(stripped)
                        if match and match.group(1).lower() != 'main':
                            in_method = True
                            method_found = True
                            f.write("    " + raw_line.strip() + "\n")
                            brace_count += raw_line.count('{') - raw_line.count('}')
                            continue
                        if in_method:
                            f.write("    " + raw_line.strip() + "\n")
                            brace_count += raw_line.count('{') - raw_line.count('}')
                            if brace_count <= 0:
                                in_method = False
                                break
                    
                    # If no method was found, write the entire class content (excluding class declaration)
                    if not method_found:
                        for line in code.splitlines():
                            line = line.strip()
                            if not line.startswith('public class') and line:
                                f.write("    " + line + "\n")
                else:
                    # Student provided just a method
                    if not code.strip().startswith('public static'):
                        f.write("    public static ")
                    f.write(code.strip())
                    if not code.strip().endswith('}'):
                        f.write("\n")
                
                f.write("\n")
                
                # Extract and normalize test logic.
                test_lines = []
                in_main = False
                brace_depth = 0
                for raw_line in unit_tests_text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith('public static void main'):
                        in_main = True
                        brace_depth = line.count('{') - line.count('}')
                        continue
                    if in_main:
                        if line == '}':
                            if brace_depth <= 0:
                                in_main = False
                                continue
                        test_lines.append(line)
                        brace_depth += line.count('{') - line.count('}')
                        if brace_depth <= 0:
                            in_main = False
                
                setup_lines: List[str] = []
                assert_conditions: List[str] = []
                expected_func_name: str = None

                def _normalize_condition(condition: str) -> str:
                    nonlocal expected_func_name
                    cond = condition.strip()
                    if cond.startswith('assert'):
                        cond = cond[len('assert'):].strip()
                    cond = cond.rstrip(';')
                    if expected_func_name is None:
                        match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', cond)
                        if match:
                            candidate = match.group(1)
                            if candidate.lower() not in {'math', 'system', 'arrays'}:
                                expected_func_name = candidate
                    if expected_func_name and expected_func_name != method_name:
                        cond = re.sub(rf'\b{re.escape(expected_func_name)}\b', method_name, cond)
                    return cond

                def _collect_from_lines(lines: List[str]) -> None:
                    for item in lines:
                        stripped = item.strip()
                        if not stripped or stripped in {'{', '}'}:
                            continue
                        if stripped.startswith('assert'):
                            assert_conditions.append(_normalize_condition(stripped))
                        else:
                            if not stripped.endswith(';') and not stripped.endswith('}'):
                                stripped = stripped + ';'
                            setup_lines.append(stripped)

                _collect_from_lines(test_lines)

                if not assert_conditions:
                    fallback_lines = [ln.strip() for ln in unit_tests_text.splitlines()]
                    _collect_from_lines(fallback_lines)

                if not assert_conditions:
                    return False, 0, "No assert statements found in Java unit tests."
                
                # Write test harness
                f.write("    public static void main(String[] args) {\n")
                f.write("        int tests_passed = 0;\n")
                f.write("        int total_tests = 0;\n")
                f.write(f"        boolean[] test_results = new boolean[{max(1, len(assert_conditions))}];\n")
                f.write("        \n")
                
                for line in setup_lines:
                    f.write(f"        {line}\n")
                if setup_lines:
                    f.write("        \n")
                
                for idx, condition in enumerate(assert_conditions):
                    f.write("        total_tests++;\n")
                    f.write("        try {\n")
                    f.write(f"            if ({condition}) {{\n")
                    f.write(f"                test_results[{idx}] = true;\n")
                    f.write("                tests_passed++;\n")
                    f.write("            } else {\n")
                    f.write(f"                test_results[{idx}] = false;\n")
                    f.write("            }\n")
                    f.write("        } catch (Exception e) {\n")
                    f.write(f"            test_results[{idx}] = false;\n")
                    f.write("        }\n")
                
                f.write("        \n")
                f.write("        System.out.println(tests_passed + \"/\" + total_tests + \" tests passed\");\n")
                f.write("        System.exit((tests_passed == total_tests) ? 0 : 1);\n")
                f.write("    }\n")
                f.write("}\n")
                
                java_file = f.name
            
            # Compile and run
            try:
                # Compile
                compile_cmd = [javac_cmd, java_file]
                compile_result = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                used_preview = False
                preview_hint = (compile_result.stderr or "").lower()
                
                if compile_result.returncode != 0 and ("preview feature" in preview_hint or "uses preview features" in preview_hint):
                    # Retry compilation with preview features enabled for the detected Java release
                    java_release = self._get_java_release(java_cmd)
                    compile_cmd = [javac_cmd, '--enable-preview', '--release', java_release, java_file]
                    compile_result = subprocess.run(
                        compile_cmd,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    used_preview = True
                
                if compile_result.returncode != 0:
                    return False, 0, f"Compilation error: {compile_result.stderr}"
                
                # Run the single class
                run_cmd = [java_cmd]
                if used_preview:
                    run_cmd.append('--enable-preview')
                run_cmd.extend(['-cp', os.path.dirname(java_file), class_name])
                run_result = subprocess.run(
                    run_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Parse test results
                output = run_result.stdout.strip()
                if "tests passed" in output:
                    # Extract test count from output like "4/5 tests passed"
                    match = re.search(r'(\d+)/(\d+) tests passed', output)
                    if match:
                        passed = int(match.group(1))
                        total = int(match.group(2))
                        score = self._calculate_score_from_tests(passed, total, problem_data)
                        is_correct = score >= 75
                        feedback = f"Tests passed: {passed}/{total}"
                        return is_correct, score, feedback
                
                # Fallback scoring
                if run_result.returncode == 0:
                    score = problem_data['max_score']
                    feedback = f"All tests passed! Score: {score}/{problem_data['max_score']}"
                    return True, score, feedback
                else:
                    score = self._calculate_partial_score(run_result.stderr, problem_data)
                    feedback = f"Some tests failed. Score: {score}/{problem_data['max_score']}\nErrors: {run_result.stderr}"
                    return score >= 75, score, feedback
                    
            finally:
                # Clean up
                os.unlink(java_file)
                class_files = [f for f in os.listdir(os.path.dirname(java_file)) if f.endswith('.class')]
                for cf in class_files:
                    os.unlink(os.path.join(os.path.dirname(java_file), cf))
                    
        except subprocess.TimeoutExpired:
            return False, 0, "Code execution timed out"
        except Exception as e:
            return False, 0, f"Java evaluation error: {str(e)}"
    
    def _evaluate_javascript(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate JavaScript code using unit tests"""
        try:
            mismatch = self._detect_language_mismatch(code, 'javascript')
            if mismatch:
                return False, 0, mismatch
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(code + "\n\n")
                f.write(problem_data['unit_tests'])
                js_file = f.name
            
            # Run with Node.js
            try:
                result = subprocess.run(
                    ['node', js_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    score = problem_data['max_score']
                    feedback = f"All tests passed! Score: {score}/{problem_data['max_score']}"
                    return True, score, feedback
                else:
                    score = self._calculate_partial_score(result.stderr, problem_data)
                    feedback = f"Some tests failed. Score: {score}/{problem_data['max_score']}\nErrors: {result.stderr}"
                    return score >= 75, score, feedback
                    
            finally:
                # Clean up
                os.unlink(js_file)
                
        except subprocess.TimeoutExpired:
            return False, 0, "Code execution timed out"
        except Exception as e:
            return False, 0, f"JavaScript evaluation error: {str(e)}"
    
    def _evaluate_csharp(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate C# code by generating a temporary dotnet project and running unit tests."""
        compiler_cmd = self._get_csharp_compiler()
        if not compiler_cmd:
            return False, 0, (
                "C# compiler (csc) not found. Install .NET SDK or set CSC_DLL_PATH / DOTNET_CSC_DLL "
                "to a valid csc.dll."
            )

        dotnet_cmd = compiler_cmd[0] if 'dotnet' in os.path.basename(compiler_cmd[0]).lower() else shutil.which('dotnet')
        if not dotnet_cmd:
            return False, 0, "dotnet CLI not found. Install the .NET SDK to execute C# code."

        unit_tests_text = problem_data.get('unit_tests') or ''
        assert_conditions: List[str] = []
        expected_func_name: Optional[str] = None
        
        for raw_line in unit_tests_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('//'):
                continue
            if line.startswith('assert '):
                condition = line[len('assert '):].rstrip(';')
                assert_conditions.append(condition)
            elif line.startswith('assert(') and line.endswith(')'):
                condition = line[len('assert('):-1].rstrip(';')
                assert_conditions.append(condition)
            elif 'assert ' in line:
                condition = line[line.find('assert ') + len('assert '):].rstrip(';')
                assert_conditions.append(condition)
            elif 'assert(' in line:
                start = line.find('assert(') + len('assert(')
                end = line.rfind(')')
                if end > start:
                    condition = line[start:end].rstrip(';')
                    assert_conditions.append(condition)

            if expected_func_name is None and assert_conditions:
                match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', assert_conditions[-1])
                if match:
                    candidate = match.group(1)
                    if candidate.lower() not in {'math', 'console', 'system'}:
                        expected_func_name = candidate
        
        if not assert_conditions:
            return False, 0, "No assert statements found in C# unit tests."
        
        class_match = re.search(r'class\s+([A-Za-z_][A-Za-z0-9_]*)', code)
        student_class_name = class_match.group(1) if class_match else None

        namespace_match = re.search(r'namespace\s+([A-Za-z_][A-Za-z0-9_\.]*)', code)
        student_namespace = namespace_match.group(1) if namespace_match else None
        qualified_class_name = (
            f"{student_namespace}.{student_class_name}"
            if student_namespace and student_class_name
            else student_class_name
        )

        method_pattern = re.compile(
            r'(?:public|private|protected|internal)?\s*(static\s+)?[^\s]+\s+(\w+)\s*\(',
            re.IGNORECASE
        )
        student_methods: List[Tuple[str, bool]] = []
        for match in method_pattern.finditer(code):
            method_name = match.group(2)
            if not method_name or method_name.lower() == 'main':
                continue
            is_static = bool(match.group(1))
            student_methods.append((method_name, is_static))

        selected_method = student_methods[0] if student_methods else None
        replacement_target = expected_func_name
        replacement_value = selected_method[0] if selected_method else None
        method_is_static = selected_method[1] if selected_method else False

        needs_instance = False
        call_prefix = ""
        if replacement_target and replacement_value:
            if qualified_class_name:
                if method_is_static:
                    call_prefix = f"{qualified_class_name}."
                else:
                    call_prefix = "__studentInstance."
                    needs_instance = True

        normalized_asserts: List[str] = []
        for condition in assert_conditions:
            normalized = condition
            if replacement_target and replacement_value:
                pattern = rf'\b{re.escape(replacement_target)}\s*\('
                replacement_call = f"{call_prefix}{replacement_value}("
                normalized = re.sub(pattern, replacement_call, normalized, flags=re.IGNORECASE)
            normalized_asserts.append(normalized)

        temp_dir = tempfile.mkdtemp(prefix='csharp_eval_')
        student_code_path = os.path.join(temp_dir, 'StudentCode.cs')
        runner_code_path = os.path.join(temp_dir, 'TestRunner.cs')
        project_path = os.path.join(temp_dir, 'TestRunner.csproj')

        target_framework = self._select_dotnet_target_framework(dotnet_cmd)

        try:
            with open(project_path, 'w', encoding='utf-8') as proj_file:
                proj_file.write(
                    "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
                    "  <PropertyGroup>\n"
                    f"    <TargetFramework>{target_framework}</TargetFramework>\n"
                    "    <OutputType>Exe</OutputType>\n"
                    "    <ImplicitUsings>disable</ImplicitUsings>\n"
                    "    <Nullable>disable</Nullable>\n"
                    "    <LangVersion>latest</LangVersion>\n"
                    "    <StartupObject>__TestRunner__</StartupObject>\n"
                    "  </PropertyGroup>\n"
                    "</Project>\n"
                )

            with open(student_code_path, 'w', encoding='utf-8') as student_file:
                student_file.write("using System;\nusing System.Collections.Generic;\nusing System.Linq;\n\n")
                student_file.write(code.strip())
                student_file.write("\n")

            with open(runner_code_path, 'w', encoding='utf-8') as runner_file:
                runner_file.write("using System;\nusing System.Collections.Generic;\n\n")
                runner_file.write("public static class __TestRunner__ {\n")
                runner_file.write("    public static void Main(string[] args) {\n")
                runner_file.write("        int testsPassed = 0;\n")
                runner_file.write("        int totalTests = 0;\n")
                runner_file.write("        var errors = new List<string>();\n")
                if needs_instance and qualified_class_name:
                    runner_file.write(f"        var __studentInstance = new {qualified_class_name}();\n")
                runner_file.write("\n")
                for condition in normalized_asserts:
                    escaped = condition.replace('\\', '\\\\').replace('"', '\\"')
                    runner_file.write("        totalTests++;\n")
                    runner_file.write("        try {\n")
                    runner_file.write(f"            if ({condition}) {{\n")
                    runner_file.write("                testsPassed++;\n")
                    runner_file.write("            } else {\n")
                    runner_file.write(f"                errors.Add(\"Assertion failed: {escaped}\");\n")
                    runner_file.write("            }\n")
                    runner_file.write("        } catch (Exception ex) {\n")
                    runner_file.write(f"            errors.Add(\"{escaped} -> \" + ex.Message);\n")
                    runner_file.write("        }\n\n")
                runner_file.write("        Console.WriteLine($\"{testsPassed}/{totalTests} tests passed\");\n")
                runner_file.write("        if (errors.Count > 0) {\n")
                runner_file.write("            foreach (var err in errors) {\n")
                runner_file.write("                Console.WriteLine(\"ERROR: \" + err);\n")
                runner_file.write("            }\n")
                runner_file.write("        }\n")
                runner_file.write("        Environment.Exit(testsPassed == totalTests ? 0 : 1);\n")
                runner_file.write("    }\n")
                runner_file.write("}\n")

            env = os.environ.copy()
            env.setdefault('DOTNET_CLI_TELEMETRY_OPTOUT', '1')
            env.setdefault('DOTNET_NOLOGO', '1')
            env.setdefault('DOTNET_SKIP_FIRST_TIME_EXPERIENCE', '1')

            run_cmd = [dotnet_cmd, 'run', '--project', project_path, '--configuration', 'Release']
            run_result = subprocess.run(
                run_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )

            stdout = (run_result.stdout or '').strip()
            stderr = (run_result.stderr or '').strip()
            combined_output = "\n".join(line for line in [stdout, stderr] if line)

            match = re.search(r'(\d+)/(\d+)\s+tests\s+passed', combined_output)
            if match:
                passed = int(match.group(1))
                total = int(match.group(2))
                score = self._calculate_score_from_tests(passed, total, problem_data)
                is_correct = score >= 75
                feedback_lines = [f"Tests passed: {passed}/{total}"]
                error_lines = [line for line in combined_output.splitlines() if line.startswith("ERROR:")]
                if error_lines:
                    feedback_lines.append("Errors:")
                    feedback_lines.extend(error_lines[:5])
                extra_logs = [
                    line for line in combined_output.splitlines()
                    if line and not line.startswith("ERROR:") and "tests passed" not in line
                ]
                if extra_logs:
                    feedback_lines.append("\n".join(extra_logs[-5:]))
                feedback = "\n".join(feedback_lines)
                return is_correct, score, feedback

            details = combined_output or "Unknown C# execution error"
            if run_result.returncode != 0:
                return False, 0, f"C# compilation/execution error:\n{details}"

            score = problem_data['max_score']
            return True, score, f"All tests passed! Score: {score}/{problem_data['max_score']}"

        except subprocess.TimeoutExpired:
            return False, 0, "C# code execution timed out"
        except Exception as e:
            return False, 0, f"C# evaluation error: {str(e)}"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _calculate_score_from_tests(self, passed: int, total: int, problem_data: Dict[str, Any]) -> int:
        """Calculate score based on percentage of tests passed with flexible scoring"""
        max_score = int(problem_data['max_score'])
        
        if total == 0:
            return 0
        
        if passed == total:
            # Perfect score for all tests passed
            return max_score
        
        # Calculate percentage of tests passed
        percentage = passed / total
        
        # Use the same flexible scoring scale as in _evaluate_python
        if percentage >= 0.8:  # 80% or more
            return int(round(0.9 * max_score))  # 90% of max score
        elif percentage >= 0.6:  # 60-79%
            return int(round(0.75 * max_score))  # 75% of max score
        elif percentage >= 0.4:  # 40-59%
            return int(round(0.5 * max_score))   # 50% of max score
        elif percentage >= 0.2:  # 20-39%
            return int(round(0.25 * max_score))  # 25% of max score
        else:  # Less than 20%
            return 0
    def _calculate_partial_score(self, error_output: str, problem_data: Dict[str, Any]) -> int:
        """Calculate partial score based on test failures and error analysis"""
        try:
            # Parse scoring criteria
            criteria = problem_data['scoring_criteria']
            max_score = problem_data['max_score']
            
            # Simple scoring based on error analysis
            if "assertion" in error_output.lower() or "assert" in error_output.lower():
                # Some assertions failed, give partial credit
                return max(25, max_score // 2)
            elif "syntax" in error_output.lower() or "compilation" in error_output.lower():
                # Syntax errors, minimal credit
                return 10
            else:
                # Runtime errors, some credit
                return max(25, max_score // 3)
                
        except Exception:
            return 0

    def _select_dotnet_target_framework(self, dotnet_cmd: str) -> str:
        """Choose the highest available netX.Y target framework for temporary C# projects."""
        try:
            dotnet_root = os.path.dirname(os.path.abspath(dotnet_cmd))
            ref_pack_root = os.path.join(dotnet_root, 'packs', 'Microsoft.NETCore.App.Ref')
            if not os.path.isdir(ref_pack_root):
                return 'net8.0'
            versions = sorted(os.listdir(ref_pack_root), reverse=True)
            for version in versions:
                match = re.match(r'(\d+)\.(\d+)', version)
                if not match:
                    continue
                major, minor = match.group(1), match.group(2)
                return f"net{major}.{minor}"
        except Exception:
            pass
        return 'net8.0'

    def _ai_available(self) -> bool:
        """Re-check whether LM Studio is reachable each time we evaluate."""
        global AI_AVAILABLE
        try:
            available = ai_evaluator._check_lm_studio_available()
            if available and not AI_AVAILABLE:
                print("AI evaluator connection restored - using AI-assisted scoring")
            AI_AVAILABLE = available
            return available
        except Exception:
            AI_AVAILABLE = False
            return False

    def _get_csharp_compiler(self) -> Optional[List[str]]:
        """Locate csc or a dotnet-hosted csc.dll"""
        csc_path = shutil.which('csc')
        if csc_path:
            return [csc_path]
        
        dotnet_path = shutil.which('dotnet')
        if not dotnet_path:
            return None
        
        dll_hint = os.environ.get('CSC_DLL_PATH') or os.environ.get('DOTNET_CSC_DLL')
        if dll_hint and os.path.exists(dll_hint):
            return [dotnet_path, dll_hint]
        
        dll_path = self._find_csc_dll()
        if dll_path:
            return [dotnet_path, dll_path]
        
        return None

    def _find_csc_dll(self) -> Optional[str]:
        """Search common .NET SDK locations for csc.dll"""
        candidates = []
        search_dirs = []
        dotnet_root = os.environ.get('DOTNET_ROOT')
        if dotnet_root:
            search_dirs.append(dotnet_root)
        program_files = os.environ.get('PROGRAMFILES')
        if program_files:
            search_dirs.append(os.path.join(program_files, 'dotnet'))
        program_files_x86 = os.environ.get('PROGRAMFILES(X86)')
        if program_files_x86:
            search_dirs.append(os.path.join(program_files_x86, 'dotnet'))
        search_dirs.append(r"C:\Program Files\dotnet")
        
        seen = set()
        for base in search_dirs:
            if not base or base in seen or not os.path.exists(base):
                continue
            seen.add(base)
            pattern = os.path.join(base, 'sdk', '*', 'Roslyn', 'bincore', 'csc.dll')
            candidates.extend(glob.glob(pattern))
        
        if not candidates:
            return None
        
        candidates.sort(reverse=True)
        return candidates[0]

    def _get_java_release(self, java_cmd: Optional[str] = None) -> str:
        """Best-effort detection of the installed Java release for preview compilation"""
        try:
            java_executable = java_cmd or self._resolve_java_tool('java') or 'java'
            result = subprocess.run(
                [java_executable, '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_output = (result.stderr or result.stdout or "").splitlines()
            if not version_output:
                return '21'
            first_line = version_output[0]
            # Extract major version number
            match = re.search(r'version\s+"(\d+)', first_line)
            if match:
                return match.group(1)
        except Exception:
            pass
        return '21'

    def _detect_language_mismatch(self, code: str, expected_language: str) -> Optional[str]:
        """Heuristically detect if the submission is written in another language."""
        normalized = (expected_language or '').lower().strip()
        snippet = (code or '').strip()
        if not snippet or not normalized:
            return None
        
        code_lower = snippet.lower()
        c_like_markers = [
            '#include', 'using namespace', 'public static void main',
            'system.out.println', 'printf(', 'std::', 'cin >>', 'cout <<',
            'template<', 'class ', 'struct ', 'enum '
        ]
        c_func_pattern = re.compile(r'^\s*(?:int|long|float|double|char|void)\s+[A-Za-z_]\w*\s*\(', re.MULTILINE)
        
        def found_markers(markers):
            return [m for m in markers if m in code_lower]
        
        if normalized == 'python':
            if found_markers(c_like_markers) or c_func_pattern.search(snippet):
                return (
                    "Submission looks like C/C++/Java code (e.g., uses types like 'int' or '#include') "
                    "but the Python evaluator was selected. Please submit Python code or switch the language before running tests."
                )
        elif normalized == 'javascript':
            js_blockers = c_like_markers + ['#define']
            if found_markers(js_blockers) or c_func_pattern.search(snippet):
                return (
                    "Submission appears to be C/C++/Java code, not JavaScript. "
                    "Choose the matching language or rewrite the solution in JavaScript before testing."
                )
        return None
    
    def _resolve_java_tool(self, tool_name: str) -> Optional[str]:
        """Return the absolute path to a Java tool (javac/java) if available."""
        if not tool_name:
            return None
        
        direct = shutil.which(tool_name)
        if direct:
            return direct
        
        env_homes = [os.environ.get('JAVA_HOME'), os.environ.get('JDK_HOME')]
        search_roots = [home for home in env_homes if home]
        if os.name == 'nt':
            search_roots.extend([
                r"C:\Program Files\Java",
                r"C:\Program Files (x86)\Java"
            ])
        exts = ['.exe', '.bat', '.cmd', ''] if os.name == 'nt' else ['']
        
        for root in search_roots:
            if not root:
                continue
            candidate_dirs = []
            if os.path.isdir(root):
                candidate_dirs.append(root)
                try:
                    subdirs = sorted(
                        (os.path.join(root, sub) for sub in os.listdir(root)),
                        reverse=True
                    )
                    candidate_dirs.extend([d for d in subdirs if os.path.isdir(d)])
                except Exception:
                    pass
            else:
                candidate_dirs.append(os.path.dirname(root))
            
            for base in candidate_dirs:
                bin_dir = os.path.join(base, 'bin')
                probe_dirs = [bin_dir] if os.path.isdir(bin_dir) else []
                probe_dirs.append(base)
                for probe in probe_dirs:
                    for ext in exts:
                        candidate_path = os.path.join(probe, tool_name + ext)
                        if os.path.exists(candidate_path):
                            return candidate_path
        return None
    

# Global evaluator instance
code_evaluator = CodeEvaluator()