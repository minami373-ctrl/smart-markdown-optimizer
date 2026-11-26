from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from models import DiscountRecommendation, Product, PurchaseLog, SimulationResult, SimulationRun


def _add_product(session: Session, name: str, initial_stock: int) -> Product:
    p = Product(name=name, initial_stock=initial_stock, elasticity=0.1, prior_demand="{}")
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _add_finished_run(session: Session) -> SimulationRun:
    run = SimulationRun(
        weather="晴れ",
        day_type="平日",
        has_event=False,
        target_waste_rate=0.03,
        status="finished",
        started_at=datetime.now(),
        finished_at=datetime.now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _add_logs(session: Session, run_id: int, product_id: int, quantities: list[int]) -> None:
    for step, qty in enumerate(quantities):
        session.add(PurchaseLog(run_id=run_id, product_id=product_id, step=step, quantity=qty))
    session.commit()


def _add_simulation_result(
    session: Session, run_id: int, product_id: int, initial_stock: int
) -> None:
    """このrun実行当時の初期在庫のスナップショット（docs/spec.md §5.7）。
    /api/opportunitiesはこれを見て判定するため、テストデータでも明示的に用意する
    （final_waste_rate/achievedはopportunities側のロジックが見ないのでダミー値でよい）。"""
    session.add(
        SimulationResult(
            run_id=run_id,
            product_id=product_id,
            final_waste_rate=0.0,
            achieved=True,
            initial_stock=initial_stock,
        )
    )
    session.commit()


def test_detects_product_that_sold_out_early_without_discount(
    session: Session, client: TestClient
) -> None:
    product = _add_product(session, "唐揚げ", initial_stock=10)
    run = _add_finished_run(session)
    _add_logs(session, run.id, product.id, [2, 2, 2, 2, 2])  # 5ステップで完売、値引きなし
    _add_simulation_result(session, run.id, product.id, product.initial_stock)

    res = client.get("/api/opportunities")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["product_name"] == "唐揚げ"
    assert body[0]["occurrence_count"] == 1
    assert body[0]["avg_suggested_increase"] == 86


def test_uses_snapshot_initial_stock_not_live_value(
    session: Session, client: TestClient
) -> None:
    """在庫の自動調整（§5.7）でProduct.initial_stockが後から変わっても、
    過去のrunの判定はSimulationResult.initial_stock（実行当時のスナップショット）のまま
    変わらないことを確認する（HIGH指摘の再発防止）。"""
    product = _add_product(session, "唐揚げ", initial_stock=10)
    run = _add_finished_run(session)
    _add_logs(session, run.id, product.id, [2, 2, 2, 2, 2])  # 5ステップで完売、値引きなし
    _add_simulation_result(session, run.id, product.id, initial_stock=10)  # 実行当時は10

    # 実行後、在庫の自動調整で現在のProduct.initial_stockが大きく変わったとする
    product.initial_stock = 999
    session.add(product)
    session.commit()

    res = client.get("/api/opportunities")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    # スナップショット値(10)基準の結果のままであり、現在値(999)基準にはならない
    assert body[0]["avg_suggested_increase"] == 86


def test_excludes_product_that_was_discounted(session: Session, client: TestClient) -> None:
    product = _add_product(session, "おでん", initial_stock=10)
    run = _add_finished_run(session)
    _add_logs(session, run.id, product.id, [2, 2, 2, 2, 2])
    _add_simulation_result(session, run.id, product.id, product.initial_stock)
    session.add(
        DiscountRecommendation(
            run_id=run.id, product_id=product.id, step=1, recommended_rate=0.2, posterior_mean=1.0
        )
    )
    session.commit()

    res = client.get("/api/opportunities")

    assert res.status_code == 200
    assert res.json() == []


def test_excludes_product_that_never_sells_out(session: Session, client: TestClient) -> None:
    product = _add_product(session, "寿司", initial_stock=100)
    run = _add_finished_run(session)
    _add_logs(session, run.id, product.id, [1] * 48)
    _add_simulation_result(session, run.id, product.id, product.initial_stock)

    res = client.get("/api/opportunities")

    assert res.json() == []


def test_no_finished_runs_returns_empty_list(session: Session, client: TestClient) -> None:
    _add_product(session, "唐揚げ", initial_stock=10)

    res = client.get("/api/opportunities")

    assert res.status_code == 200
    assert res.json() == []


def test_ranks_multiple_products_by_avg_suggested_increase(
    session: Session, client: TestClient
) -> None:
    small = _add_product(session, "小さい機会損失", initial_stock=10)
    big = _add_product(session, "大きい機会損失", initial_stock=10)
    run = _add_finished_run(session)
    # small: 20ステップで完売（緩やかな機会損失）
    _add_logs(session, run.id, small.id, [1] * 10 + [0] * 30)
    _add_simulation_result(session, run.id, small.id, small.initial_stock)
    # big: 2ステップで完売（大きな機会損失）
    _add_logs(session, run.id, big.id, [5, 5])
    _add_simulation_result(session, run.id, big.id, big.initial_stock)

    res = client.get("/api/opportunities")

    names = [r["product_name"] for r in res.json()]
    assert names[0] == "大きい機会損失"
    assert "小さい機会損失" in names


def test_ignores_deleted_product(session: Session, client: TestClient) -> None:
    product = _add_product(session, "削除予定", initial_stock=10)
    run = _add_finished_run(session)
    _add_logs(session, run.id, product.id, [2, 2, 2, 2, 2])
    _add_simulation_result(session, run.id, product.id, product.initial_stock)

    client.delete(f"/api/products/{product.id}")
    res = client.get("/api/opportunities")

    assert res.status_code == 200
    assert res.json() == []
