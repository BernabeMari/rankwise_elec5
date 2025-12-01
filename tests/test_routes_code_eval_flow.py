def test_evaluate_code_with_custom_system_uses_custom_tests(monkeypatch):
    import app.routes as routes_mod
    # Capture arguments passed to evaluator
    captured = {}

    class DummyEvaluator:
        def evaluate_code_with_custom_tests(self, code_answer, tests, language, interactive_inputs, expected_outputs):
            captured['code_answer'] = code_answer
            captured['tests'] = tests
            captured['language'] = language
            captured['interactive_inputs'] = interactive_inputs
            captured['expected_outputs'] = expected_outputs
            return True, 100, 'Custom tests executed'

    # Monkeypatch the evaluator instance used inside routes
    import app.code_evaluator as ce
    monkeypatch.setattr(ce, 'code_evaluator', DummyEvaluator())

    ok, score, fb = routes_mod.evaluate_code_with_custom_system(
        code_answer='def f(x):\n    return x',
        question_text='Write a Python function f',
        question_unit_tests='assert f(2) == 2',
        interactive_inputs=None,
        expected_outputs=None,
    )

    assert ok is True and score == 100 and 'Custom tests executed' in fb
    assert 'def f' in captured['code_answer']
    assert 'assert f(2) == 2' in captured['tests']
    # Language detection should default to python for this code
    assert captured['language'] == 'python'


def test_detect_language_handles_c_without_includes():
    import app.routes as routes_mod

    code = """
    int sumArray(int arr[], int size) {
        int total = 0;
        for (int i = 0; i < size; ++i) {
            total += arr[i];
        }
        return total;
    }
    """
    detected = routes_mod.detect_language_from_submission(code, "Implement in C")
    assert detected == 'c'


def test_detect_language_identifies_cpp_markers_without_include():
    import app.routes as routes_mod

    code = """
    using namespace std;

    int sumVector(vector<int>& values) {
        int s = 0;
        for (int v : values) {
            s += v;
        }
        return s;
    }
    """
    detected = routes_mod.detect_language_from_submission(code, "Write a C++ function")
    assert detected == 'cpp'
