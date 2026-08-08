"""商品API（docs/spec.md §4②）。"""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from db import get_session
from models import Product

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductOut(BaseModel):
    id: int
    name: str
    initial_stock: int
    elasticity: float
    prior_demand: dict


@router.get("", response_model=list[ProductOut])
def list_products(session: Session = Depends(get_session)) -> list[ProductOut]:
    products = session.exec(select(Product)).all()
    return [
        ProductOut(
            id=p.id,
            name=p.name,
            initial_stock=p.initial_stock,
            elasticity=p.elasticity,
            prior_demand=json.loads(p.prior_demand),
        )
        for p in products
    ]
