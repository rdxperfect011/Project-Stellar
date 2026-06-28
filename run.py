import os
from app import create_app, db
import app.models

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Ensure tables are created for local development
    app.run(port=5001, debug=True)
