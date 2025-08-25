from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from os import path
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'your-secret-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forms.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    # Attempt lightweight migration: add submitted_by column to Response if missing
    with app.app_context():
        try:
            from sqlalchemy import text
            from sqlalchemy.engine import Engine
            engine: Engine = db.get_engine()
            # Check if column exists
            result = engine.execute(text("PRAGMA table_info(response);"))
            cols = [row[1] for row in result]
            if 'submitted_by' not in cols:
                engine.execute(text("ALTER TABLE response ADD COLUMN submitted_by VARCHAR(100);"))
        except Exception:
            pass

    # Initialize the auth blueprint
    from app.auth import auth
    app.register_blueprint(auth, url_prefix='/auth')
    
    # Initialize the main routes
    from app.routes import main
    app.register_blueprint(main)
    
    # Register context processors
    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    
    return app