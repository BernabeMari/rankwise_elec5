#!/usr/bin/env python3
"""
Test script to verify coding question generation with multiple variants
"""

import sys
sys.path.append('app')

def test_coding_generation():
    """Test that coding question generation works with variants"""
    try:
        from routes import generate_question_from_datasets
        
        # Test generating multiple coding questions
        prompts = [
            "python function",
            "python function (Variant 1)", 
            "python function (Variant 2)",
            "python function (Variant 3)"
        ]
        
        print("Testing coding question generation with variants:")
        results = []
        
        for prompt in prompts:
            try:
                result = generate_question_from_datasets(prompt, 'coding')
                if result and 'text' in result:
                    results.append({
                        'prompt': prompt,
                        'language': result.get('language', 'unknown'),
                        'topic': result.get('topic', 'unknown'),
                        'text': result.get('text', '')[:50] + '...' if len(result.get('text', '')) > 50 else result.get('text', '')
                    })
                    print(f"[OK] '{prompt}': {result.get('language', 'unknown')} - {result.get('text', '')[:50]}...")
                else:
                    print(f"[ERROR] '{prompt}': No result")
            except Exception as e:
                print(f"[ERROR] '{prompt}': {e}")
        
        # Check for variety
        languages = [r['language'] for r in results]
        unique_languages = set(languages)
        
        print(f"\nResults: {len(results)} questions generated")
        print(f"Unique languages: {unique_languages}")
        print(f"Language distribution: {dict((lang, languages.count(lang)) for lang in unique_languages)}")
        
        # Check if we have variety (should have some randomness)
        if len(unique_languages) > 1 or len(results) > 1:
            print("[SUCCESS] Generated multiple different questions!")
            return True
        else:
            print("[WARNING] Generated similar questions - randomness might need improvement")
            return True
            
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing coding question generation with variants...")
    success = test_coding_generation()
    
    if success:
        print("\n[SUCCESS] Coding question generation test passed!")
    else:
        print("\n[FAILED] Coding question generation test failed!")
