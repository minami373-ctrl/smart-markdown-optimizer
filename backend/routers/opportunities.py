"""機会損失分析API（docs/spec.md §4④・§5.5）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from db import get_session
from models import DiscountRecommendation, Product, PurchaseLog, SimulationRun
from services.opportunity import (
    OpportunityOccurrence,
    ProductOpportunitySummary,
    build_step_records,
    detect_opportunity,
    rank_opportunities,
)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


class OpportunityOut(BaseModel):
    product_id: int
    product_name: str
    occurrence_count: int
    avg_sellout_step: float
    avg_suggested_increase: float


def _to_out(s: ProductOpportunitySummary) -> OpportunityOut:
    return OpportunityOut(
        product_id=s.product_id,
        product_name=s.product_name,
        occurrence_count=s.occurrence_count,
        avg_sellout_step=s.avg_sellout_step,
        avg_suggested_increase=s.avg_suggested_increase,
    )


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(session: Session = Depends(get_session)) -> list[OpportunityOut]:
    # 現存する商品だけを対象にする（削除済みは初期在庫が分からず判定できないため）
    products = {p.id: p for p in session.exec(select(Product)).all()}
    finished_runs = session.exec(
        select(SimulationRun).where(SimulationRun.status == "finished")
    ).all()

    occurrences_by_product: dict[tuple[int, str], list[OpportunityOccurrence]] = {
        (p.id, p.name): [] for p in products.values()
    }

    if not finished_runs:
        return [_to_out(s) for s in rank_opportunities(occurrences_by_product)]

    # run件数ぶんクエリを繰り返さず、IN句で一括取得してからPython側でグルーピングする
    run_ids = [run.id for run in finished_runs]
    all_logs = session.exec(select(PurchaseLog).where(PurchaseLog.run_id.in_(run_ids))).all()
    all_recs = session.exec(
        select(DiscountRecommendation).where(DiscountRecommendation.run_id.in_(run_ids))
    ).all()

    logs_by_run_product: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for log in all_logs:
        logs_by_run_product.setdefault((log.run_id, log.product_id), []).append(
            (log.step, log.quantity)
        )
    recs_by_run_product: dict[tuple[int, int], list[tuple[int, float]]] = {}
    for rec in all_recs:
        recs_by_run_product.setdefault((rec.run_id, rec.product_id), []).append(
            (rec.step, rec.recommended_rate)
        )

    for (run_id, product_id), log_steps in logs_by_run_product.items():
        product = products.get(product_id)
        if product is None:
            continue  # 削除済み商品は対象外
        step_records = build_step_records(
            log_steps, recs_by_run_product.get((run_id, product_id), [])
        )
        occurrence = detect_opportunity(step_records, product.initial_stock)
        if occurrence is not None:
            occurrences_by_product[(product.id, product.name)].append(occurrence)

    summaries = rank_opportunities(occurrences_by_product)
    return [_to_out(s) for s in summaries]
