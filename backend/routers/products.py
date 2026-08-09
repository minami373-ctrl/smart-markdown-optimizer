"""商品API（docs/spec.md §4②）。"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from db import get_session
from models import Product
from services.prior import generate_prior_demand

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductOut(BaseModel):
    id: int
    name: str
    initial_stock: int
    elasticity: float
    prior_demand: dict


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    initial_stock: int = Field(gt=0)
    elasticity: float = Field(gt=0)
    #: 平日・晴れ・イベントなしの日、1ステップあたり平均何個売れそうかの目安値（docs/spec.md §5.4）
    base_demand: float = Field(gt=0)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("商品名を入力してください")
        return stripped


def _to_out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id,
        name=p.name,
        initial_stock=p.initial_stock,
        elasticity=p.elasticity,
        prior_demand=json.loads(p.prior_demand),
    )


@router.get("", response_model=list[ProductOut])
def list_products(session: Session = Depends(get_session)) -> list[ProductOut]:
    products = session.exec(select(Product)).all()
    return [_to_out(p) for p in products]


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductCreate, session: Session = Depends(get_session)
) -> ProductOut:
    prior_demand = generate_prior_demand(body.base_demand)
    product = Product(
        name=body.name,
        initial_stock=body.initial_stock,
        elasticity=body.elasticity,
        prior_demand=json.dumps(prior_demand, ensure_ascii=False),
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return _to_out(product)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, body: ProductCreate, session: Session = Depends(get_session)
) -> ProductOut:
    """商品名・初期在庫・値引き感度・基準需要を丸ごと上書きする（部分更新ではない）。
    基準需要から12条件ぶんの事前分布を作り直す（docs/spec.md §4②）。"""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    prior_demand = generate_prior_demand(body.base_demand)
    product.name = body.name
    product.initial_stock = body.initial_stock
    product.elasticity = body.elasticity
    product.prior_demand = json.dumps(prior_demand, ensure_ascii=False)
    session.add(product)
    session.commit()
    session.refresh(product)
    return _to_out(product)


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, session: Session = Depends(get_session)) -> None:
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")
    # 過去のシミュレーション履歴（PurchaseLog等）は消さない（docs/spec.md §4②）
    session.delete(product)
    session.commit()
