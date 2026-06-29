import sys
print("STARTUP: Python version", sys.version, flush=True)
print("STARTUP: Beginning imports", flush=True)

try:
    print("STARTUP: importing os", flush=True)
    import os
    print("STARTUP: os OK", flush=True)
except Exception as e:
    print("STARTUP CRASH on os import:", e, flush=True)
    raise

try:
    print("STARTUP: importing app dependencies", flush=True)
    from app import create_app, db
    import app.models
    import traceback
    print("STARTUP: app dependencies OK", flush=True)
except Exception as e:
    print("STARTUP CRASH on app dependencies import:", e, flush=True)
    raise

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
