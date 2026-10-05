from models import Product

class ShoppingCart:
    def __init__(self):
        self.items = [] 

class ShoppingCart:
    def __init__(self):
        self.items = [] 

    def add_item(self, product: Product, quantity: int):
        # Check if the product already exists in the cart
        for item in self.items:
            if item['product'] == product:
                # If it exists, increase the quantity
                item['quantity'] += quantity
                return
        # If it doesn't exist, add it as a new item
        self.items.append({'product': product, 'quantity': quantity})

    def get_total(self) -> float:
        total = 0.0
        for item in self.items:
            total += item['product'].price * item['quantity']
        return total

    def get_total(self) -> float:
        total = 0.0
        for item in self.items:
            total += item['product'].price * item['quantity']
        return total
