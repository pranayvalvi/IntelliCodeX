from app import get_user_email

def test_has_email():
    assert get_user_email({"name": "Alice", "email": "alice@example.com"}) == "alice@example.com"

def test_missing_email():
    assert get_user_email({"name": "Bob"}) == "No Email"
