from logger import add_event

def test_single_event():
    assert add_event("start") == ["start"]

def test_isolated_events():
    # Because of the mutable default argument, this will fail
    # It will return ["start", "stop"] instead of ["stop"]
    assert add_event("stop") == ["stop"]
