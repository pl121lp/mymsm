from navigation_history import NavigationHistory


def test_pop_on_empty_history_returns_none():
    history = NavigationHistory()
    assert history.pop() is None


def test_push_then_pop_returns_pushed_view():
    history = NavigationHistory()
    history.push((0, None))
    assert history.pop() == (0, None)


def test_pop_returns_views_in_lifo_order():
    history = NavigationHistory()
    history.push((0, 1))
    history.push((0, 2))
    history.push((1, None))
    assert history.pop() == (1, None)
    assert history.pop() == (0, 2)
    assert history.pop() == (0, 1)
    assert history.pop() is None
