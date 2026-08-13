"""過剰在庫分析API（docs/spec.md §4⑤・§5.6）。`routers/opportunities.py` の鏡像。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from db import get_session
from models import DiscountRecommendation, Product, PurchaseLog, SimulationResult, SimulationRun
from services.overstock import (
    OverstockOccurrence,
    ProductOverstockSummary,
    detect_overstock,
    rank_overstocks,
)

router = APIRouter(prefix="/api/overstock", tags=["overstock"])


class OverstockOut(BaseModel):
    product_id: int
    product_name: str
    occurrence_count: int
    avg_final_remaining: float
    avg_suggested_decrease: float


def _to_out(s: ProductOverstockSummary) -> OverstockOut:
    return OverstockOut(
        product_id=s.product_id,
        product_name=s.product_name,
        occurrence_count=s.occurrence_count,
        avg_final_remaining=s.avg_final_remaining,
        avg_suggested_decrease=s.avg_suggested_decrease,
    )


@router.get("", response_model=list[OverstockOut])
def list_overstocks(session: Session = Depends(get_session)) -> list[OverstockOut]:
    # 現存する商品だけを対象にする（削除済みは初期在庫が分からず判定できないため）
    products = {p.id: p for p in session.exec(select(Product)).all()}
    finished_runs = session.exec(
        select(SimulationRun).where(SimulationRun.status == "finished")
    ).all()

    occurrences_by_product: dict[tuple[int, str], list[OverstockOccurrence]] = {
        (p.id, p.name): [] for p in products.values()
    }

    if not finished_runs:
        return [_to_out(s) for s in rank_overstocks(occurrences_by_product)]

    # run件数ぶんクエリを繰り返さず、IN句で一括取得してからPython側でグルーピングする
    run_ids = [run.id for run in finished_runs]
    all_logs = session.exec(select(PurchaseLog).where(PurchaseLog.run_id.in_(run_ids))).all()
    all_recs = session.exec(
        select(DiscountRecommendation).where(DiscountRecommendation.run_id.in_(run_ids))
    ).all()
    # 各runを実行した時点の初期在庫のスナップショット。Product.initial_stockは
    # 在庫の自動調整（§5.7）でrunを重ねるたびに変わりうるため、現在値ではなくこちらを使う
    all_results = session.exec(
        select(SimulationResult).where(SimulationResult.run_id.in_(run_ids))
    ).all()
    initial_stock_by_run_product: dict[tuple[int, int], int] = {
        (r.run_id, r.product_id): r.initial_stock for r in all_results
    }

    quantities_by_run_product: dict[tuple[int, int], list[int]] = {}
    for log in all_logs:
        quantities_by_run_product.setdefault((log.run_id, log.product_id), []).append(
            log.quantity
        )
    rates_by_run_product: dict[tuple[int, int], list[float]] = {}
    for rec in all_recs:
        rates_by_run_product.setdefault((rec.run_id, rec.product_id), []).append(
            rec.recommended_rate
        )

    for (run_id, product_id), quantities in quantities_by_run_product.items():
        product = products.get(product_id)
        if product is None:
            continue  # 削除済み商品は対象外
        initial_stock = initial_stock_by_run_product.get((run_id, product_id))
        if initial_stock is None:
            continue  # SimulationResultが無ければ判定できない（通常は起こらない）
        rates = rates_by_run_product.get((run_id, product_id), [])
        occurrence = detect_overstock(rates, quantities, initial_stock)
        if occurrence is not None:
            occurrences_by_product[(product.id, product.name)].append(occurrence)

    summaries = rank_overstocks(occurrences_by_product)
    return [_to_out(s) for s in summaries]
