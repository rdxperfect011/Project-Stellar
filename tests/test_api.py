def test_availability_api(client):
    """
    Test that the availability API only returns 'available', 'limited', or 'unavailable'
    and never exposes raw inventory numbers.
    """
    response = client.post('/api/check-availability', json={
        'checkIn': '2030-10-01',
        'checkOut': '2030-10-05'
    })
    
    assert response.status_code == 200
    data = response.get_json()
    
    assert 'status' in data
    assert data['status'] in ['available', 'limited', 'unavailable']
    
    # Ensure no raw inventory is leaked
    assert 'inventory' not in str(data).lower()
    assert 'rooms' not in str(data).lower()
    assert 'count' not in str(data).lower()
