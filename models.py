from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# ---------------- USERS ----------------
class User(BaseModel):
    username: str
    email: EmailStr
    password: str
    created_at: datetime = datetime.utcnow()

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------------- CART ----------------
class CartItem(BaseModel):
    product_id: int
    quantity: int

class Cart(BaseModel):
    user_id: str
    items: List[CartItem]

# ---------------- ORDERS ----------------
class OrderItem(BaseModel):
    product_id: int
    title: str
    price: float
    quantity: int

class Order(BaseModel):
    user_id: str
    items: List[OrderItem]
    total: float
    status: str = "pending"
    created_at: datetime = datetime.utcnow()

# ---------------- JWT TOKENS ----------------
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[str] = None
