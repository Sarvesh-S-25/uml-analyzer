"""Application layer. Talks to persistence; never to transport."""
from domain.order import Order
from persistence.repository import OrderRepository


class OrderService:
    def __init__(self, repo: OrderRepository, audit: "AuditLog" = None):
        self.repo = repo
        self.audit = audit

    def place(self, order: Order) -> bool:
        saved = self.repo.save(order)
        return saved

    def cancel(self, order_id: str) -> bool:
        order = self.repo.find_by_id(order_id)
        if order is None:
            return False
        order.cancel()
        return self.repo.save(order)

    def refund(self, order_id: str) -> bool:
        return self.repo.delete(order_id)


class AuditLog:
    def __init__(self):
        self.entries = []

    def record(self, message: str) -> None:
        self.entries.append(message)
