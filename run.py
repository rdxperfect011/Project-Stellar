import os
from app import create_app, db
import app.models

app = create_app(os.getenv('FLASK_CONFIG') or 'default')

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Ensure tables are created for local development
        from app.utils.db_seed import seed_database
        seed_database()
    app.run(port=5002, debug=True)
