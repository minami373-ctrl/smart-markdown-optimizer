"""値引きタイミングの傾向分析API（docs/spec.md §4⑦・§5.10）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from db import get_session
from models import DiscountRecommendation, SimulationResult, SimulationRun
from services.discount_timing import first_discount_step, summarize_condition_timing

router = APIRouter(prefix="/api/discount-timing", tags=["discount-timing"])


class ConditionTimingOut(BaseModel):
    weather: str
    day_type: str
    has_event: bool
    sample_count: int
    discounted_count: int
    avg_first_discount_step: float | None


@router.get("", response_model=list[ConditionTimingOut])
def get_discount_timing(session: Session = Depends(get_session)) -> list[ConditionTimingOut]:
    finished_runs = session.exec(
        select(SimulationRun).where(SimulationRun.status == "finished")
    ).all()
    if not finished_runs:
        return []

    run_ids = [run.id for run in finished_runs]
    run_by_id = {run.id: run for run in finished_runs}

    # run件数ぶんクエリを繰り返さず、IN句で一括取得してからPython側でグルーピングする
    # （routers/opportunities.py・routers/overstock.pyと同じ方針）
    all_results = session.exec(
        select(SimulationResult).where(SimulationResult.run_id.in_(run_ids))
    ).all()
    all_recs = session.exec(
        select(DiscountRecommendation).where(DiscountRecommendation.run_id.in_(run_ids))
    ).all()

    recs_by_run_product: dict[tuple[int, int], list[tuple[int, float]]] = {}
    for rec in all_recs:
        recs_by_run_product.setdefault((rec.run_id, rec.product_id), []).append(
            (rec.step, rec.recommended_rate)
        )

    # 条件（天気・曜日・イベント有無）ごとに初回値引きステップのリストを集める。
    # 商品ごとではなく条件ごとの集計のため、削除済み商品のSimulationResultも含める
    # （docs/spec.md §5.10「削除済み商品の扱い」）
    first_steps_by_condition: dict[tuple[str, str, bool], list[int | None]] = {}
    for result in all_results:
        run = run_by_id.get(result.run_id)
        if run is None:
            continue  # 通常は起こらない（all_resultsはrun_idsから引いているため）
        condition = (run.weather, run.day_type, run.has_event)
        recs = recs_by_run_product.get((result.run_id, result.product_id), [])
        first_step = first_discount_step(recs)
        first_steps_by_condition.setdefault(condition, []).append(first_step)

    summaries = [
        summarize_condition_timing(weather, day_type, has_event, steps)
        for (weather, day_type, has_event), steps in first_steps_by_condition.items()
    ]

    return [
        ConditionTimingOut(
            weather=s.weather,
            day_type=s.day_type,
            has_event=s.has_event,
            sample_count=s.sample_count,
            discounted_count=s.discounted_count,
            avg_first_discount_step=s.avg_first_discount_step,
        )
        for s in summaries
    ]
