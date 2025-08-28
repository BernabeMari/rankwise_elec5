#!/usr/bin/env python3
"""
Database migration script to add is_visible column to forms table.
This script will update the existing database schema.
"""

import sqlite3
import os

def migrate_database():
    """Add is_visible column to forms table"""
    
    db_path = 'instance/forms.db'
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(form)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_visible' not in columns:
            # Add the new column with default value True
            cursor.execute("ALTER TABLE form ADD COLUMN is_visible BOOLEAN DEFAULT 1")
            print("✅ Added 'is_visible' column to form table")
            
            # Update existing forms to be visible by default
            cursor.execute("UPDATE form SET is_visible = 1 WHERE is_visible IS NULL")
            print("✅ Set all existing forms to visible")
            
            conn.commit()
            print("✅ Database migration completed successfully!")
        else:
            print("✅ Column 'is_visible' already exists")
        
        # Verify the migration
        cursor.execute("SELECT id, title, is_visible FROM form LIMIT 5")
        forms = cursor.fetchall()
        
        print("\n📋 Sample forms after migration:")
        for form_id, title, is_visible in forms:
            status = "Visible" if is_visible else "Hidden"
            print(f"  - Form {form_id}: '{title}' - {status}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("🔄 Starting database migration...")
    success = migrate_database()
    if success:
        print("\n🎉 Migration completed! You can now run the Flask application.")
    else:
        print("\n💥 Migration failed! Please check the error messages above.") 