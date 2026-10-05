from calculator import calculate_average

def test_average_normal():
    assert calculate_average([10, 20, 30]) == 20.0

def calculate_average(scores: list) -> float:
    """Calculates the average of a list of scores. Returns 0.0 if the list is empty."""
    if len(scores) == 0:
        return 0.0
    return sum(scores) / len(scores)
