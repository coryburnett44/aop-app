from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import base64
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")
PAYPAL_BASE = (
    "https://api-m.sandbox.paypal.com"
    if PAYPAL_MODE == "sandbox"
    else "https://api-m.paypal.com"
)

app = FastAPI()
api_router = APIRouter(prefix="/api")


# ---------- Models ----------
class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str
    quantity: float = 1
    rate: float = 0


class InvoiceBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_number: str
    issue_date: str  # ISO date string yyyy-mm-dd
    due_date: str
    customer_name: str
    customer_email: Optional[str] = ""
    customer_address: Optional[str] = ""
    items: List[LineItem] = []
    tax_rate: float = 0  # percentage
    discount: float = 0  # absolute USD amount
    notes: Optional[str] = ""
    terms: Optional[str] = ""
    currency: str = "USD"


class InvoiceCreate(InvoiceBase):
    pass


class Invoice(InvoiceBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: Literal["draft", "sent", "paid", "overdue"] = "draft"
    paypal_order_id: Optional[str] = ""
    paypal_capture_id: Optional[str] = ""
    paid_at: Optional[str] = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    items: Optional[List[LineItem]] = None
    tax_rate: Optional[float] = None
    discount: Optional[float] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    status: Optional[Literal["draft", "sent", "paid", "overdue"]] = None


# ---------- Helpers ----------
def calculate_totals(invoice: dict) -> dict:
    items = invoice.get("items", [])
    subtotal = sum(float(i.get("quantity", 0)) * float(i.get("rate", 0)) for i in items)
    tax_rate = float(invoice.get("tax_rate", 0) or 0)
    discount = float(invoice.get("discount", 0) or 0)
    tax = round(subtotal * (tax_rate / 100), 2)
    total = round(subtotal - discount + tax, 2)
    return {
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "discount": round(discount, 2),
        "total": max(total, 0),
    }


def serialize_invoice(doc: dict) -> dict:
    doc.pop("_id", None)
    totals = calculate_totals(doc)
    return {**doc, **totals}


async def get_paypal_access_token() -> str:
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        raise HTTPException(
            status_code=503,
            detail="PayPal credentials not configured. Set PAYPAL_CLIENT_ID and PAYPAL_SECRET in backend/.env",
        )
    auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"PayPal auth failed: {r.text}")
    return r.json()["access_token"]


# ---------- Routes ----------
@api_router.get("/")
async def root():
    return {"message": "Invoice API", "paypal_mode": PAYPAL_MODE}


@api_router.get("/config/paypal")
async def paypal_config():
    return {
        "client_id": PAYPAL_CLIENT_ID,
        "mode": PAYPAL_MODE,
        "configured": bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET),
    }


@api_router.post("/invoices")
async def create_invoice(payload: InvoiceCreate):
    invoice = Invoice(**payload.model_dump())
    doc = invoice.model_dump()
    await db.invoices.insert_one(doc)
    return serialize_invoice(doc)


@api_router.get("/invoices")
async def list_invoices():
    docs = await db.invoices.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [serialize_invoice(d) for d in docs]


@api_router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str):
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return serialize_invoice(doc)


@api_router.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No updates provided")
    if "items" in update:
        update["items"] = [
            i if isinstance(i, dict) else i.model_dump() for i in update["items"]
        ]
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.invoices.update_one({"id": invoice_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return serialize_invoice(doc)


@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    result = await db.invoices.delete_one({"id": invoice_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"deleted": True, "id": invoice_id}


# ---------- PayPal ----------
@api_router.post("/invoices/{invoice_id}/paypal/create-order")
async def create_paypal_order(invoice_id: str):
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if doc.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Invoice already paid")

    totals = calculate_totals(doc)
    if totals["total"] <= 0:
        raise HTTPException(status_code=400, detail="Invoice total must be > 0")

    token = await get_paypal_access_token()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": doc["id"],
                "description": f"Invoice {doc.get('invoice_number','')} - Cory Burnett / Overflow Investment Legacy",
                "amount": {
                    "currency_code": doc.get("currency", "USD"),
                    "value": f"{totals['total']:.2f}",
                },
            }
        ],
    }
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if r.status_code not in (200, 201):
        raise HTTPException(
            status_code=502, detail=f"PayPal order create failed: {r.text}"
        )
    order = r.json()
    await db.invoices.update_one(
        {"id": invoice_id},
        {
            "$set": {
                "paypal_order_id": order["id"],
                "status": doc.get("status") if doc.get("status") == "paid" else "sent",
            }
        },
    )
    return {"id": order["id"]}


@api_router.post("/invoices/{invoice_id}/paypal/capture/{order_id}")
async def capture_paypal_order(invoice_id: str, order_id: str):
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice not found")
    token = await get_paypal_access_token()
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    if r.status_code not in (200, 201):
        raise HTTPException(
            status_code=502, detail=f"PayPal capture failed: {r.text}"
        )
    capture = r.json()
    capture_id = ""
    try:
        capture_id = capture["purchase_units"][0]["payments"]["captures"][0]["id"]
    except Exception:
        pass
    await db.invoices.update_one(
        {"id": invoice_id},
        {
            "$set": {
                "status": "paid",
                "paypal_capture_id": capture_id,
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"status": "paid", "capture": capture}


# Mark invoice as paid manually (for non-PayPal payments or testing)
@api_router.post("/invoices/{invoice_id}/mark-paid")
async def mark_paid(invoice_id: str):
    result = await db.invoices.update_one(
        {"id": invoice_id},
        {
            "$set": {
                "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    doc = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return serialize_invoice(doc)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
