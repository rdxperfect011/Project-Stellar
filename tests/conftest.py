import pytest
import os
from app import create_app, db
from app.models.user import User

@pytest.fixture
def app():
    # Use testing config
    os.environ['FLASK_CONFIG'] = 'testing'
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['WTF_CSRF_ENABLED'] = 'False'
    
    app = create_app('testing')
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def init_database(app):
    admin_user = User(email='admin@test.com', name='Admin')
    admin_user.password = 'password'
    db.session.add(admin_user)
    db.session.commit()
    return db
