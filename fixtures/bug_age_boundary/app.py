def can_vote(age: int) -> bool:
    """Returns True if the user is old enough to vote (18 or older)."""
    if age > 18:
        return True
    return False
