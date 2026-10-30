from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.subscription_service import reserve_ai_usage


class FakeResult:
    def __init__(self, subscription):
        self.subscription = subscription

    def scalar_one_or_none(self):
        return self.subscription


class FakeDB:
    def __init__(self, subscription):
        self.subscription = subscription
        self.commits = 0
        self.added = []

    async def execute(self, _statement):
        return FakeResult(self.subscription)

    def add(self, item):
        self.added.append(item)
        self.subscription = item

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        return None


def make_subscription(**overrides):
    values = {
        "user_id": 7,
        "plan": "free",
        "messages_used": 0,
        "messages_limit": 50,
        "is_active": True,
        "expires_at": None,
        "usage_date": datetime.now(timezone.utc).date(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_reserve_ai_usage_increments_under_limit():
    sub = make_subscription(messages_used=49)
    db = FakeDB(sub)
    await reserve_ai_usage(7, db)
    assert sub.messages_used == 50
    assert db.commits == 1


@pytest.mark.anyio
async def test_reserve_ai_usage_rejects_at_limit():
    db = FakeDB(make_subscription(messages_used=50))
    with pytest.raises(HTTPException) as exc:
        await reserve_ai_usage(7, db)
    assert exc.value.status_code == 429
    assert db.commits == 0


@pytest.mark.anyio
async def test_reserve_ai_usage_resets_counter_on_new_utc_day():
    sub = make_subscription(
        messages_used=50,
        usage_date=datetime.now(timezone.utc).date() - timedelta(days=1),
    )
    db = FakeDB(sub)
    await reserve_ai_usage(7, db)
    assert sub.usage_date == datetime.now(timezone.utc).date()
    assert sub.messages_used == 1
    assert db.commits == 1


@pytest.mark.anyio
async def test_reserve_ai_usage_rejects_inactive_subscription():
    db = FakeDB(make_subscription(is_active=False))
    with pytest.raises(HTTPException) as exc:
        await reserve_ai_usage(7, db)
    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_reserve_ai_usage_rejects_expired_subscription():
    db = FakeDB(make_subscription(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)
    ))
    with pytest.raises(HTTPException) as exc:
        await reserve_ai_usage(7, db)
    assert exc.value.status_code == 403

@pytest.mark.anyio
@pytest.mark.parametrize(
    ("plan", "expected_limit"),
    [
        ("free", 50),
        ("pro", 200),
        ("enterprise", 1000),
    ],
)
async def test_reserve_ai_usage_uses_plan_limit(plan, expected_limit):
    sub = make_subscription(
        plan=plan,
        messages_used=0,
        messages_limit=50,
    )
    db = FakeDB(sub)

    await reserve_ai_usage(7, db)

    assert sub.messages_limit == expected_limit
    assert sub.messages_used == 1
    assert db.commits == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("plan", "limit"),
    [
        ("free", 50),
        ("pro", 200),
        ("enterprise", 1000),
    ],
)
async def test_reserve_ai_usage_rejects_at_plan_limit(plan, limit):
    sub = make_subscription(
        plan=plan,
        messages_used=limit,
        messages_limit=50,
    )
    db = FakeDB(sub)

    with pytest.raises(HTTPException) as exc:
        await reserve_ai_usage(7, db)

    assert exc.value.status_code == 429
    assert sub.messages_used == limit
    assert db.commits == 0


@pytest.mark.anyio
async def test_reserve_ai_usage_rejects_unknown_plan():
    db = FakeDB(make_subscription(plan="unknown"))

    with pytest.raises(HTTPException) as exc:
        await reserve_ai_usage(7, db)

    assert exc.value.status_code == 403
    assert db.commits == 0
