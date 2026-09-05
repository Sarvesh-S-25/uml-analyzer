"""Persistence layer."""
from domain.order import Order


class Repository:
    """The persistence contract the service layer depends on."""

    def save(self, entity: Order) -> bool:
        raise NotImplementedError


class OrderRepository(Repository):
    def __init__(self):
        self.rows = {}

    def save(self, entity: Order) -> bool:
        self.rows[entity.order_id] = entity
        return True

    def find_by_id(self, order_id: str) -> Order:
        return self.rows.get(order_id)

    def delete(self, order_id: str) -> bool:
        return self.rows.pop(order_id, None) is not None
