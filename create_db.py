from app import create_app, db
from app.models.models import Form, Question, Response, Answer

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()
    print("Database has been recreated with updated schema.") 