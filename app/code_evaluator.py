"""
Custom Code Evaluation System
Replaces LM Studio AI with automated unit testing and scoring
Now integrates AI evaluation as initial checker
"""

import os
import sys
import tempfile
import subprocess
import re
from typing import Tuple, List, Dict, Any
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
            
            # Step 1: AI Evaluation (if available)
            ai_correct = None
            ai_confidence = 0
            ai_feedback = ""
            
            if AI_AVAILABLE:
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
                ai_correct, ai_confidence, ai_feedback,
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
            
            # Step 1: AI Evaluation (if available)
            ai_correct = None
            ai_confidence = 0
            ai_feedback = ""
            
            if AI_AVAILABLE:
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
                ai_correct, ai_confidence, ai_feedback,
                unit_correct, unit_score, unit_feedback,
                problem_data
            )
            
        except Exception as e:
            return False, 0, f"Custom evaluation error: {str(e)}"
    
    def _combine_evaluation_results(self, ai_correct: bool, ai_confidence: int, ai_feedback: str,
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
            if AI_AVAILABLE and ai_feedback:
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
                'language': row['language'],
                'problem_statement': row['problem_statement'],
                'unit_tests': row['unit_tests'],
                'expected_outputs': '',  # Column removed from CSV
                'scoring_criteria': 'Auto-graded by unit tests',  # Default value
                'max_score': 100  # Default value
            }
            
        except Exception as e:
            print(f"Error loading problem data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _evaluate_python(self, code: str, problem_data: Dict[str, Any]) -> Tuple[bool, int, str]:
        """Evaluate Python code using parsed unit tests with partial scoring and name aliasing"""
        try:
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
        try:
            # Check if code has interactive elements that would cause issues
            has_input = 'input(' in code
            has_print = 'print(' in code
            
            if not AI_AVAILABLE:
                # Fallback to rule-based scoring when AI is not available
                return self._evaluate_python_fallback_scoring(code, problem_data)
            
            # Get AI evaluation
            ai_correct, ai_confidence, ai_feedback = ai_evaluator.evaluate_code(
                code, 
                problem_data['problem_statement'], 
                "python",
                ""  # No unit tests
            )
            
            # Convert AI confidence to score based on the specified rubric
            score = self._convert_ai_confidence_to_score(ai_confidence, ai_feedback, code)
            
            # Determine if code is correct (score >= 75%)
            is_correct = score >= 75
            
            # Build feedback (no penalty for missing unit tests)
            feedback_parts = [f"AI Evaluation:"]
            feedback_parts.append(ai_feedback)
            
            if has_input:
                feedback_parts.append("\nNote: Code contains input() calls which cannot be tested without interactive input.")
            if has_print and not has_input:
                feedback_parts.append("\nNote: Code uses print() instead of return statements - consider returning values for better function design.")

            feedback = "\n".join(feedback_parts)
            
            return is_correct, score, feedback
            
        except Exception as e:
            return False, 0, f"AI-only evaluation error: {str(e)}"
    
    def _convert_ai_confidence_to_score(self, ai_confidence: int, ai_feedback: str, code: str) -> int:
        """Convert AI confidence and feedback to score based on the specified rubric"""
        try:
            feedback_lower = ai_feedback.lower()
            code_lower = code.lower().strip()
            
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
                    import re
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
                    import re
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
            # Extract test logic from unit_tests (which is a complete program)
            unit_tests_text = problem_data['unit_tests'] or ''
            
            # Create a proper test harness by combining student code with test logic
            with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
                java_file = f.name
                class_name = os.path.basename(java_file).replace('.java', '')
                
                # For Java, always create a single class with the student's method and test harness
                # Extract method name from student code
                method_name = "sumArray"  # Default
                if code.strip().startswith('public class'):
                    # Extract method name from complete class
                    for line in code.splitlines():
                        if 'public static int' in line and '(' in line:
                            method_name = line.split('(')[0].split()[-1]
                            break
                else:
                    # Extract method name from method definition
                    for line in code.splitlines():
                        if 'int ' in line and '(' in line and ')' in line:
                            method_name = line.split('(')[0].split()[-1]
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
                        line = line.strip()
                        if 'public static int' in line and '(' in line:
                            in_method = True
                            method_found = True
                            f.write("    " + line + "\n")
                            # Count the opening brace in the method declaration
                            if '{' in line:
                                brace_count += line.count('{')
                        elif in_method:
                            f.write("    " + line + "\n")
                            if '{' in line:
                                brace_count += line.count('{')
                            if '}' in line:
                                brace_count -= line.count('}')
                            if brace_count == 0:
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
                
                # Extract and write test logic (remove the class wrapper)
                test_lines = []
                in_main = False
                for line in unit_tests_text.splitlines():
                    line = line.strip()
                    if line.startswith('public static void main(String[] args)'):
                        in_main = True
                        continue
                    elif in_main and line == '}':
                        break
                    elif in_main and line:
                        test_lines.append(line)
                
                # Write test harness
                f.write("    public static void main(String[] args) {\n")
                f.write("        int tests_passed = 0;\n")
                f.write("        int total_tests = 0;\n")
                f.write("        boolean[] test_results = new boolean[10];\n")
                f.write("        \n")
                
                # First, write all variable declarations
                for test_line in test_lines:
                    if 'int[]' in test_line and '=' in test_line:
                        f.write(f"        {test_line};\n")
                
                f.write("        \n")
                
                for i, test_line in enumerate(test_lines):
                    if 'assert ' in test_line:
                        # Convert assert to test counting and fix method name
                        test_condition = test_line.replace('assert ', '').replace(';', '')
                        if 'sumArray' in test_condition:
                            test_condition = test_condition.replace('sumArray', method_name)
                        f.write(f"        total_tests++;\n")
                        f.write(f"        if ({test_condition}) {{\n")
                        f.write(f"            test_results[{i}] = true;\n")
                        f.write(f"            tests_passed++;\n")
                        f.write(f"        }} else {{\n")
                        f.write(f"            test_results[{i}] = false;\n")
                        f.write(f"        }}\n")
                
                f.write("        \n")
                f.write("        System.out.println(tests_passed + \"/\" + total_tests + \" tests passed\");\n")
                f.write("        System.exit((tests_passed == total_tests) ? 0 : 1);\n")
                f.write("    }\n")
                f.write("}\n")
                
                java_file = f.name
            
            # Compile and run
            try:
                # Compile
                compile_result = subprocess.run(
                    ['javac', java_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if compile_result.returncode != 0:
                    return False, 0, f"Compilation error: {compile_result.stderr}"
                
                # Run the single class
                run_result = subprocess.run(
                    ['java', '-cp', os.path.dirname(java_file), class_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                # Parse test results
                output = run_result.stdout.strip()
                if "tests passed" in output:
                    # Extract test count from output like "4/5 tests passed"
                    import re
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


# Global evaluator instance
code_evaluator = CodeEvaluator()