# add_category_column.py
import sqlite3
import os

def add_category_column():
    db_path = 'instance/forms.db'
    
    print(f"🔧 Adding category column to question table in: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if category column already exists
        cursor.execute("PRAGMA table_info(question)")
        question_columns = [col[1] for col in cursor.fetchall()]
        
        if 'category' not in question_columns:
            # Add the category column
            cursor.execute("ALTER TABLE question ADD COLUMN category VARCHAR(50)")
            print("✅ Added category column to question table")
            
            # Set default values for existing records
            cursor.execute("UPDATE question SET category = 'general' WHERE category IS NULL")
            print("✅ Set default category 'general' for existing questions")
        else:
            print("✅ category column already exists in question table")
        
        # Verify the change
        cursor.execute("PRAGMA table_info(question)")
        final_columns = [col[1] for col in cursor.fetchall()]
        print(f"🎯 Final question table columns: {final_columns}")
        
        # Show some sample data
        cursor.execute("SELECT id, question_text, category FROM question LIMIT 3")
        sample_data = cursor.fetchall()
        print("\n📝 Sample question data:")
        for row in sample_data:
            print(f"  - ID: {row[0]}, Text: {row[1][:50]}..., Category: {row[2]}")
        
        conn.commit()
        conn.close()
        print("\n✅ Category column added successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Failed to add category column: {e}")
        return False

if __name__ == "__main__":
    add_category_column()