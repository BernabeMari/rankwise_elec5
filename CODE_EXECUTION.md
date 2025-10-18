# Code Execution System

This document describes the real-time code execution system implemented in the RankWise application.

## Overview

The Monaco editor now supports real code execution for Python, Java, C++, and C languages. When users click "Run Code", their code is actually compiled and executed on the server, with real output displayed in the output panel.

## Supported Languages

### Python
- **Compiler**: Built-in Python interpreter
- **Command**: `python <file>`
- **Security**: Restricted imports (no os, sys, subprocess, etc.)
- **Timeout**: 10 seconds

### Java
- **Compiler**: `javac` (requires JDK)
- **Command**: `java <classname>`
- **Security**: Restricted classes (no Runtime, ProcessBuilder, etc.)
- **Timeout**: 10 seconds

### C++
- **Compiler**: `g++` (requires GCC)
- **Command**: `./main`
- **Security**: Restricted includes (no fstream, cstdlib, etc.)
- **Timeout**: 10 seconds

### C
- **Compiler**: `gcc` (requires GCC)
- **Command**: `./main`
- **Security**: Restricted includes (no stdlib.h, unistd.h, etc.)
- **Timeout**: 10 seconds

## API Endpoint

### POST /execute-code

**Request Body:**
```json
{
    "code": "name = input('Enter your name: ')\nage = input('Enter your age: ')\nprint(f'Hello, {name}! You are {age} years old.')",
    "language": "python",
    "inputs": ["John", "25"]
}
```

**Response:**
```json
{
    "success": true,
    "output": "Enter your name: Hello, John!\n",
    "error": null
}
```

**Error Response:**
```json
{
    "success": false,
    "output": "",
    "error": "Compilation error: ..."
}
```

## Security Features

1. **Code Pattern Filtering**: Dangerous operations are blocked before execution
2. **Timeout Protection**: All executions are limited to 10 seconds
3. **Sandboxed Environment**: Code runs in temporary directories
4. **Resource Cleanup**: Temporary files are automatically deleted
5. **Restricted Imports**: Only safe standard library functions are allowed
6. **Input Validation**: User input is sanitized and limited to 1000 characters
7. **Input Security**: Dangerous characters are filtered from user input

## System Requirements

### For Development/Testing:
- Python 3.x (built-in)
- Java JDK (for Java support)
- GCC (for C/C++ support)

### For Production:
- All compilers must be installed on the server
- Proper file permissions for temporary directory creation
- Network access restrictions if needed

## Usage

1. Select a programming language from the language selector
2. Write code in the Monaco editor
3. Click "Run Code" button
4. If your code needs input, the input field will be highlighted and you'll see a prompt
5. Enter your input and click the "Send" button (or press Enter)
6. If more input is needed, the system will prompt for the next input
7. Continue until all inputs are provided and the program completes
8. Use the "Stop" button to halt execution at any time
9. Switch between Editor and Output tabs as needed

### Interactive Input Examples

**Python (Multiple Inputs):**
```python
name = input("Enter your name: ")
age = input("Enter your age: ")
city = input("Enter your city: ")
print(f"Hello, {name}! You are {age} years old and live in {city}.")
```
1. Click "Run Code"
2. Input field is highlighted with "Input 1: Enter your input here"
3. Type "John" and click "Send" (or press Enter)
4. Input field shows "Input 2: Enter your input here"
5. Type "25" and click "Send" (or press Enter)
6. Input field shows "Input 3: Enter your input here"
7. Type "New York" and click "Send" (or press Enter)
8. Output: `Enter your name: Enter your age: Enter your city: Hello, John! You are 25 years old and live in New York.`

**Java (Multiple Inputs):**
```java
Scanner scanner = new Scanner(System.in);
System.out.print("Enter your name: ");
String name = scanner.nextLine();
System.out.print("Enter your age: ");
int age = scanner.nextInt();
System.out.println("Hello, " + name + "! You are " + age + " years old.");
```
1. Click "Run Code"
2. Input field is highlighted with "Input 1: Enter your input here"
3. Type "Alice" and click "Send" (or press Enter)
4. Input field shows "Input 2: Enter your input here"
5. Type "30" and click "Send" (or press Enter)
6. Output: `Enter your name: Enter your age: Hello, Alice! You are 30 years old.`

**C++ (Multiple Inputs):**
```cpp
string name;
int age;
cout << "Enter your name: ";
getline(cin, name);
cout << "Enter your age: ";
cin >> age;
cout << "Hello, " << name << "! You are " << age << " years old." << endl;
```
1. Click "Run Code"
2. Input field is highlighted with "Input 1: Enter your input here"
3. Type "Bob" and click "Send" (or press Enter)
4. Input field shows "Input 2: Enter your input here"
5. Type "35" and click "Send" (or press Enter)
6. Output: `Enter your name: Enter your age: Hello, Bob! You are 35 years old.`

**C (Multiple Inputs):**
```c
char name[100];
int age;
printf("Enter your name: ");
fgets(name, sizeof(name), stdin);
printf("Enter your age: ");
scanf("%d", &age);
printf("Hello, %s! You are %d years old.", name, age);
```
1. Click "Run Code"
2. Input field is highlighted with "Input 1: Enter your input here"
3. Type "Charlie" and click "Send" (or press Enter)
4. Input field shows "Input 2: Enter your input here"
5. Type "28" and click "Send" (or press Enter)
6. Output: `Enter your name: Enter your age: Hello, Charlie! You are 28 years old.`

## Multiple Input Support

The system now supports multiple inputs in sequence, just like a real IDE:

### Features
- **Sequential Input**: Handles multiple inputs one by one as the program requests them
- **Input Queue**: Maintains a queue of inputs to provide to the program
- **Visual Feedback**: Input field shows which input number is expected
- **Stop Button**: Stop execution at any time during input collection
- **Auto-Detection**: Automatically detects when more input is needed

### How It Works
1. Program starts execution with no inputs
2. When program requests input, execution pauses and input field is highlighted
3. User enters input and presses Enter
4. Program continues with the provided input
5. If more input is needed, process repeats
6. Program completes when all inputs are provided

## Error Handling

- **Compilation Errors**: Displayed with full error messages
- **Runtime Errors**: Shown with stack traces
- **Timeout Errors**: Graceful timeout handling
- **Security Violations**: Clear security restriction messages
- **Input Errors**: Helpful messages when input is missing with tips on how to provide it
- **Auto-Detection**: System automatically detects when code needs input and highlights the input field
- **Multiple Input Errors**: Clear indication of which input caused an error

## Performance Considerations

- Each execution creates temporary files (automatically cleaned up)
- 10-second timeout prevents infinite loops
- Concurrent executions are supported
- Memory usage is limited by system resources

## Future Enhancements

- Support for additional languages (JavaScript, Go, Rust)
- Input handling for interactive programs
- Code sharing and collaboration features
- Advanced debugging capabilities
- Custom test case execution
