from app import get_last_three_items

def test_long_list():
    assert get_last_three_items([1, 2, 3, 4, 5]) == [3, 4, 5]

def test_short_list():
    assert get_last_three_items([1, 2]) == [1, 2]

def test_exact_length():
    assert get_last_three_items([1, 2, 3]) == [1, 2, 3]
