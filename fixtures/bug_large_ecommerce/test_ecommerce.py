import pytest
from models import Product
from cart import ShoppingCart
from checkout import process_payment
from inventory import InventoryManager

def test_cart_add_duplicate():
    p1 = Product("1", "Apple", 1.0, 10)
    cart = ShoppingCart()
    cart.add_item(p1, 2)
    cart.add_item(p1, 3)
    
    # It should merge them into a single entry with quantity 5
    assert len(cart.items) == 1
    assert cart.items[0]['quantity'] == 5

def test_inventory_not_found():
    inv = InventoryManager()
    # Should return None if the product doesn't exist
    assert inv.get_product("999") is None

def test_inventory_negative_stock():
    p1 = Product("1", "Apple", 1.0, 10)
    inv = InventoryManager()
    inv.add_product(p1)
    
    # Should raise ValueError if stock goes below zero
    with pytest.raises(ValueError):
        inv.reduce_stock("1", 15)
