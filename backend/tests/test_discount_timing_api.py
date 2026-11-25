from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from models import DiscountRecommendation, Product, SimulationResult, SimulationRun


def _add_product(session: Session, name: str = "唐揚げ") -> Product:
    p = Product(name=name, initial_stock=30, elasticity=0.12, prior_demand="{}")
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _add_finished_run(
    session: Session, weather: str = "晴れ", day_type: str = "平日", has_event: bool = False
) -> SimulationRun:
    run = SimulationRun(
        weather=weather,
        day_type=day_type,
        has_event=has_event,
        target_waste_rate=0.03,
        status="finished",
        started_at=datetime.now(),
        finished_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _add_simulation_result(session: Session, run_id: int, product_id: int) -> None:
    session.add(
        SimulationResult(
            run_id=run_id, product_id=product_id, final_waste_rate=0.0, achieved=True,
            initial_stock=30,
        )
    )
    session.commit()


def _add_discount_recommendation(
    session: Session, run_id: int, product_id: int, step: int, rate: float
) -> None:
    session.add(
        DiscountRecommendation(
            run_id=run_id, product_id=product_id, step=step, recommended_rate=rate,
            posterior_mean=1.0,
        )
    )
    session.commit()


def test_no_finished_runs_returns_empty_list(session: Session, client: TestClient) -> None:
    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    assert res.json() == []


def test_aggregates_first_discount_step_per_condition(
    session: Session, client: TestClient
) -> None:
    product = _add_product(session)
    run1 = _add_finished_run(session, weather="雨", day_type="平日", has_event=False)
    _add_simulation_result(session, run1.id, product.id)
    _add_discount_recommendation(session, run1.id, product.id, step=5, rate=0.30)
    _add_discount_recommendation(session, run1.id, product.id, step=10, rate=0.75)

    run2 = _add_finished_run(session, weather="雨", day_type="平日", has_event=False)
    _add_simulation_result(session, run2.id, product.id)
    _add_discount_recommendation(session, run2.id, product.id, step=15, rate=0.30)

    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["weather"] == "雨"
    assert entry["day_type"] == "平日"
    assert entry["has_event"] is False
    assert entry["sample_count"] == 2
    assert entry["discounted_count"] == 2
    assert entry["avg_first_discount_step"] == 10.0  # (5 + 15) / 2


def test_condition_with_no_discount_has_null_average(
    session: Session, client: TestClient
) -> None:
    product = _add_product(session)
    run = _add_finished_run(session, weather="晴れ", day_type="休日", has_event=True)
    _add_simulation_result(session, run.id, product.id)
    # DiscountRecommendationを一切追加しない＝値引きが一度も発生しなかった

    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["sample_count"] == 1
    assert body[0]["discounted_count"] == 0
    assert body[0]["avg_first_discount_step"] is None


def test_separates_different_conditions(session: Session, client: TestClient) -> None:
    product = _add_product(session)
    rainy = _add_finished_run(session, weather="雨", day_type="平日", has_event=False)
    _add_simulation_result(session, rainy.id, product.id)
    _add_discount_recommendation(session, rainy.id, product.id, step=3, rate=0.30)

    sunny = _add_finished_run(session, weather="晴れ", day_type="平日", has_event=False)
    _add_simulation_result(session, sunny.id, product.id)
    _add_discount_recommendation(session, sunny.id, product.id, step=30, rate=0.30)

    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    body = {(e["weather"], e["day_type"], e["has_event"]): e for e in res.json()}
    assert len(body) == 2
    assert body[("雨", "平日", False)]["avg_first_discount_step"] == 3.0
    assert body[("晴れ", "平日", False)]["avg_first_discount_step"] == 30.0


def test_ignores_running_simulations(session: Session, client: TestClient) -> None:
    product = _add_product(session)
    run = SimulationRun(
        weather="雨", day_type="平日", has_event=False, target_waste_rate=0.03,
        status="running", started_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    _add_simulation_result(session, run.id, product.id)

    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    assert res.json() == []


def test_includes_deleted_products_in_condition_aggregate(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.10：商品ごとではなく条件ごとの集計のため、削除済み商品の
    SimulationResultも含める（/opportunities・/overstockとは異なる方針）。"""
    product = _add_product(session, "削除予定")
    run = _add_finished_run(session, weather="雨", day_type="平日", has_event=False)
    _add_simulation_result(session, run.id, product.id)
    _add_discount_recommendation(session, run.id, product.id, step=7, rate=0.30)

    client.delete(f"/api/products/{product.id}")
    res = client.get("/api/discount-timing")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["sample_count"] == 1
    assert body[0]["avg_first_discount_step"] == 7.0
