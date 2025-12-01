import subprocess

def run_junit():
    print("Running Java JUnit tests...")
    # Compile Java
    subprocess.run(["javac", "student_submissions/StudentCode.java", "tests/test_java.java"])
    # Run JUnit using Java (assumes junit jar in classpath)
    result = subprocess.run(["java", "-cp", ".:junit-5.9.3.jar:hamcrest-core-1.3.jar", "org.junit.platform.console.ConsoleLauncher",
                             "--select-class", "BitShiftTest"], capture_output=True, text=True)
    print(result.stdout)
    return "FAILURE" not in result.stdout

def run_gtest_cpp():
    print("Running C++ Google Test...")
    subprocess.run(["g++", "-std=c++17", "student_submissions/student.cpp", "tests/test_cpp.cpp", "-lgtest", "-lgtest_main", "-pthread", "-o", "test_cpp"])
    result = subprocess.run(["./test_cpp"], capture_output=True, text=True)
    print(result.stdout)
    return result.returncode == 0

def run_c_tests():
    print("Running C tests...")
    subprocess.run(["gcc", "student_submissions/student.c", "tests/test_c.c", "-o", "test_c"])
    result = subprocess.run(["./test_c"], capture_output=True, text=True)
    print(result.stdout)
    return result.returncode == 0

if __name__ == "__main__":
    results = {
        "Java": run_junit(),
        "C++": run_gtest_cpp(),
        "C": run_c_tests()
    }
    
    print("\nSummary:")
    for lang, passed in results.items():
        print(f"{lang}: {'PASSED' if passed else 'FAILED'}")
