"""
Custom Code Evaluation System
Replaces LM Studio AI with automated unit testing and scoring
"""

import os
import sys
import tempfile
import subprocess
import re
from typing import Tuple, List, Dict, Any
import pandas as pd


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
        Evaluate student code using unit tests and expected outputs
        
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
            
            # Get evaluation function for the language
            eval_func = self.supported_languages[lang_key]
            
            # Run evaluation
            return eval_func(code, problem_data)
            
        except Exception as e:
            return False, 0, f"Evaluation error: {str(e)}"
    
    def evaluate_code_with_custom_tests(self, code: str, unit_tests: str, language: str) -> Tuple[bool, int, str]:
        """Evaluate code using custom unit tests provided directly"""
        try:
            # Create a mock problem data structure
            problem_data = {
                'problem_id': 'custom',
                'topic': 'Custom',
                'language': language,
                'problem_statement': 'Custom problem',
                'unit_tests': unit_tests,
                'expected_outputs': '',
                'scoring_criteria': 'Auto-graded by custom unit tests',
                'max_score': 100
            }
            
            # Detect language and get appropriate evaluator
            lang_key = language.lower()
            if lang_key not in self.supported_languages:
                return False, 0, f"Unsupported language: {language}"
            
            # Get evaluation function for the language
            eval_func = self.supported_languages[lang_key]
            
            # Run evaluation with custom unit tests
            return eval_func(code, problem_data)
            
        except Exception as e:
            return False, 0, f"Custom evaluation error: {str(e)}"
    
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
            # Extract assert lines from unit tests
            unit_tests_text = problem_data['unit_tests'] or ''
            assert_lines: List[str] = []
            for raw_line in unit_tests_text.splitlines():
                line = raw_line.strip()
                if line.startswith('assert '):
                    assert_lines.append(line)
            total_asserts = len(assert_lines)
            if total_asserts == 0:
                # Fallback: execute provided unit_tests block directly
                assert_lines = []
                total_asserts = 0
            
            # Determine expected function name from first assert
            expected_func_name = None
            if assert_lines:
                m = re.match(r"assert\s+(\w+)\(", assert_lines[0])
                if m:
                    expected_func_name = m.group(1)
            
            # Determine student's defined function names
            student_func_names = re.findall(r"^def\s+(\w+)\(", code, flags=re.M)
            alias_used = False
            alias_line = ''
            # Only create alias if the expected function name is not found but student has exactly one function
            if expected_func_name and expected_func_name not in student_func_names and len(student_func_names) == 1:
                # Create an alias so tests can run: expected_name = student's only function
                alias_line = f"\n{expected_func_name} = {student_func_names[0]}\n"
                alias_used = True
            
            # Build a deterministic test harness for counting passes
            with tempfile.NamedTemporaryFile(mode='w', suffix='_py_eval.py', delete=False) as f:
                # Write student's code
                f.write(code)
                if alias_line:
                    f.write(alias_line)
                f.write("\n\n")
                # Write runner
                f.write("def __run_asserts__():\n")
                f.write("    total = 0\n")
                f.write("    passed = 0\n")
                f.write("    errors = []\n")
                for a in assert_lines:
                    safe = a.replace('\\', '\\\\').replace('"', '\\"')
                    f.write("    total += 1\n")
                    f.write("    try:\n")
                    f.write(f"        {a}\n")
                    f.write("        passed += 1\n")
                    f.write("    except Exception as e:\n")
                    f.write(f"        errors.append(\"{safe} -> { '{'}type(e).__name__{'}'}: { '{'}str(e){'}'}\")\n")
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
                
                # Apply specific scoring based on test results
                if total == 0:
                    score = 0
                elif passed == total:
                    # Perfect score for all tests passed
                    score = max_score
                elif passed == total - 1 and total >= 5:
                    # 4/5 or similar - minor issues like variable mistakes
                    score = int(round(0.9 * max_score))
                elif passed == total - 2 and total >= 5:
                    # 3/5 or similar - data type issues and major flaws
                    score = int(round(0.7 * max_score))
                elif passed == total - 3 and total >= 5:
                    # 2/5 or similar - almost great but lots of errors
                    score = int(round(0.5 * max_score))
                elif passed == total - 4 and total >= 5:
                    # 1/5 or similar - trying something
                    score = int(round(0.25 * max_score))
                else:
                    # 0/5 or other cases
                    score = 0
                
                # If only name aliasing was needed and all tests passed, apply 90% rule
                # This handles cases where student used wrong function name but correct implementation
                if alias_used and total > 0 and passed == total:
                    # Apply 90% deduction only when function name was wrong but logic is correct
                    score = int(round(0.9 * max_score))
                
                is_correct = score >= 75
                # Build feedback
                fb_lines = [
                    f"Tests passed: {passed}/{total}",
                ]
                if alias_used:
                    fb_lines.append("Note: Function name alias applied (deducted to 90%).")
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
        """Calculate score based on percentage of tests passed"""
        max_score = int(problem_data['max_score'])
        
        if total == 0:
            return 0
        
        # Calculate percentage of tests passed
        percentage = passed / total
        
        # Return score based on percentage
        return int(round(percentage * max_score))

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