from busy_indicator import BusyIndicator


def test_busy_indicator_hidden_and_not_spinning_by_default(qapp):
    indicator = BusyIndicator()
    assert not indicator.isVisible()
    assert not indicator.is_spinning()


def test_start_shows_and_starts_spinning(qapp):
    indicator = BusyIndicator()
    indicator.start()
    assert indicator.isVisible()
    assert indicator.is_spinning()


def test_stop_hides_and_stops_spinning(qapp):
    indicator = BusyIndicator()
    indicator.start()
    indicator.stop()
    assert not indicator.isVisible()
    assert not indicator.is_spinning()


def test_advance_rotates_the_angle(qapp):
    indicator = BusyIndicator()
    initial_angle = indicator._angle
    indicator._advance()
    assert indicator._angle == (initial_angle + 30) % 360


def test_angle_wraps_around_at_360(qapp):
    indicator = BusyIndicator()
    indicator._angle = 350
    indicator._advance()
    assert indicator._angle == 20
