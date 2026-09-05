"""Domain layer. Knows nothing about persistence or transport."""


class Order:
    def __init__(self, order_id: str, total: float):
        self.order_id = order_id
        self.total = total
        self.cancelled = False

    def total_with_tax(self, rate: float) -> float:
        return self.total * (1 + rate)

    def cancel(self) -> None:
        self.cancelled = True
