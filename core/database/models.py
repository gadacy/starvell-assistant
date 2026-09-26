from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, Integer, BigInteger, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database.base import Base

class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=True)

class AutoResponse(Base):
    __tablename__ = "auto_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, default="contains")  # exact, contains, regex, first_message, order_paid
    pattern: Mapped[str] = mapped_column(Text, nullable=False, default="")
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    lot_id: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lot_name: Mapped[str] = mapped_column(String(255), nullable=True)
    item_data: Mapped[str] = mapped_column(Text, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    buyer_id: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class OrderHistory(Base):
    __tablename__ = "order_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    order_uuid: Mapped[str] = mapped_column(String(100), nullable=True)
    buyer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    lot_id: Mapped[str] = mapped_column(String(100), nullable=False)
    lot_title: Mapped[str] = mapped_column(String(255), nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new")
    chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivered_content: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ReviewHistory(Base):
    __tablename__ = "review_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(100), nullable=True)
    order_short_id: Mapped[str] = mapped_column(String(100), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=5)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    author_name: Mapped[str] = mapped_column(String(255), nullable=True)
    lot_title: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DumperRule(Base):
    __tablename__ = "dumper_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    lot_title: Mapped[str] = mapped_column(String(255), nullable=True)
    min_price: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    max_price: Mapped[float] = mapped_column(Float, nullable=False, default=100000.0)
    step: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class PluginState(Base):
    __tablename__ = "plugin_states"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    settings_json: Mapped[str] = mapped_column(Text, default="{}")

class QuickReply(Base):
    __tablename__ = "quick_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SeenChat(Base):
    __tablename__ = "seen_chats"

    chat_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatPurchase(Base):
    """Purchase context independent of automatic delivery and chat activity."""
    __tablename__ = "chat_purchases"

    order_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    chat_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    buyer_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)


class TelegramChatLink(Base):
    """Route a Telegram reply using the exact chat/message pair, never quoted text."""
    __tablename__ = "telegram_chat_links"

    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    starvell_chat_id: Mapped[str] = mapped_column(String(100), nullable=False)
