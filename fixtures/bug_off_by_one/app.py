def get_last_three_items(items: list) -> list:
    """Returns the last three items of a list. If less than 3 items, returns the whole list."""
    if len(items) < 3:
        return items
    # Fix: Correctly return the last three items
    return items[-3:]
