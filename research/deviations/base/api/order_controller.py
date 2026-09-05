"""Transport layer. Talks to the service layer only."""
from domain.order import Order
from service.order_service import OrderService


class OrderController:
    def __init__(self, service: OrderService):
        self.service = service

    def create(self, payload: dict) -> dict:
        order = Order(payload["id"], payload["total"])
        placed = self.service.place(order)
        return {"ok": placed}

    def get(self, order_id: str) -> dict:
        return {"id": order_id}
