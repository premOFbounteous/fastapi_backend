import uuid
from fastapi import FastAPI, HTTPException, Depends, Query
from passlib.context import CryptContext
from db import db
from models import User, LoginRequest, Token, CartItem, OrderItem
from auth import create_access_token, create_refresh_token, get_current_user
from utils import paginate, sort_items
from typing import List, Optional
from typing import Optional
from fastapi import Query
from fastapi import Query, HTTPException
from typing import Optional

app = FastAPI()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------- PRODUCTS ----------------



allowed_sorts = ["price", "rating", "title", "id"]

@app.get("/products")
async def get_products(
    page: int = Query(1, ge=1),                # default page 1
    limit: int = Query(10, ge=1, le=100),      # default limit 10, max 100
    category: Optional[str] = None,
    sort: Optional[str] = None
):
    query = {}
    if category:
        query["category"] = category

    # ----- Sorting -----
    sort_field = "id"  # ✅ Default sort by id
    sort_order = 1

    if sort:
        sort = sort.strip()  # strip accidental spaces/newlines
        if sort.startswith("-"):
            sort_field = sort[1:] or "id"
            sort_order = -1
        else:
            sort_field = sort or "id"

        if sort_field not in allowed_sorts:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort field '{sort_field}'. Allowed: {allowed_sorts}"
            )

    cursor = db["ecommerce"].find(query).sort(sort_field, sort_order)

    total = await db["ecommerce"].count_documents(query)
    total_pages = max((total + limit - 1) // limit, 1)

    # ✅ If user requests a page that doesn't exist → empty result
    if page > total_pages:
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": total_pages,
            "sort": f"{'-' if sort_order==-1 else ''}{sort_field}",
            "products": []
        }

    skip_count = (page - 1) * limit
    cursor = cursor.skip(skip_count).limit(limit)

    products = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])  # Convert ObjectId to string
        products.append(doc)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": total_pages,
        "sort": f"{'-' if sort_order==-1 else ''}{sort_field}",
        "products": products
    }


@app.get("/products/search")
async def search_products(
    search_str: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    query = {
        "$or": [
            {"title": {"$regex": search_str, "$options": "i"}},
            {"description": {"$regex": search_str, "$options": "i"}}
        ]
    }

    total = await db["ecommerce"].count_documents(query)
    total_pages = max((total + limit - 1) // limit, 1)

    if page > total_pages:
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "pages": total_pages,
            "products": []
        }

    skip_count = (page - 1) * limit
    cursor = db["ecommerce"].find(query).skip(skip_count).limit(limit)

    products = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        products.append(doc)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": total_pages,
        "products": products
    }

@app.get("/products/{product_id}")
async def get_product_by_id(product_id: int):
    product = await db["ecommerce"].find_one({"id": product_id})
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    product["_id"] = str(product["_id"])
    return product

@app.get("/categories")
async def get_categories():
    categories = await db["ecommerce"].distinct("category")
    return {"count": len(categories), "categories": categories}

# ---------------- USERS ----------------
@app.post("/users/register")
async def register_user(user: User):
    if await db["users"].find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await db["users"].find_one({"username": user.username}):
        raise HTTPException(status_code=400, detail="Username taken")

    hashed = pwd_context.hash(user.password)
    user_dict = user.dict()
    user_dict["password"] = hashed
    user_dict["user_id"] = str(uuid.uuid4())

    await db["users"].insert_one(user_dict)
    return {"message": "User registered", "user_id": user_dict["user_id"]}

@app.post("/users/login", response_model=Token)
async def login_user(login: LoginRequest):
    user = await db["users"].find_one({"email": login.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not pwd_context.verify(login.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    access = create_access_token({"user_id": user["user_id"]})
    refresh = create_refresh_token({"user_id": user["user_id"]})
    return {"access_token": access, "refresh_token": refresh}

@app.post("/users/refresh", response_model=Token)
async def refresh_token(refresh_token: str):
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(refresh_token, "supersecretkey123", algorithms=["HS256"])
        user_id: str = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        access = create_access_token({"user_id": user_id})
        new_refresh = create_refresh_token({"user_id": user_id})
        return {"access_token": access, "refresh_token": new_refresh}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# ---------------- CART ----------------
@app.post("/cart/add")
async def add_to_cart(item: CartItem, user=Depends(get_current_user)):
    user_id = user["user_id"]

    # ✅ Check if product exists and stock is available
    product = await db["ecommerce"].find_one({"id": item.product_id})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if product["stock"] < item.quantity:
        raise HTTPException(status_code=400, detail=f"Only {product['stock']} items left in stock")

    # ✅ Add item to user's cart
    cart = await db["carts"].find_one({"user_id": user_id})
    if not cart:
        await db["carts"].insert_one({"user_id": user_id, "items": [item.dict()]})
    else:
        updated = False
        for i in cart["items"]:
            if i["product_id"] == item.product_id:
                if product["stock"] < i["quantity"] + item.quantity:
                    raise HTTPException(status_code=400, detail=f"Only {product['stock']} items left in stock")
                i["quantity"] += item.quantity
                updated = True
        if not updated:
            cart["items"].append(item.dict())
        await db["carts"].update_one({"user_id": user_id}, {"$set": {"items": cart["items"]}})
    return {"message": "Item added to cart"}


def serialize_cart(cart: dict):
    """Convert MongoDB cart document into JSON serializable dict."""
    return {
        "_id": str(cart["_id"]),
        "user_id": cart["user_id"],
        "items": [
            {
                "product_id": item["product_id"],
                "quantity": item["quantity"]
            }
            for item in cart.get("items", [])
        ]
    }

@app.get("/cart")
async def get_cart(user: dict = Depends(get_current_user)):
    user_id = user["user_id"]
    cart = await db["carts"].find_one({"user_id": str(user_id)})
    if not cart:
        return {"items": []}
    return serialize_cart(cart)

@app.post("/cart/checkout")
async def checkout_cart(user=Depends(get_current_user)):
    user_id = user["user_id"]
    cart = await db["carts"].find_one({"user_id": user_id})
    if not cart or len(cart["items"]) == 0:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    order_items = []
    total = 0

    for c in cart["items"]:
        product = await db["ecommerce"].find_one({"id": c["product_id"]})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {c['product_id']} not found")

        if product["stock"] < c["quantity"]:
            raise HTTPException(status_code=400, detail=f"Only {product['stock']} left for {product['title']}")

        # ✅ Deduct stock
        await db["ecommerce"].update_one(
            {"id": c["product_id"]},
            {"$inc": {"stock": -c["quantity"]}}
        )

        order_items.append({
            "product_id": product["id"],
            "title": product["title"],
            "price": product["price"],
            "quantity": c["quantity"]
        })
        total += product["price"] * c["quantity"]
    
    order = {"user_id": user_id, "items": order_items, "total": total, "status": "pending"}
    await db["orders"].insert_one(order)
    
    # ✅ Empty cart
    await db["carts"].update_one({"user_id": user_id}, {"$set": {"items": []}})
    
    return {"message": "Order placed successfully", "total": total, "items": order_items}


# ---------------- ORDERS ----------------
@app.get("/orders")
async def get_orders(user=Depends(get_current_user)):
    orders = []
    cursor = db["orders"].find({"user_id": user["user_id"]})
    async for o in cursor:
        o["_id"] = str(o["_id"])
        orders.append(o)
    return {"count": len(orders), "orders": orders}
