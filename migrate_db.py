from app import create_app, db
from app.models.models import Form, Question, Response, Answer
import sqlite3
import os

app = create_app()

def add_points_column():
    """Add points column to Question table if it doesn't exist"""
    with app.app_context():
        try:
            # Connect to the SQLite database
            db_path = os.path.join(app.root_path, '..', 'instance', 'forms.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if the points column already exists
            cursor.execute("PRAGMA table_info(question)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'points' not in columns:
                print("Adding 'points' column to Question table...")
                cursor.execute("ALTER TABLE question ADD COLUMN points INTEGER DEFAULT 1")
                conn.commit()
                print("Successfully added 'points' column")
            else:
                print("'points' column already exists in Question table")
                
            conn.close()
            
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            if conn:
                conn.close()

if __name__ == '__main__':
    add_points_column()
    print("Database migration completed.") 