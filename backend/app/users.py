from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, utcnow
from app.telegram_init_data import TelegramIdentity

PROFILE_FIELDS = ("username", "first_name", "last_name")


async def upsert_user(session: AsyncSession, identity: TelegramIdentity) -> None:
    dialect = session.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert

    now = utcnow()
    profile = {field: getattr(identity, field) for field in PROFILE_FIELDS}
    statement = insert(User).values(
        telegram_id=identity.telegram_id,
        first_seen_at=now,
        last_seen_at=now,
        **profile,
    )
    updates = {"last_seen_at": statement.excluded.last_seen_at}
    updates.update(
        {field: statement.excluded[field] for field, value in profile.items() if value is not None}
    )
    await session.execute(
        statement.on_conflict_do_update(index_elements=[User.telegram_id], set_=updates)
    )
