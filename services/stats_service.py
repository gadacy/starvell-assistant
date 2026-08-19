from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy import select, func
from core.database.base import AsyncSessionLocal
from core.database.models import OrderHistory, StockItem
from core.logger import logger
from starvell.client import StarvellClient

class StatsService:
    @staticmethod
    async def sync_api_orders(client: StarvellClient):
        """Fetch latest orders from Starvell API and sync into local OrderHistory DB."""
        if not client or client.is_simulation:
            return

        try:
            api_orders = await client.get_orders()
            if not api_orders:
                return

            async with AsyncSessionLocal() as session:
                for o in api_orders:
                    # Ignore mock/test orders
                    if str(o.id).startswith("st_") or str(o.id).startswith("ord_sim"):
                        continue

                    res = await session.execute(
                        select(OrderHistory).where(OrderHistory.order_id == str(o.id))
                    )
                    record = res.scalar_one_or_none()
                    price_val = float(o.total_price or o.price or 0.0)

                    if not record:
                        session.add(OrderHistory(
                            order_id=str(o.id),
                            buyer_id=str(o.buyer_id),
                            buyer_name=o.buyer_name,
                            lot_id=str(o.lot_id),
                            lot_title=o.lot_title,
                            price=price_val,
                            status=o.status or "completed",
                            created_at=o.created_at or datetime.utcnow()
                        ))
                    else:
                        if o.status:
                            record.status = o.status
                        if price_val > 0:
                            record.price = price_val

                await session.commit()
        except Exception as e:
            logger.warning(f"[StatsService] Error syncing API orders: {e}")

    @staticmethod
    async def get_summary_stats(client: Optional[StarvellClient] = None) -> Dict[str, Any]:
        """
        Calculate statistics for sales and revenue broken down by rolling 24h periods:
        1. Сегодня (За последние 24 часа)
        2. Вчера (От 24 до 48 часов назад)
        3. 3 дня назад (За последние 3 суток / 72 часа)
        4. 7 дней назад (За последние 7 суток)
        5. Месяц назад (За последние 30 суток)
        6. 3 месяца назад (За последние 90 суток)
        7. Год (За последние 365 суток)
        8. Всё время (За все время)
        """
        if client:
            await StatsService.sync_api_orders(client)

        now = datetime.utcnow()
        hours_24_ago = now - timedelta(hours=24)
        hours_48_ago = now - timedelta(hours=48)
        days_3_ago = now - timedelta(days=3)
        days_7_ago = now - timedelta(days=7)
        days_30_ago = now - timedelta(days=30)
        days_90_ago = now - timedelta(days=90)
        days_365_ago = now - timedelta(days=365)

        valid_statuses = ["paid", "delivered", "completed"]

        async with AsyncSessionLocal() as session:
            # Filter out mock test order IDs starting with 'st_'
            res = await session.execute(
                select(OrderHistory).where(
                    OrderHistory.status.in_(valid_statuses),
                    ~OrderHistory.order_id.like("st_%")
                )
            )
            db_orders = res.scalars().all()

            # Available stock count
            res_stock = await session.execute(
                select(func.count(StockItem.id)).where(StockItem.is_used == False)
            )
            stock_available = res_stock.scalar() or 0

        # Combine with API orders if provided
        all_orders_map = {}
        for o in db_orders:
            all_orders_map[str(o.order_id)] = {
                "price": float(o.price or 0.0),
                "created_at": o.created_at or now,
                "status": o.status
            }

        if client and not client.is_simulation:
            try:
                api_orders = await client.get_orders()
                for o in api_orders:
                    if o.status in valid_statuses and not str(o.id).startswith("st_"):
                        all_orders_map[str(o.id)] = {
                            "price": float(o.total_price or o.price or 0.0),
                            "created_at": o.created_at or now,
                            "status": o.status
                        }
            except Exception:
                pass

        stats_data = {
            "today": {"count": 0, "revenue": 0.0},
            "yesterday": {"count": 0, "revenue": 0.0},
            "days_3": {"count": 0, "revenue": 0.0},
            "days_7": {"count": 0, "revenue": 0.0},
            "month_1": {"count": 0, "revenue": 0.0},
            "month_3": {"count": 0, "revenue": 0.0},
            "year_1": {"count": 0, "revenue": 0.0},
            "all_time": {"count": 0, "revenue": 0.0},
            "stock_available": stock_available
        }

        for item in all_orders_map.values():
            dt = item["created_at"]
            price = item["price"]

            # All time
            stats_data["all_time"]["count"] += 1
            stats_data["all_time"]["revenue"] += price

            # Today (Last 24 hours)
            if dt >= hours_24_ago:
                stats_data["today"]["count"] += 1
                stats_data["today"]["revenue"] += price

            # Yesterday (24 to 48 hours ago)
            if hours_48_ago <= dt < hours_24_ago:
                stats_data["yesterday"]["count"] += 1
                stats_data["yesterday"]["revenue"] += price

            # Last 3 days (72 hours)
            if dt >= days_3_ago:
                stats_data["days_3"]["count"] += 1
                stats_data["days_3"]["revenue"] += price

            # Last 7 days
            if dt >= days_7_ago:
                stats_data["days_7"]["count"] += 1
                stats_data["days_7"]["revenue"] += price

            # Last 30 days
            if dt >= days_30_ago:
                stats_data["month_1"]["count"] += 1
                stats_data["month_1"]["revenue"] += price

            # Last 90 days
            if dt >= days_90_ago:
                stats_data["month_3"]["count"] += 1
                stats_data["month_3"]["revenue"] += price

            # Last 365 days
            if dt >= days_365_ago:
                stats_data["year_1"]["count"] += 1
                stats_data["year_1"]["revenue"] += price

        return stats_data
