from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, Field

class StarvellUser(BaseModel):
    id: str
    username: str
    public_id: Optional[str] = None
    avatar: Optional[str] = None
    is_online: bool = False
    balance_rub: float = 0.0
    balance_hold: float = 0.0
    rating: float = 5.0
    reviews_count: int = 0
    kyc_status: str = "VERIFIED"
    is_selling_enabled: bool = True

class StarvellMessage(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    sender_name: str
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False
    order_id: Optional[str] = None

class StarvellOrder(BaseModel):
    id: str
    short_id: Optional[str] = None
    full_id: Optional[str] = None
    buyer_id: str
    buyer_name: str
    lot_id: str
    lot_title: str
    amount: int = 1
    price: float = 0.0
    total_price: float = 0.0
    status: str = "paid"  # paid, pending, completed, refunded, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    chat_id: Optional[str] = None

    @property
    def order_url(self) -> str:
        if self.full_id:
            return f"https://starvell.com/order/{self.full_id}"
        if self.chat_id:
            return f"https://starvell.com/chat/{self.chat_id}"
        return "https://starvell.com"

class StarvellReview(BaseModel):
    id: str
    rating: int = 5  # 1 to 5 stars
    content: str = ""
    order_id: Optional[str] = None  # Full UUID for order url (e.g. 01a04ef2-c0f3-5640-8cfa-5f0a190a4f13)
    order_short_id: Optional[str] = None  # Human-readable order code (e.g. F37WQ43K)
    lot_title: Optional[str] = None
    buyer_id: Optional[str] = None
    buyer_name: Optional[str] = "Покупатель"
    buyer_avatar: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    chat_id: Optional[str] = None
    is_anonymous: bool = False

    @property
    def stars_display(self) -> str:
        r = max(1, min(5, int(self.rating or 5)))
        return "⭐" * r

    @property
    def order_url(self) -> str:
        if self.order_id:
            return f"https://starvell.com/order/{self.order_id}"
        if self.chat_id:
            return f"https://starvell.com/chat/{self.chat_id}"
        return "https://starvell.com"

class StarvellLot(BaseModel):
    id: str
    public_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    price: float
    amount: int = 1
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    game_id: Optional[str] = None
    game_name: Optional[str] = None
    is_active: bool = True
    can_raise: bool = False
    next_raise_at: Optional[datetime] = None

class StarvellEvent(BaseModel):
    event_type: str  # "new_message", "order_paid", "order_completed", "order_cancelled", "new_review"
    chat_id: Optional[str] = None
    message: Optional[StarvellMessage] = None
    order: Optional[StarvellOrder] = None
    review: Optional[StarvellReview] = None
    raw_data: dict = Field(default_factory=dict)
