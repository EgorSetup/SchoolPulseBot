import asyncio
from app.db.database import engine
from app.models import Base

async def init():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Таблицы успешно созданы!")

asyncio.run(init())