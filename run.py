import os
from app import create_app, db
import app.models

import traceback

try:
    app = create_app(os.getenv('FLASK_CONFIG') or 'default')
except Exception as e:
    print("STARTUP ERROR:", traceback.format_exc())
    raise

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Ensure tables are created for local development
        from app.utils.db_seed import seed_database
        seed_database()
    app.run(port=5002, debug=True)
