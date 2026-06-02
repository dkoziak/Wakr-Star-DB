from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from config import settings

engine = create_async_engine(settings.stardb_url, pool_pre_ping=True)


@asynccontextmanager
async def get_conn() -> AsyncConnection:
    async with engine.connect() as conn:
        yield conn
