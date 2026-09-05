from meridian.reminders.store import ReminderStore


def test_add_reminder_and_get_reminder(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")

    reminder_id = store.add_reminder(
        "meet with Nick", proposed_slot_start="2024-06-03T14:00:00+00:00", proposed_slot_end="2024-06-03T14:30:00+00:00"
    )

    row = store.get_reminder(reminder_id)
    assert row["reminder_text"] == "meet with Nick"
    assert row["status"] == "pending"
    assert row["proposed_slot_start"] == "2024-06-03T14:00:00+00:00"


def test_add_reminder_without_a_proposed_slot(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")

    reminder_id = store.add_reminder("call the accountant")

    row = store.get_reminder(reminder_id)
    assert row["proposed_slot_start"] is None
    assert row["proposed_slot_end"] is None


def test_dismiss_marks_status_and_returns_true(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")
    reminder_id = store.add_reminder("meet with Nick")

    dismissed = store.dismiss(reminder_id)

    assert dismissed is True
    row = store.get_reminder(reminder_id)
    assert row["status"] == "dismissed"
    assert row["decided_at"] is not None


def test_dismiss_unknown_id_returns_false(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")

    assert store.dismiss("does-not-exist") is False


def test_list_pending_reminders_excludes_dismissed(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")
    keep_id = store.add_reminder("meet with Nick")
    dismiss_id = store.add_reminder("call the accountant")
    store.dismiss(dismiss_id)

    pending = store.list_pending_reminders()

    assert len(pending) == 1
    assert pending[0]["reminder_id"] == keep_id


def test_count_reminders(tmp_path):
    store = ReminderStore(tmp_path / "reminders.db")
    store.add_reminder("a")
    store.add_reminder("b")

    assert store.count_reminders() == 2
