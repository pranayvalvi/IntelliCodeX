def calculate_average(scores: list) -> float:
    """Calculates the average of a list of scores. Returns 0.0 if the list is empty."""
    if len(scores) == 0:
        return 0.0
    return sum(scores) / (scores)
