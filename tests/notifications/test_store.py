from meridian.notifications.store import NotificationStore


def test_has_notified_false_for_unknown_event(tmp_path):
    store = NotificationStore(tmp_path / "notifications.db")

    assert store.has_notified("cal:evt-1") is False


def test_mark_notified_then_has_notified_true(tmp_path):
    store = NotificationStore(tmp_path / "notifications.db")

    store.mark_notified("cal:evt-1")

    assert store.has_notified("cal:evt-1") is True


def test_mark_notified_is_idempotent(tmp_path):
    store = NotificationStore(tmp_path / "notifications.db")

    store.mark_notified("cal:evt-1")
    store.mark_notified("cal:evt-1")

    assert store.count_notified() == 1


def test_count_notified(tmp_path):
    store = NotificationStore(tmp_path / "notifications.db")
    store.mark_notified("cal:evt-1")
    store.mark_notified("cal:evt-2")

    assert store.count_notified() == 2
