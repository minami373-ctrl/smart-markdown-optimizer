"""商品API（docs/spec.md §4②）。"""

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from db import get_session
from models import Product, StockAdjustmentLog
from services.prior import generate_prior_demand

router = APIRouter(prefix="/api/products", tags=["products"])


#: 商品の種類（docs/spec.md §2.1。models.CATEGORIESと同じ3値）
Category = Literal["弁当・丼", "揚げ物の単品", "軽食・つまみ"]


class ProductOut(BaseModel):
    id: int
    name: str
    category: str
    initial_stock: int
    elasticity: float
    prior_demand: dict
    unit_price: int | None = None


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    #: 種類（docs/spec.md §6）。省略時は「弁当・丼」
    category: Category = "弁当・丼"
    initial_stock: int = Field(gt=0)
    elasticity: float = Field(gt=0)
    #: 平日・晴れ・イベントなしの日、1ステップあたり平均何個売れそうかの目安値（docs/spec.md §5.4）
    base_demand: float = Field(gt=0)
    #: 単価（円）。任意項目（docs/spec.md §6）。シミュレーション画面の推定売上にのみ使う
    unit_price: int | None = Field(default=None, ge=0)

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
        category=p.category,
        initial_stock=p.initial_stock,
        elasticity=p.elasticity,
        prior_demand=json.loads(p.prior_demand),
        unit_price=p.unit_price,
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
        category=body.category,
        initial_stock=body.initial_stock,
        elasticity=body.elasticity,
        prior_demand=json.dumps(prior_demand, ensure_ascii=False),
        unit_price=body.unit_price,
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return _to_out(product)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, body: ProductCreate, session: Session = Depends(get_session)
) -> ProductOut:
    """商品名・種類・初期在庫・値引き感度・基準需要・単価を丸ごと上書きする（部分更新ではない）。
    基準需要から12条件ぶんの事前分布を作り直す（docs/spec.md §4②）。"""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    prior_demand = generate_prior_demand(body.base_demand)
    product.name = body.name
    product.category = body.category
    product.initial_stock = body.initial_stock
    product.elasticity = body.elasticity
    product.prior_demand = json.dumps(prior_demand, ensure_ascii=False)
    product.unit_price = body.unit_price
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


class StockAdjustmentLogOut(BaseModel):
    id: int
    run_id: int
    reason: Literal["opportunity", "overstock"]
    delta: int
    new_initial_stock: int
    created_at: datetime


@router.get("/{product_id}/stock-adjustments", response_model=list[StockAdjustmentLogOut])
def list_stock_adjustments(
    product_id: int, session: Session = Depends(get_session)
) -> list[StockAdjustmentLogOut]:
    """在庫の自動調整履歴（docs/spec.md §5.8）。発生順（created_at昇順）で返す。
    商品削除後もStockAdjustmentLog自体は残すが（履歴は消さない方針）、この画面から
    見る手段は無くなる（商品が存在しなければ404）。"""
    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="商品が見つかりません")

    logs = session.exec(
        select(StockAdjustmentLog)
        .where(StockAdjustmentLog.product_id == product_id)
        # created_atだけだとタイブレークが無い。「連続実行」（docs/spec.md §4①）でPOSTを
        # 間隔を空けず繰り返すと、Windows環境のdatetime.now()の分解能次第で同一runの
        # 複数件が同じcreated_atになりうるため、idを挿入順のタイブレークとして併用する
        .order_by(StockAdjustmentLog.created_at, StockAdjustmentLog.id)
    ).all()
    return [
        StockAdjustmentLogOut(
            id=log.id,
            run_id=log.run_id,
            reason=log.reason,
            delta=log.delta,
            new_initial_stock=log.new_initial_stock,
            created_at=log.created_at,
        )
        for log in logs
    ]
