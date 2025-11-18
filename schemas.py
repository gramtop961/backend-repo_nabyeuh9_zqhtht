"""
Database Schemas for Delicassy

Each Pydantic model represents a MongoDB collection (collection name = class name lowercased).
These schemas are used for validation in API endpoints and exposed via GET /schema for tooling.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime

# Core domain schemas

class Category(BaseModel):
    name: str = Field(..., description="Display name of the category")
    slug: str = Field(..., description="URL-friendly identifier")
    description: Optional[str] = Field(None, description="SEO-friendly description")
    icon: Optional[str] = Field(None, description="Icon name for UI")

class ProductImage(BaseModel):
    url: HttpUrl
    alt: Optional[str] = None

class Product(BaseModel):
    title: str
    slug: str
    description: str
    price: float = Field(..., ge=0)
    category: str = Field(..., description="Category slug")
    stock: int = Field(..., ge=0)
    fragility_rating: int = Field(..., ge=1, le=5, description="1 (sturdy) to 5 (ultra-fragile)")
    handling_instructions: Optional[str] = None
    assurance_badge: bool = Field(True, description="Shows 25-year heritage badge")
    images: List[ProductImage] = Field(default_factory=list)
    seo_keywords: Optional[List[str]] = None

class Review(BaseModel):
    product_id: str = Field(..., description="MongoDB ObjectId as string")
    user_name: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None

class User(BaseModel):
    name: str
    email: str
    password_hash: Optional[str] = None
    language: Optional[str] = Field("en", description="Language code, e.g., en, fr, es")
    dark_mode: bool = False

class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(..., ge=1)

class Cart(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = Field(None, description="Anonymous session identifier")
    items: List[CartItem] = Field(default_factory=list)

class Address(BaseModel):
    full_name: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    postal_code: str
    country: str
    phone: Optional[str] = None

class PaymentMethod(BaseModel):
    method: Literal["card", "paypal", "apple_pay", "google_pay", "bnpl"]
    token: Optional[str] = Field(None, description="Opaque token from payment provider")
    last4: Optional[str] = None

class ShippingOption(BaseModel):
    insured: bool = True
    premium_packaging: bool = False

class Order(BaseModel):
    user_id: Optional[str] = None
    cart_id: Optional[str] = None
    items: List[CartItem]
    amount_subtotal: float = Field(..., ge=0)
    amount_shipping: float = Field(..., ge=0)
    amount_insurance: float = Field(..., ge=0)
    amount_total: float = Field(..., ge=0)
    shipping_address: Address
    payment: PaymentMethod
    shipping: ShippingOption
    status: Literal["created", "paid", "packaging", "shipped", "delivered"] = "created"
    estimated_delivery: Optional[str] = None

class PackagingGuide(BaseModel):
    title: str
    content_md: str = Field(..., description="Markdown content for packaging/safety")
    media: Optional[List[str]] = Field(None, description="List of video/image URLs")

class Notification(BaseModel):
    user_id: str
    kind: Literal["order_update", "packaging", "announcement", "restock"]
    title: str
    body: str
    read: bool = False

class Testimonial(BaseModel):
    author: str
    quote: str

class About(BaseModel):
    headline: str
    story: str
    years: int = 25
    badges: List[str] = Field(default_factory=lambda: [
        "Trusted handling for 25 years",
        "Expert packaging for fragile goods",
        "Curated artisan collections"
    ])
    testimonials: Optional[List[Testimonial]] = None

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints for the viewer, but the app uses specific endpoints.
