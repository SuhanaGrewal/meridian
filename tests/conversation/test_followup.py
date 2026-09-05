from meridian.conversation.followup import rewrite_followup_question


class _FakeAnalyzer:
    def analyze(self, text, entities, language):
        return []


class _FakeMessages:
    def __init__(self, reply_text):
        self.reply_text = reply_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self.reply_text)


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeClient:
    def __init__(self, reply_text):
        self.messages = _FakeMessages(reply_text)


def test_rewrite_followup_with_no_history_returns_question_unchanged_without_calling_llm():
    client = _FakeClient("should never be used")

    result = rewrite_followup_question(
        [], "what about next month", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert result == "what about next month"
    assert client.messages.calls == []


def test_rewrite_followup_with_history_calls_llm_and_returns_rewritten_question():
    history = [
        {"role": "user", "content": "what's on my calendar this month"},
        {"role": "assistant", "content": "You have a meeting on the 10th [1]."},
    ]
    client = _FakeClient("what's on my calendar next month")

    result = rewrite_followup_question(
        history, "what about next month", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert result == "what's on my calendar next month"
    assert len(client.messages.calls) == 1


def test_rewrite_followup_falls_back_to_original_question_if_llm_returns_empty():
    history = [{"role": "user", "content": "prior question"}]
    client = _FakeClient("")

    result = rewrite_followup_question(
        history, "a follow-up", client=client, model="claude-haiku-4-5", analyzer=_FakeAnalyzer()
    )

    assert result == "a follow-up"
