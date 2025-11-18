from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from os import path
db = SQLAlchemy()

def create_app():
	app = Flask(__name__)
	app.config['SECRET_KEY'] = 'your-secret-key'
	app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forms.db'
	app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
	
	db.init_app(app)
	
	# Ensure models are imported and tables are created on startup
	with app.app_context():
		from app.models import models
		db.create_all()
		# Reset student passwords to default on each server start
		from app.models.users import reset_student_passwords_to_default
		reset_student_passwords_to_default()
	
	# Initialize the auth blueprint
	from app.auth import auth, student_verification_codes
	app.register_blueprint(auth, url_prefix='/auth')

	# Clear in-memory verification codes on startup
	student_verification_codes.clear()
	
	# Initialize the main routes
	from app.routes import main
	app.register_blueprint(main)
	
	return app