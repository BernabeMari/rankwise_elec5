import sqlite3

try:
    print("Connecting to database...")
    conn = sqlite3.connect('instance/forms.db')
    cursor = conn.cursor()
    
    print("Checking existing tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"Tables found: {tables}")
    
    if tables:
        print("\nChecking form table structure...")
        cursor.execute("PRAGMA table_info(form)")
        columns = cursor.fetchall()
        print("Current columns:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
        # Check if is_visible column exists
        column_names = [col[1] for col in columns]
        if 'is_visible' not in column_names:
            print("\nAdding is_visible column...")
            cursor.execute("ALTER TABLE form ADD COLUMN is_visible BOOLEAN DEFAULT 1")
            print("Column added successfully!")
            
            # Update existing records
            cursor.execute("UPDATE form SET is_visible = 1 WHERE is_visible IS NULL")
            print("Existing forms updated to visible!")
            
            conn.commit()
            print("Changes committed!")
        else:
            print("\nis_visible column already exists!")
    
    conn.close()
    print("Database connection closed.")
    
except Exception as e:
    print(f"Error: {e}")
    if 'conn' in locals():
        conn.close() 