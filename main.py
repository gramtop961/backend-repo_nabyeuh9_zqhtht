import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, Category, Review, Cart, CartItem, Order, PackagingGuide, About, Notification

app = FastAPI(title="Delicassy API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "Delicassy", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:120]}"
    return response


# Helpers
class IdModel(BaseModel):
    id: str

def to_obj_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid id")


# Catalog Endpoints
@app.get("/api/categories", response_model=List[Category])
def list_categories():
    return get_documents("category", {})


@app.post("/api/categories")
def create_category(category: Category):
    new_id = create_document("category", category)
    return {"id": new_id}


@app.get("/api/products", response_model=List[Product])
def list_products(category: Optional[str] = None, q: Optional[str] = None):
    filter_q = {}
    if category:
        filter_q["category"] = category
    if q:
        filter_q["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}}
        ]
    return get_documents("product", filter_q)


@app.post("/api/products")
def create_product(product: Product):
    new_id = create_document("product", product)
    return {"id": new_id}


@app.get("/api/products/{slug}")
def get_product_by_slug(slug: str):
    docs = get_documents("product", {"slug": slug}, limit=1)
    if not docs:
        raise HTTPException(status_code=404, detail="Not found")
    product = docs[0]
    product["reviews"] = get_documents("review", {"product_id": str(product.get("_id"))})
    return product


@app.post("/api/reviews")
def add_review(review: Review):
    # Ensure product exists
    if not get_documents("product", {"_id": ObjectId(review.product_id)}, limit=1):
        raise HTTPException(status_code=404, detail="Product not found")
    new_id = create_document("review", review)
    return {"id": new_id}


# Cart Endpoints (session-based)
@app.post("/api/cart/init")
def init_cart(cart: Cart):
    new_id = create_document("cart", cart)
    return {"id": new_id}


@app.get("/api/cart/{cart_id}")
def get_cart(cart_id: str):
    docs = get_documents("cart", {"_id": to_obj_id(cart_id)}, limit=1)
    if not docs:
        raise HTTPException(status_code=404, detail="Cart not found")
    return docs[0]


class UpdateCart(BaseModel):
    items: List[CartItem]

@app.put("/api/cart/{cart_id}")
def update_cart(cart_id: str, body: UpdateCart):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    res = db["cart"].update_one({"_id": to_obj_id(cart_id)}, {"$set": {"items": [i.model_dump() for i in body.items]}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cart not found")
    return {"ok": True}


# Checkout / Orders
class CheckoutRequest(BaseModel):
    cart_id: str
    shipping_address: dict
    payment: dict
    insured: bool = True
    premium_packaging: bool = False

@app.post("/api/checkout")
def checkout(req: CheckoutRequest):
    # Pull cart
    cart_docs = get_documents("cart", {"_id": to_obj_id(req.cart_id)}, limit=1)
    if not cart_docs:
        raise HTTPException(status_code=404, detail="Cart not found")
    cart = cart_docs[0]

    # Compute totals and insurance
    items = cart.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    product_ids = [ObjectId(i["product_id"]) for i in items]
    products = list(db["product"].find({"_id": {"$in": product_ids}}))
    price_map = {str(p["_id"]): p["price"] for p in products}
    fragility_map = {str(p["_id"]): p.get("fragility_rating", 3) for p in products}

    subtotal = sum(price_map.get(it["product_id"], 0) * it.get("quantity", 1) for it in items)
    # Insurance and shipping are affected by fragility
    avg_fragility = sum(fragility_map.get(it["product_id"], 3) for it in items) / len(items)
    insurance = round(subtotal * (0.02 + 0.02 * (avg_fragility - 1)), 2) if req.insured else 0
    premium_packaging_fee = 14.0 if req.premium_packaging else 0
    shipping = round(9.0 + (avg_fragility - 1) * 2.5, 2)

    total = round(subtotal + shipping + insurance + premium_packaging_fee, 2)

    order = Order(
        items=[CartItem(**i) for i in items],
        amount_subtotal=subtotal,
        amount_shipping=shipping,
        amount_insurance=insurance,
        amount_total=total,
        shipping_address=req.shipping_address,  # type: ignore
        payment=req.payment,  # type: ignore
        shipping={"insured": req.insured, "premium_packaging": req.premium_packaging},  # type: ignore
    )
    order_id = create_document("order", order)

    # Basic stock decrement (atomic per item)
    for it in items:
        db["product"].update_one({"_id": ObjectId(it["product_id"])}, {"$inc": {"stock": -it.get("quantity", 1)}})

    return {"order_id": order_id, "amount_total": total, "status": "created"}


# Packaging & About
@app.get("/api/packaging", response_model=List[PackagingGuide])
def get_packaging_guides():
    return get_documents("packagingguide", {})


@app.post("/api/packaging")
def create_packaging_guide(pg: PackagingGuide):
    new_id = create_document("packagingguide", pg)
    return {"id": new_id}


@app.get("/api/about")
def get_about():
    docs = get_documents("about", {}, limit=1)
    if docs:
        return docs[0]
    return {
        "headline": "Delicassy — 25 Years of Elegant Craftsmanship",
        "story": "For a quarter-century, Delicassy has curated and safely delivered delicate, handcrafted treasures to collectors worldwide.",
        "years": 25,
        "badges": [
            "Trusted handling for 25 years",
            "Expert packaging for fragile goods",
            "Curated artisan collections"
        ]
    }


# Notifications
@app.get("/api/notifications/{user_id}", response_model=List[Notification])
def get_notifications(user_id: str):
    return get_documents("notification", {"user_id": user_id})


@app.post("/api/notifications")
def create_notification(note: Notification):
    new_id = create_document("notification", note)
    return {"id": new_id}


# Schema endpoint for tooling
@app.get("/schema")
def get_schema():
    from schemas import __dict__ as schema_dict
    # Simple reflection: list class names defined here that subclass BaseModel
    models = {}
    for k, v in schema_dict.items():
        try:
            if isinstance(v, type) and issubclass(v, BaseModel):
                models[k] = v.schema()  # type: ignore
        except Exception:
            continue
    return models


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
