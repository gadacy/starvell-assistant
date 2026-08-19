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
    buyer_id: str
    buyer_name: str
    lot_id: str
    lot_title: str
    amount: int = 1
    price: float
    total_price: float
    status: str  # paid, pending, completed, refunded, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    chat_id: Optional[str] = None

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
    event_type: str  # "new_message", "order_paid", "order_completed", "order_cancelled"
    chat_id: Optional[str] = None
    message: Optional[StarvellMessage] = None
    order: Optional[StarvellOrder] = None
    raw_data: dict = Field(default_factory=dict)
