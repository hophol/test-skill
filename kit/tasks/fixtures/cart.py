"""购物车模块 —— pytest 任务被测对象"""


class Cart:
    def __init__(self):
        self.items = []          # [(sku, price, qty)]

    def add(self, sku, price, qty=1):
        if price <= 0:
            raise ValueError("price must be positive")
        if not isinstance(qty, int) or qty < 1:
            raise ValueError("qty must be a positive integer")
        self.items.append((sku, price, qty))

    def subtotal(self):
        return sum(p * q for _, p, q in self.items)

    def payable(self, is_vip=False):
        """VIP 95 折;满 200 减 30,可叠加(折后参与满减)"""
        s = self.subtotal() * (0.95 if is_vip else 1)
        return round(s - int(s // 200) * 30, 2)

    def count(self):
        return sum(q for _, _, q in self.items)
