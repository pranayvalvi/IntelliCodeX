from app import can_vote

def test_can_vote_adult():
    assert can_vote(20) == True

def test_can_vote_minor():
    assert can_vote(16) == False

def test_can_vote_exact_boundary():
    # A user who is exactly 18 should be allowed to vote
    assert can_vote(18) == True
