"""シミュレーションAPI（docs/spec.md §4①③・§5.2）。

POST   /api/simulations       … 実行（条件を受け取り、即座に全40ステップぶん計算して返す）
GET    /api/simulations       … 履歴一覧（新しい順）
GET    /api/simulations/{id}  … 履歴1件の詳細（値引き率の推移グラフ用）
"""

import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from db import get_session
from models import (
    DiscountRecommendation,
    Product,
    PurchaseLog,
    SimulationResult,
    SimulationRun,
    StockAdjustmentLog,
)
from services.simulation import ProductInput, condition_key, run_simulation
from services.stock_adjustment import compute_stock_adjustment

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


class SimulationCreate(BaseModel):
    weather: Literal["晴れ", "曇り", "雨"]
    day_type: Literal["平日", "休日"]
    has_event: bool
    target_waste_rate: float = Field(ge=0.0, le=0.10)


class StepOut(BaseModel):
    product_id: int
    step: int
    quantity: int
    # 商品が削除済みで初期在庫が分からない場合は null（docs/spec.md §4②）
    remaining_stock: int | None
    recommended_rate: float
    posterior_mean: float | None = None
    is_new_recommendation: bool = False
    # 需要率の事後分布パラメータ（画面で確率密度曲線を描く用）。
    # ライブ実行直後（POST応答）だけ入る。履歴の再構築（GET）では持たないため null
    posterior_alpha: float | None = None
    posterior_beta: float | None = None


class FinalOut(BaseModel):
    product_id: int
    product_name: str
    final_waste_rate: float
    achieved: bool


class StockAdjustmentOut(BaseModel):
    """在庫の自動調整通知（docs/spec.md §5.7）。POSTのその場限りの通知で、履歴には残さない
    （GET系のレスポンスでは常に空配列。DBに保存し直さないため）。"""

    product_id: int
    product_name: str
    delta: int  # 正なら増加、負なら減少
    new_initial_stock: int


class SimulationSummary(BaseModel):
    id: int
    weather: str
    day_type: str
    has_event: bool
    target_waste_rate: float
    status: str
    started_at: datetime
    finished_at: datetime | None
    finals: list[FinalOut]
    stock_adjustments: list[StockAdjustmentOut] = []


class SimulationDetail(SimulationSummary):
    steps: list[StepOut]


def _load_active_products(session: Session) -> list[Product]:
    products = list(session.exec(select(Product)).all())
    if not products:
        raise HTTPException(
            status_code=500, detail="商品が登録されていません（seed投入が必要です）"
        )
    return products


def _finals_out(results: list, names: dict[int, str]) -> list[FinalOut]:
    """SimulationResult / services.simulation.ProductFinalResult のどちらでも使える
    （product_id・final_waste_rate・achieved の3属性だけを見るため）。"""
    return [
        FinalOut(
            product_id=r.product_id,
            product_name=names.get(r.product_id, "?"),
            final_waste_rate=r.final_waste_rate,
            achieved=r.achieved,
        )
        for r in results
    ]


def _build_inputs(products: list[Product], key: str) -> list[ProductInput]:
    """商品ごとに条件キーの事前分布を引く。1つでも欠けていたら例外を投げる
    （DBへの書き込みより前に呼ぶこと。壊れた SimulationRun を残さないため）。"""
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
            )
        )
    return inputs


@router.post("", response_model=SimulationDetail)
def create_simulation(
    body: SimulationCreate, session: Session = Depends(get_session)
) -> SimulationDetail:
    products = _load_active_products(session)
    # このrunで実際に使う初期在庫のスナップショット（在庫の自動調整・§5.7で後から
    # product.initial_stockが書き換わっても、SimulationResultにはこの回の実行当時の値を残す）
    initial_stock_snapshot = {p.id: p.initial_stock for p in products}

    # 先に事前分布を検証する。ここで失敗しても SimulationRun はまだDBに存在しないので、
    # 「running のまま完了しない孤立レコード」が履歴に残らない
    key = condition_key(body.weather, body.day_type, body.has_event)
    inputs = _build_inputs(products, key)

    run = SimulationRun(
        weather=body.weather,
        day_type=body.day_type,
        has_event=body.has_event,
        target_waste_rate=body.target_waste_rate,
        status="running",
        started_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    # 乱数シードは SimulationRun.id から決定的に導出する（docs/spec.md §5.2）
    outcome = run_simulation(inputs, target_waste_rate=body.target_waste_rate, seed=run.id)

    for s in outcome.steps:
        session.add(
            PurchaseLog(run_id=run.id, product_id=s.product_id, step=s.step, quantity=s.quantity)
        )
        if s.is_new_recommendation:
            session.add(
                DiscountRecommendation(
                    run_id=run.id,
                    product_id=s.product_id,
                    step=s.step,
                    recommended_rate=s.recommended_rate,
                    posterior_mean=s.posterior_mean,
                )
            )
    for f in outcome.finals:
        session.add(
            SimulationResult(
                run_id=run.id,
                product_id=f.product_id,
                final_waste_rate=f.final_waste_rate,
                achieved=f.achieved,
                initial_stock=initial_stock_snapshot[f.product_id],
            )
        )

    # 学習の継続（docs/spec.md §2「学習の継続」・§5.2 step4）：終了時点の事後分布を、
    # 実行した条件キーに対応する事前分布へ書き戻す。他の11条件のエントリは変更しない
    products_by_id = {p.id: p for p in products}
    stock_adjustments: list[StockAdjustmentOut] = []
    # StockAdjustmentLog.created_atとrun.finished_atを同一時刻にそろえる（§5.8）
    finished_at = datetime.now()
    for f in outcome.finals:
        product = products_by_id.get(f.product_id)
        if product is None:
            continue
        prior = json.loads(product.prior_demand)
        prior[key] = {"alpha": f.final_alpha, "beta": f.final_beta}
        product.prior_demand = json.dumps(prior, ensure_ascii=False)

        # 在庫の自動調整（docs/spec.md §5.7）：履歴全体の集計（/opportunities・/overstock）とは
        # 別に、その回だけの結果を見て早期完売なら増やし、売れ残りなら減らす
        product_steps = [s for s in outcome.steps if s.product_id == f.product_id]
        log_steps = [(s.step, s.quantity) for s in product_steps]
        recommendation_steps = [
            (s.step, s.recommended_rate) for s in product_steps if s.is_new_recommendation
        ]
        adjustment = compute_stock_adjustment(
            product.initial_stock, log_steps, recommendation_steps
        )
        if adjustment is not None:
            product.initial_stock = adjustment.new_initial_stock
            stock_adjustments.append(
                StockAdjustmentOut(
                    product_id=product.id,
                    product_name=product.name,
                    delta=adjustment.delta,
                    new_initial_stock=adjustment.new_initial_stock,
                )
            )
            # 在庫調整履歴（docs/spec.md §5.8）：POSTのその場限りの通知（stock_adjustments）とは別に、
            # 「どう変わってきたか」を後から追えるよう1行残す
            session.add(
                StockAdjustmentLog(
                    run_id=run.id,
                    product_id=product.id,
                    reason=adjustment.reason,
                    delta=adjustment.delta,
                    new_initial_stock=adjustment.new_initial_stock,
                    created_at=finished_at,
                )
            )

        session.add(product)

    run.status = "finished"
    run.finished_at = finished_at
    session.add(run)
    session.commit()
    session.refresh(run)

    names = {p.id: p.name for p in products}
    return SimulationDetail(
        id=run.id,
        weather=run.weather,
        day_type=run.day_type,
        has_event=run.has_event,
        target_waste_rate=run.target_waste_rate,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        finals=_finals_out(outcome.finals, names),
        stock_adjustments=stock_adjustments,
        # 生成直後は計算済みの全ステップをそのまま返す（フロントが0.5秒間隔で再生する）
        steps=[
            StepOut(
                product_id=s.product_id,
                step=s.step,
                quantity=s.quantity,
                remaining_stock=s.remaining_stock,
                recommended_rate=s.recommended_rate,
                posterior_mean=s.posterior_mean,
                is_new_recommendation=s.is_new_recommendation,
                posterior_alpha=s.posterior_alpha,
                posterior_beta=s.posterior_beta,
            )
            for s in outcome.steps
        ],
    )


@router.get("", response_model=list[SimulationSummary])
def list_simulations(session: Session = Depends(get_session)) -> list[SimulationSummary]:
    runs = session.exec(select(SimulationRun).order_by(SimulationRun.started_at.desc())).all()
    names = {p.id: p.name for p in session.exec(select(Product)).all()}
    all_results = session.exec(select(SimulationResult)).all()
    results_by_run: dict[int, list[SimulationResult]] = {}
    for r in all_results:
        results_by_run.setdefault(r.run_id, []).append(r)

    return [
        SimulationSummary(
            id=r.id,
            weather=r.weather,
            day_type=r.day_type,
            has_event=r.has_event,
            target_waste_rate=r.target_waste_rate,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            finals=_finals_out(results_by_run.get(r.id, []), names),
        )
        for r in runs
    ]


@router.get("/{run_id}", response_model=SimulationDetail)
def get_simulation(run_id: int, session: Session = Depends(get_session)) -> SimulationDetail:
    run = session.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="シミュレーションが見つかりません")

    products = list(session.exec(select(Product)).all())
    existing_product_ids = {p.id for p in products}

    results = session.exec(
        select(SimulationResult).where(SimulationResult.run_id == run_id)
    ).all()
    # このrun実行当時の初期在庫のスナップショットを使う（Product.initial_stockは在庫の自動調整・
    # §5.7で以後の実行のたびに変わりうるため、現在値ではなくこのrunのSimulationResultに
    # 保存された値を使う。商品が削除済みの場合は従来どおり初期在庫が分からずnullのまま・§4②）
    initial_stock = {
        r.product_id: r.initial_stock for r in results if r.product_id in existing_product_ids
    }

    logs = session.exec(
        select(PurchaseLog)
        .where(PurchaseLog.run_id == run_id)
        .order_by(PurchaseLog.product_id, PurchaseLog.step)
    ).all()
    recs = session.exec(
        select(DiscountRecommendation)
        .where(DiscountRecommendation.run_id == run_id)
        .order_by(DiscountRecommendation.product_id, DiscountRecommendation.step)
    ).all()

    # 値引き率は変化した時点しか記録していないので、ステップごとにフォワードフィルする
    rec_by_product: dict[int, list[DiscountRecommendation]] = {}
    for r in recs:
        rec_by_product.setdefault(r.product_id, []).append(r)

    steps: list[StepOut] = []
    remaining_by_product: dict[int, int] = dict(initial_stock)
    current_rate: dict[int, float] = {}
    rec_index: dict[int, int] = {}

    for log in logs:
        # 商品が削除済みだと initial_stock に無いので、在庫は追跡できない（null のまま）
        if log.product_id in remaining_by_product:
            remaining_by_product[log.product_id] -= log.quantity
        remaining_stock = remaining_by_product.get(log.product_id)

        product_recs = rec_by_product.get(log.product_id, [])
        idx = rec_index.get(log.product_id, 0)
        is_new = False
        while idx < len(product_recs) and product_recs[idx].step == log.step:
            current_rate[log.product_id] = product_recs[idx].recommended_rate
            is_new = True
            idx += 1
        rec_index[log.product_id] = idx

        steps.append(
            StepOut(
                product_id=log.product_id,
                step=log.step,
                quantity=log.quantity,
                remaining_stock=remaining_stock,
                recommended_rate=current_rate.get(log.product_id, 0.0),
                posterior_mean=None,
                is_new_recommendation=is_new,
            )
        )

    # POST /api/simulations と同じ「ステップ優先」の並びに揃える
    # （フロントの再生ロジックをどちらの応答にも使い回せるようにするため）
    steps.sort(key=lambda s: (s.step, s.product_id))

    names = {p.id: p.name for p in products}

    return SimulationDetail(
        id=run.id,
        weather=run.weather,
        day_type=run.day_type,
        has_event=run.has_event,
        target_waste_rate=run.target_waste_rate,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        finals=_finals_out(results, names),
        steps=steps,
    )
