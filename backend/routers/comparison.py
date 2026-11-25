"""固定スケジュール値引きとの比較API（docs/spec.md §4⑥・§5.9）。

POST /api/compare … 動的値引きと固定スケジュール値引きを同じ乱数シードで両方実行し、
                     結果を返す。DBには何も保存しない（一過性の比較のため）。
"""

import json
import random
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from db import get_session
from models import Product
from services.schedule_comparison import (
    FIXED_SCHEDULE_30_STEP,
    FIXED_SCHEDULE_50_STEP,
    run_fixed_schedule_simulation,
)
from services.simulation import ProductInput, condition_key, run_simulation

router = APIRouter(prefix="/api/compare", tags=["comparison"])


class ComparisonCreate(BaseModel):
    weather: Literal["晴れ", "曇り", "雨"]
    day_type: Literal["平日", "休日"]
    has_event: bool
    #: 長期休みの日か（docs/spec.md §5.13）
    is_long_vacation: bool = False
    #: 動的値引き側にのみ使う。固定スケジュール側は目標廃棄率という概念を持たない（docs/spec.md §5.9）
    target_waste_rate: float = Field(ge=0.0, le=0.10)
    #: 動的値引き側のズバリ引きの承認の遅れ（docs/spec.md §5.11。POST /api/simulationsと同じ）
    approval_delay_steps: int = Field(default=0, ge=0, le=3)
    #: 「お客さんが待つ」効果を固定スケジュール側に入れるか（docs/spec.md §5.12。仮定なので選べる）
    customer_anticipation: bool = False


class ScheduleStepOut(BaseModel):
    step: int
    quantity: int
    remaining_stock: int
    recommended_rate: float


class ComparisonProductOut(BaseModel):
    product_id: int
    product_name: str
    unit_price: int | None
    dynamic_steps: list[ScheduleStepOut]
    dynamic_final_waste_rate: float
    fixed_steps: list[ScheduleStepOut]
    fixed_final_waste_rate: float


class ComparisonOut(BaseModel):
    products: list[ComparisonProductOut]
    #: 画面のグラフに縦線を引くための固定スケジュールの切り替わりステップ
    fixed_schedule_30_step: int
    fixed_schedule_50_step: int


def _load_all_products(session: Session) -> list[Product]:
    """routers/simulations.pyの_load_active_productsと同じ「商品が1件も無い」チェック。
    0在庫の商品自体は許容する（0在庫フィルタは呼び出し側でrun_simulationのactive_products
    フィルタと同じタイミングで行う。§5.9「初期在庫0の商品は結果から除外する」）。
    ここで0在庫を弾くと、商品は存在するが全商品が0在庫のときに
    `POST /api/simulations`（200・空配列）と違って500になってしまう不整合があった。"""
    products = list(session.exec(select(Product)).all())
    if not products:
        raise HTTPException(
            status_code=500, detail="商品が登録されていません（seed投入が必要です）"
        )
    return products


def _build_inputs(products: list[Product], key: str) -> list[ProductInput]:
    """商品ごとに条件キーの事前分布を引く（routers/simulations.pyの同名関数と同じ考え方）。"""
    inputs: list[ProductInput] = []
    for p in products:
        prior = json.loads(p.prior_demand)
        combo = prior.get(key)
        if combo is None:
            raise HTTPException(
                status_code=500, detail=f"{p.name} に条件 {key} の事前分布がありません"
            )
        inputs.append(
            ProductInput(
                product_id=p.id,
                name=p.name,
                initial_stock=p.initial_stock,
                elasticity=p.elasticity,
                prior_alpha=combo["alpha"],
                prior_beta=combo["beta"],
                # お客さんの本当の需要（§5.14）。無ければ事前分布の平均
                true_rate=(json.loads(p.true_demand).get(key) if p.true_demand else None),
            )
        )
    return inputs


def _steps_out(steps: list) -> list[ScheduleStepOut]:
    """services.simulation.ProductStepResult / services.schedule_comparison.ScheduleStepResult
    のどちらでも使える（step・quantity・remaining_stock・recommended_rateの4属性だけを見るため）。"""
    return [
        ScheduleStepOut(
            step=s.step,
            quantity=s.quantity,
            remaining_stock=s.remaining_stock,
            # 動的値引き側は、モニターに実際に出ている値引き（承認済み。docs/spec.md §5.11）を返す。
            # 固定スケジュール側（ScheduleStepResult）はapplied_rateを持たないのでそのまま
            recommended_rate=getattr(s, "applied_rate", s.recommended_rate),
        )
        for s in steps
    ]


@router.post("", response_model=ComparisonOut)
def compare_schedules(
    body: ComparisonCreate, session: Session = Depends(get_session)
) -> ComparisonOut:
    products = _load_all_products(session)
    key = condition_key(body.weather, body.day_type, body.has_event, body.is_long_vacation)
    inputs = _build_inputs(products, key)

    # DBに保存しない一過性の比較のため、SimulationRun.idではなくその場で乱数シードを選ぶ
    # （動的値引き・固定スケジュールの両方が同じシードを使うことで、同じ「その日の運」から
    # 出発した別のポリシーとして比較できる。docs/spec.md §5.9）
    seed = random.randint(1, 1_000_000)

    dynamic_outcome = run_simulation(
        inputs,
        target_waste_rate=body.target_waste_rate,
        seed=seed,
        approval_delay_steps=body.approval_delay_steps,
    )
    dynamic_finals = {f.product_id: f for f in dynamic_outcome.finals}
    dynamic_steps_by_product: dict[int, list] = {}
    for s in dynamic_outcome.steps:
        dynamic_steps_by_product.setdefault(s.product_id, []).append(s)

    names = {p.id: p.name for p in products}
    unit_prices = {p.id: p.unit_price for p in products}

    result_products: list[ComparisonProductOut] = []
    for inp in inputs:
        if inp.initial_stock <= 0:
            # 初期在庫0の商品は結果から除外する（docs/spec.md §5.9。run_simulationの
            # active_productsフィルタと同じ扱い。0除算を避けるためでもある）
            continue
        fixed_outcome = run_fixed_schedule_simulation(
            inp, seed=seed, customer_anticipation=body.customer_anticipation
        )
        dynamic_final = dynamic_finals.get(inp.product_id)
        result_products.append(
            ComparisonProductOut(
                product_id=inp.product_id,
                product_name=names[inp.product_id],
                unit_price=unit_prices[inp.product_id],
                dynamic_steps=_steps_out(
                    sorted(
                        dynamic_steps_by_product.get(inp.product_id, []),
                        key=lambda s: s.step,
                    )
                ),
                dynamic_final_waste_rate=(
                    dynamic_final.final_waste_rate if dynamic_final is not None else 0.0
                ),
                fixed_steps=_steps_out(fixed_outcome.steps),
                fixed_final_waste_rate=fixed_outcome.final_waste_rate,
            )
        )

    return ComparisonOut(
        products=result_products,
        fixed_schedule_30_step=FIXED_SCHEDULE_30_STEP,
        fixed_schedule_50_step=FIXED_SCHEDULE_50_STEP,
    )
