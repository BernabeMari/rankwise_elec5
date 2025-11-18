"""
AI Code Evaluator using LM Studio
Provides initial code analysis and feedback before unit test evaluation
"""

import requests
import json
import re
from typing import Tuple, Dict, Any, Optional


class AIEvaluator:
    """AI-powered code evaluator using LM Studio"""
    
    def __init__(self):
        self.lm_studio_url = "http://localhost:1234/v1/chat/completions"
        self.model_path = r"C:\Users\Zyb\.lmstudio\models\bartowski\DeepSeek-Coder-V2-Lite-Instruct-GGUF\DeepSeek-Coder-V2-Lite-Instruct-Q8_0_L.gguf"
        self.timeout = 30  # 30 seconds timeout for AI evaluation
    
    def evaluate_code(self, code: str, problem_statement: str, language: str, unit_tests: str = "") -> Tuple[bool, int, str]:
        """
        Evaluate student code using AI analysis
        
        Args:
            code: Student's code submission
            problem_statement: The problem description
            language: Programming language
            unit_tests: Unit tests for additional context
            
        Returns:
            Tuple of (is_correct, confidence_score, feedback)
        """
        try:
            # Check if LM Studio is running
            if not self._check_lm_studio_available():
                return False, 0, "AI evaluation unavailable: LM Studio not running"
            
            # Create the prompt for AI evaluation
            prompt = self._create_evaluation_prompt(code, problem_statement, language, unit_tests)
            
            # Send request to LM Studio
            response = self._send_ai_request(prompt)
            
            if not response:
                return False, 0, "AI evaluation failed: No response from LM Studio"
            
            # Parse AI response
            is_correct, confidence, feedback = self._parse_ai_response(response)
            
            return is_correct, confidence, feedback
            
        except Exception as e:
            return False, 0, f"AI evaluation error: {str(e)}"
    
    def _check_lm_studio_available(self) -> bool:
        """Check if LM Studio is running and accessible"""
        try:
            response = requests.get("http://localhost:1234/v1/models", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _create_evaluation_prompt(self, code: str, problem_statement: str, language: str, unit_tests: str) -> str:
        """Create a concise prompt for AI code evaluation"""
        
        prompt = f"""You are an expert code reviewer. Analyze the following student code and focus ONLY on code quality - strengths and weaknesses of the implementation.

PROBLEM STATEMENT:
{problem_statement}

PROGRAMMING LANGUAGE: {language.upper()}

STUDENT CODE:
```{language.lower()}
{code}
```

UNIT TESTS (for context):
{unit_tests if unit_tests else "No unit tests provided"}

EVALUATION FOCUS:
- Code correctness and logic
- Code efficiency and performance
- Code readability and structure
- Best practices and conventions
- Potential bugs or issues

SCORING GUIDELINES (when no unit tests provided):
- 100%: All correct, perfect implementation
- 90%: Minor flaw (typo, variable naming issue, small syntax error, or uses print() instead of return)
- 75%: Major flaw (wrong data type, significant logic error, or uses input() when function expected)
- 50%: Logic is there but not executed properly
- 25%: Started coding but incomplete (syntax errors, undefined variables)
- 0%: Didn't try (empty code, just comments, no attempt)

Please provide your evaluation in the following JSON format:
{{
    "is_correct": true/false,
    "confidence": 0-100,
    "feedback": "Focus on specific code strengths and weaknesses in 1-3 sentences. Mention specific lines, functions, or patterns. Include scoring rationale."
}}

Avoid generic comments - be specific about the code."""

        return prompt
    
    def _send_ai_request(self, prompt: str) -> Optional[str]:
        """Send request to LM Studio and return response"""
        try:
            payload = {
                "model": "local-model",  # LM Studio uses this for local models
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,  # Lower temperature for more consistent evaluation
                "max_tokens": 300,
                "stream": False
            }
            
            response = requests.post(
                self.lm_studio_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                print(f"LM Studio API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print("LM Studio request timed out")
            return None
        except Exception as e:
            print(f"Error sending request to LM Studio: {e}")
            return None
    
    def _parse_ai_response(self, response: str) -> Tuple[bool, int, str]:
        """Parse AI response and extract evaluation results"""
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                is_correct = data.get("is_correct", False)
                confidence = data.get("confidence", 0)
                feedback = data.get("feedback", "No feedback provided")
                
                return is_correct, confidence, feedback
            else:
                # Fallback: try to parse the response text
                return self._parse_text_response(response)
                
        except json.JSONDecodeError:
            # Fallback: try to parse the response text
            return self._parse_text_response(response)
        except Exception as e:
            return False, 0, f"Error parsing AI response: {str(e)}"
    
    def _parse_text_response(self, response: str) -> Tuple[bool, int, str]:
        """Fallback parser for non-JSON responses"""
        try:
            # Look for keywords indicating correctness with code-specific focus
            response_lower = response.lower()
            
            # Positive code indicators
            positive_keywords = ["correct", "right", "good", "proper", "works", "efficient", "clean", "well-structured", "follows best practices", "optimal"]
            # Negative code indicators  
            negative_keywords = ["incorrect", "wrong", "error", "bug", "issue", "inefficient", "poor", "problem", "flaw", "weakness"]
            
            if any(word in response_lower for word in positive_keywords):
                is_correct = True
                confidence = 75
            elif any(word in response_lower for word in negative_keywords):
                is_correct = False
                confidence = 75
            else:
                is_correct = False
                confidence = 50
            
            # Clean up the response and keep it short
            feedback = response.strip()
            if len(feedback) > 200:
                feedback = feedback[:200] + "..."
            
            return is_correct, confidence, feedback
            
        except Exception:
            return False, 0, "Unable to parse AI response"


# Global AI evaluator instance
ai_evaluator = AIEvaluator()
