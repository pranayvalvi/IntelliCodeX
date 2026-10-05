def add_event(event: str, events_list: list = []) -> list:
    """Appends an event to a list and returns the list."""
    # Bug: Mutable default argument 'events_list' causes state to persist across calls
    events_list.append(event)
    return events_list
