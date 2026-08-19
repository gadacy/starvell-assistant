from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import config

engine = create_async_engine(
    config.database_url,
    echo=False,
    future=True
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy import select
    from core.database.models import QuickReply
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(QuickReply))
        if not res.scalars().all():
            defaults = [
                QuickReply(title="👋 Приветствие", text="Здравствуйте! Чем могу помочь?"),
                QuickReply(title="✅ Выдача товара", text="Ваш заказ выполнен! Проверьте, пожалуйста, и подтвердите получение."),
                QuickReply(title="⏳ Проверка", text="Секундочку, проверяю информацию по вашему заказу..."),
                QuickReply(title="⭐ Попросить отзыв", text="Спасибо за покупку! Пожалуйста, оставьте отзыв, будем очень благодарны.")
            ]
            session.add_all(defaults)
            await session.commit()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
