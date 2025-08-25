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