def get_user_email(user_data: dict) -> str:
    """Returns the user's email, or 'No Email' if not provided."""
    return user_data.get("email", "No Email")
