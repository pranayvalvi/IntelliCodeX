from cart import ShoppingCart

def process_payment(cart: ShoppingCart, balance: float) -> float:
    """Processes payment and returns remaining balance."""
    total = cart.get_total()
    if balance >= total:
        return balance - total
    else:
        raise Exception("Insufficient funds")
