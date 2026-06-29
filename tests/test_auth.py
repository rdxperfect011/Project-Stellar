def test_admin_access_requires_login(client):
    """
    Test that an unauthenticated user cannot access the admin dashboard
    """
    response = client.get('/admin/', follow_redirects=True)
    
    # Should redirect to login page
    assert response.status_code == 200
    assert b'Admin Portal' in response.data

def test_admin_login(client, init_database):
    """
    Test successful login flow
    """
    response = client.post('/auth/login', data={
        'email': 'admin@test.com',
        'password': 'password'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Admin Dashboard' in response.data
