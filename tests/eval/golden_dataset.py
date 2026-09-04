from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from meridian.indexing.parent_child import ChunkRecord
from meridian.indexing.store import IndexStore


@dataclass(frozen=True)
class GoldenDoc:
    source: str  # "gmail" | "calendar" | "docs" | "local_files"
    item_id: str
    text: str
    metadata: dict
    topic: str


@dataclass(frozen=True)
class GoldenQuestion:
    question: str
    topic: str  # for abstain questions: a topic no GoldenDoc uses
    relevant_chunk_ids: frozenset[str]
    should_abstain: bool
    source_filter: str | None = None


def chunk_id_for(doc: GoldenDoc) -> str:
    return f"{doc.source}:{doc.item_id}:0000"


GOLDEN_DOCS: list[GoldenDoc] = [
    GoldenDoc(
        "gmail", "msg-budget-q3",
        "Hi team, attached is the Q3 marketing budget report showing a 12% "
        "increase in ad spend over Q2. Please review before Friday.",
        {"subject": "Q3 Budget Report", "sender": "finance@acme.com", "sent_at": "2024-05-03T09:00:00Z"},
        topic="q3_budget",
    ),
    GoldenDoc(
        "gmail", "msg-vacation-request",
        "Hi manager, requesting PTO from July 10-17 for a family trip. "
        "Let me know if this is approved.",
        {"subject": "PTO Request", "sender": "sam@acme.com", "sent_at": "2024-06-01T14:00:00Z"},
        topic="vacation_request",
    ),
    GoldenDoc(
        "gmail", "msg-security-incident",
        "We detected unusual login activity on the staging server at 2am "
        "UTC. IT has rotated credentials and is investigating root cause.",
        {"subject": "Security Alert: Staging Login Activity", "sender": "it@acme.com", "sent_at": "2024-04-12T02:30:00Z"},
        topic="security_incident",
    ),
    GoldenDoc(
        "gmail", "msg-launch-press",
        "Draft press release attached for the June 15 product launch, need "
        "finance sign-off on the marketing spend by Friday.",
        {"subject": "Launch Press Release Draft", "sender": "pr@acme.com", "sent_at": "2024-06-05T11:00:00Z"},
        topic="product_launch",
    ),
    GoldenDoc(
        "gmail", "msg-conference-invite",
        "You're invited to speak at DevCon 2024 in September, topic: "
        "scaling data pipelines.",
        {"subject": "DevCon 2024 Speaker Invitation", "sender": "events@devcon.org", "sent_at": "2024-05-20T10:00:00Z"},
        topic="conference_invite",
    ),
    GoldenDoc(
        "calendar", "evt-standup",
        "Daily engineering standup, 9:00-9:15am, discuss sprint blockers "
        "and yesterday's progress.",
        {"summary": "Engineering Standup", "start_at": "2024-05-06T09:00:00Z"},
        topic="eng_standup",
    ),
    GoldenDoc(
        "calendar", "evt-launch-review",
        "Product Launch Review meeting, June 15 2pm - finance and "
        "marketing align on launch-day budget approval.",
        {"summary": "Product Launch Review", "start_at": "2024-06-15T14:00:00Z"},
        topic="product_launch",
    ),
    GoldenDoc(
        "calendar", "evt-dentist",
        "Dentist checkup, 10am, Downtown Dental.",
        {"summary": "Dentist Checkup", "start_at": "2024-05-15T10:00:00Z"},
        topic="dentist_appointment",
    ),
    GoldenDoc(
        "calendar", "evt-board-meeting",
        "Quarterly board meeting - review Q3 budget numbers and the "
        "product roadmap.",
        {"summary": "Q3 Board Meeting", "start_at": "2024-05-10T13:00:00Z"},
        topic="board_meeting",
    ),
    GoldenDoc(
        "calendar", "evt-team-offsite",
        "Team offsite in Austin, Oct 3-4, focus on planning next quarter's "
        "roadmap.",
        {"summary": "Team Offsite - Austin", "start_at": "2024-10-03T09:00:00Z"},
        topic="team_offsite",
    ),
    GoldenDoc(
        "docs", "doc-onboarding",
        "New Hire Onboarding Guide: complete your I-9 form within three "
        "business days, set up your laptop via IT self-service, and "
        "schedule a 1:1 with your manager in week one.",
        {"title": "New Hire Onboarding Guide"},
        topic="onboarding",
    ),
    GoldenDoc(
        "docs", "doc-security-policy",
        "Company security policy: rotate passwords every 90 days, use "
        "hardware keys for admin access.",
        {"title": "Security Policy"},
        topic="security_policy",
    ),
    GoldenDoc(
        "docs", "doc-roadmap-q4",
        "Q4 product roadmap: ship the mobile app redesign, expand API "
        "rate limits, begin SOC2 audit prep.",
        {"title": "Q4 Product Roadmap"},
        topic="q4_roadmap",
    ),
    GoldenDoc(
        "docs", "doc-travel-policy",
        "Travel expense policy: submit receipts within 30 days, economy "
        "class for flights under 6 hours.",
        {"title": "Travel Expense Policy"},
        topic="travel_policy",
    ),
    GoldenDoc(
        "local_files", "note-launch-plan",
        "Meeting notes: product launch is targeted for June 15th. "
        "Marketing will coordinate the press release with finance on the "
        "launch-day budget.",
        {"path": "notes/launch-plan.md"},
        topic="product_launch",
    ),
    GoldenDoc(
        "local_files", "note-interview-feedback",
        "Feedback notes for candidate Jordan: strong system design, weak "
        "on behavioral questions. Recommend hire for the backend role.",
        {"path": "notes/interview-jordan.md"},
        topic="interview_feedback",
    ),
    GoldenDoc(
        "local_files", "note-security-incident-followup",
        "Follow-up notes on the staging incident: root cause was a leaked "
        "SSH key in a public repo, key rotated, added secret-scanning to "
        "CI.",
        {"path": "notes/security-incident-followup.md"},
        topic="security_incident",
    ),
    GoldenDoc(
        "local_files", "note-book-recommendations",
        "Reading list from book club: Thinking in Systems, The Phoenix "
        "Project, Staff Engineer.",
        {"path": "notes/book-club.md"},
        topic="book_recommendations",
    ),
]

GOLDEN_QUESTIONS: list[GoldenQuestion] = [
    GoldenQuestion(
        "what was the Q3 budget report about",
        topic="q3_budget",
        relevant_chunk_ids=frozenset({"gmail:msg-budget-q3:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "when is my vacation request for",
        topic="vacation_request",
        relevant_chunk_ids=frozenset({"gmail:msg-vacation-request:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "who is invited to speak at DevCon 2024",
        topic="conference_invite",
        relevant_chunk_ids=frozenset({"gmail:msg-conference-invite:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what time is the daily engineering standup",
        topic="eng_standup",
        relevant_chunk_ids=frozenset({"calendar:evt-standup:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "when is the dentist appointment",
        topic="dentist_appointment",
        relevant_chunk_ids=frozenset({"calendar:evt-dentist:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what topics will the board meeting cover",
        topic="board_meeting",
        relevant_chunk_ids=frozenset({"calendar:evt-board-meeting:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "where is the team offsite happening",
        topic="team_offsite",
        relevant_chunk_ids=frozenset({"calendar:evt-team-offsite:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what do I need to do in my first week as a new hire",
        topic="onboarding",
        relevant_chunk_ids=frozenset({"docs:doc-onboarding:0000"}),
        should_abstain=False,
        source_filter="docs",
    ),
    GoldenQuestion(
        "how often should I rotate my password per company policy",
        topic="security_policy",
        relevant_chunk_ids=frozenset({"docs:doc-security-policy:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what's planned for Q4 on the product roadmap",
        topic="q4_roadmap",
        relevant_chunk_ids=frozenset({"docs:doc-roadmap-q4:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "how long do I have to submit travel receipts",
        topic="travel_policy",
        relevant_chunk_ids=frozenset({"docs:doc-travel-policy:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "how did the candidate Jordan's interview go",
        topic="interview_feedback",
        relevant_chunk_ids=frozenset({"local_files:note-interview-feedback:0000"}),
        should_abstain=False,
        source_filter="local_files",
    ),
    GoldenQuestion(
        "what books did the book club recommend",
        topic="book_recommendations",
        relevant_chunk_ids=frozenset({"local_files:note-book-recommendations:0000"}),
        should_abstain=False,
    ),
    GoldenQuestion(
        "how does the product launch relate to the budget",
        topic="product_launch",
        relevant_chunk_ids=frozenset({
            "gmail:msg-launch-press:0000",
            "calendar:evt-launch-review:0000",
            "local_files:note-launch-plan:0000",
        }),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what was the root cause of the security incident and how was it fixed",
        topic="security_incident",
        relevant_chunk_ids=frozenset({
            "gmail:msg-security-incident:0000",
            "local_files:note-security-incident-followup:0000",
        }),
        should_abstain=False,
    ),
    GoldenQuestion(
        "what is my gym membership renewal date",
        topic="unmatched_gym_membership",
        relevant_chunk_ids=frozenset(),
        should_abstain=True,
    ),
    GoldenQuestion(
        "what is the wifi password for the office",
        topic="unmatched_wifi_password",
        relevant_chunk_ids=frozenset(),
        should_abstain=True,
    ),
    GoldenQuestion(
        "when does my flight to Chicago depart",
        topic="unmatched_flight_booking",
        relevant_chunk_ids=frozenset(),
        should_abstain=True,
    ),
]

_ALL_TOPICS = sorted({doc.topic for doc in GOLDEN_DOCS} | {q.topic for q in GOLDEN_QUESTIONS})
_TOPIC_INDEX = {topic: index for index, topic in enumerate(_ALL_TOPICS)}


def topic_vector(topic: str) -> np.ndarray:
    """exact one-hot per topic - same-topic pairs get cosine similarity of
    exactly 1.0, different-topic pairs exactly 0.0, so the fast eval's
    ranking is deterministic by construction, not by chance."""
    vector = np.zeros(len(_ALL_TOPICS), dtype=np.float32)
    vector[_TOPIC_INDEX[topic]] = 1.0
    return vector


def build_golden_store(store: IndexStore, *, embed: Callable[[GoldenDoc], np.ndarray]) -> None:
    for doc in GOLDEN_DOCS:
        record = ChunkRecord(text=doc.text, parent_text=doc.text, position=0, is_own_parent=True)
        store.upsert_item_chunks(doc.source, doc.item_id, [record], [embed(doc)], doc.metadata)
