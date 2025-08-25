from app import create_app, db
from app.models.models import Form, Question, Response, Answer
import sqlite3
import os

app = create_app()

def add_score_percentage_column():
    """Add score_percentage column to Answer table if it doesn't exist"""
    with app.app_context():
        try:
            # Connect to the SQLite database
            db_path = os.path.join(app.root_path, '..', 'instance', 'forms.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if the score_percentage column already exists
            cursor.execute("PRAGMA table_info(answer)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'score_percentage' not in columns:
                print("Adding 'score_percentage' column to Answer table...")
                cursor.execute("ALTER TABLE answer ADD COLUMN score_percentage REAL DEFAULT 0")
                conn.commit()
                print("Successfully added 'score_percentage' column")
            else:
                print("'score_percentage' column already exists in Answer table")
                
            conn.close()
            
        except Exception as e:
            print(f"Error during migration: {str(e)}")
            if 'conn' in locals() and conn:
                conn.close()

if __name__ == '__main__':
    add_score_percentage_column()
    print("Database migration completed.") 