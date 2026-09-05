from meridian.inbox_intelligence.gmail_filters import NON_ACTIONABLE_CATEGORIES, looks_like_auto_reply


def test_auto_reply_subject_variants_are_detected():
    assert looks_like_auto_reply("Auto Reply", "someone@example.com")
    assert looks_like_auto_reply("Automatic reply: away", "someone@example.com")
    assert looks_like_auto_reply("Out of Office: back Monday", "someone@example.com")
    assert looks_like_auto_reply("Undeliverable: your message", "someone@example.com")


def test_noreply_sender_variants_are_detected():
    assert looks_like_auto_reply("Hi there", "Some Service <no-reply@service.example.com>")
    assert looks_like_auto_reply("Hi there", "Some Service <donotreply@service.example.com>")
    assert looks_like_auto_reply("Hi there", "Mailer Daemon <mailer-daemon@example.com>")


def test_normal_message_is_not_flagged():
    assert not looks_like_auto_reply("Re: Event documentation", "Alice <alice@example.com>")


def test_non_actionable_categories_contains_expected_labels():
    assert "CATEGORY_PROMOTIONS" in NON_ACTIONABLE_CATEGORIES
    assert "CATEGORY_SOCIAL" in NON_ACTIONABLE_CATEGORIES
    assert "CATEGORY_PERSONAL" not in NON_ACTIONABLE_CATEGORIES
