from typing import Optional
from models import Product

class InventoryManager:
    def __init__(self):
        self.catalog = {}

    def add_product(self, product: Product):
        self.catalog[product.id] = product

    def get_product(self, product_id: str) -> Optional[Product]:
        # Bug 2: Raises KeyError instead of returning None if missing
        return self.catalog[product_id]
    
    def reduce_stock(self, product_id: str, quantity: int):
        product = self.get_product(product_id)
        if product:
            # Bug 3: Allows stock to drop below zero instead of raising ValueError
            product.stock -= quantity
