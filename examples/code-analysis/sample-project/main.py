"""Sample project for Toonic code analysis demo."""

import os
import sys
from typing import List, Optional


class UserService:
    """Manages user operations."""

    def __init__(self, db_url: str = "sqlite:///users.db"):
        self.db_url = db_url
        self.users = {}

    def create_user(self, name: str, email: str) -> dict:
        """Create a new user."""
        user_id = len(self.users) + 1
        user = {"id": user_id, "name": name, "email": email, "active": True}
        self.users[user_id] = user
        return user

    def get_user(self, user_id: int) -> Optional[dict]:
        """Get user by ID."""
        return self.users.get(user_id)

    def list_users(self, active_only: bool = True) -> List[dict]:
        """List all users."""
        users = list(self.users.values())
        if active_only:
            users = [u for u in users if u.get("active")]
        return users

    def deactivate_user(self, user_id: int) -> bool:
        """Deactivate a user — potential bug: no existence check."""
        self.users[user_id]["active"] = False  # KeyError if not found
        return True


class OrderService:
    """Manages orders — has intentional issues for analysis."""

    def __init__(self):
        self.orders = []

    def create_order(self, user_id: int, items: list, total: float) -> dict:
        """Create order — no validation on total."""
        order = {
            "id": len(self.orders) + 1,
            "user_id": user_id,
            "items": items,
            "total": total,  # Bug: no validation, could be negative
            "status": "pending",
        }
        self.orders.append(order)
        return order

    def get_orders(self, user_id: int) -> list:
        """Get orders for user — inefficient O(n) scan."""
        return [o for o in self.orders if o["user_id"] == user_id]

    def process_payment(self, order_id: int) -> bool:
        """Process payment — hardcoded credentials (security issue)."""
        API_KEY = "sk-live-1234567890abcdef"  # Hardcoded secret!
        # ... payment processing logic ...
        for order in self.orders:
            if order["id"] == order_id:
                order["status"] = "paid"
                return True
        return False


def main():
    svc = UserService()
    alice = svc.create_user("Alice", "alice@example.com")
    bob = svc.create_user("Bob", "bob@example.com")
    print(f"Users: {svc.list_users()}")

    orders = OrderService()
    order = orders.create_order(alice["id"], ["widget"], 29.99)
    print(f"Order: {order}")


if __name__ == "__main__":
    main()
