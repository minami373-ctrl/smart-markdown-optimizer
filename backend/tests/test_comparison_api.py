import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import Product, SimulationRun
from services.schedule_comparison import FIXED_SCHEDULE_30_STEP, FIXED_SCHEDULE_50_STEP

PRIOR_DEMAND = {
    "晴れ_平日_なし": {"alpha": 3.0, "beta": 2.0},
    "雨_平日_なし": {"alpha": 1.0, "beta": 2.0},
}


def _add_product(
    session: Session,
    name: str = "唐揚げ",
    initial_stock: int = 30,
    unit_price: int | None = None,
) -> Product:
    p = Product(
        name=name,
        initial_stock=initial_stock,
        elasticity=0.12,
        prior_demand=json.dumps(PRIOR_DEMAND, ensure_ascii=False),
        unit_price=unit_price,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


VALID_BODY = {
    "weather": "晴れ",
    "day_type": "平日",
    "has_event": False,
    "target_waste_rate": 0.05,
}


def test_compare_returns_dynamic_and_fixed_results_per_product(
    session: Session, client: TestClient
) -> None:
    _add_product(session, "唐揚げ", initial_stock=30)
    _add_product(session, "おでん", initial_stock=20)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    body = res.json()
    assert len(body["products"]) == 2
    for p in body["products"]:
        assert set(p.keys()) == {
            "product_id",
            "product_name",
            "unit_price",
            "dynamic_steps",
            "dynamic_final_waste_rate",
            "fixed_steps",
            "fixed_final_waste_rate",
        }
        assert len(p["dynamic_steps"]) == 48  # 15分ごと（§5.19）
        assert len(p["fixed_steps"]) == 48


def test_compare_returns_fixed_schedule_step_constants(
    session: Session, client: TestClient
) -> None:
    _add_product(session)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["fixed_schedule_30_step"] == FIXED_SCHEDULE_30_STEP
    assert body["fixed_schedule_50_step"] == FIXED_SCHEDULE_50_STEP


def test_compare_does_not_persist_anything_to_db(session: Session, client: TestClient) -> None:
    """docs/spec.md §5.9：一過性の比較のため、DBには何も保存しない。"""
    product = _add_product(session, "唐揚げ", initial_stock=30)
    original_prior_demand = product.prior_demand
    original_initial_stock = product.initial_stock

    res = client.post("/api/compare", json=VALID_BODY)
    assert res.status_code == 200

    runs = session.exec(select(SimulationRun)).all()
    assert len(runs) == 0, "SimulationRunが作られてはいけない（一過性の比較のため）"

    session.refresh(product)
    assert product.prior_demand == original_prior_demand, "学習の継続が発生してはいけない"
    assert product.initial_stock == original_initial_stock, "在庫の自動調整が発生してはいけない"


def test_compare_includes_unit_price_when_set(session: Session, client: TestClient) -> None:
    _add_product(session, "唐揚げ", initial_stock=30, unit_price=350)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    assert res.json()["products"][0]["unit_price"] == 350


def test_compare_unit_price_is_null_when_unset(session: Session, client: TestClient) -> None:
    _add_product(session, "唐揚げ", initial_stock=30)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    assert res.json()["products"][0]["unit_price"] is None


def test_compare_excludes_zero_stock_products(session: Session, client: TestClient) -> None:
    _add_product(session, "唐揚げ", initial_stock=30)
    _add_product(session, "在庫切れ商品", initial_stock=0)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    names = [p["product_name"] for p in res.json()["products"]]
    assert names == ["唐揚げ"]


def test_compare_with_no_products_returns_500(session: Session, client: TestClient) -> None:
    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 500


def test_compare_with_only_zero_stock_products_returns_empty_list_not_500(
    session: Session, client: TestClient
) -> None:
    """コードレビュー指摘の回帰テスト：商品自体は存在するが全商品が0在庫のとき、
    POST /api/simulations（200・空配列）と同じ扱いになる（500にはならない）。
    以前は0在庫フィルタを商品の存在チェックより先に行っていたため、
    このケースで誤って「商品が登録されていません」という500になっていた。"""
    _add_product(session, "在庫切れ商品", initial_stock=0)

    res = client.post("/api/compare", json=VALID_BODY)

    assert res.status_code == 200
    assert res.json()["products"] == []


def test_compare_with_missing_prior_demand_condition_returns_500(
    session: Session, client: TestClient
) -> None:
    _add_product(session, "唐揚げ", initial_stock=30)

    res = client.post(
        "/api/compare",
        json={"weather": "雨", "day_type": "休日", "has_event": True, "target_waste_rate": 0.05},
    )

    assert res.status_code == 500


def test_compare_rejects_target_waste_rate_out_of_range(
    session: Session, client: TestClient
) -> None:
    _add_product(session)

    res = client.post(
        "/api/compare",
        json={"weather": "晴れ", "day_type": "平日", "has_event": False, "target_waste_rate": 0.5},
    )

    assert res.status_code == 422


def test_compare_fixed_schedule_never_discounts_before_30_step(
    session: Session, client: TestClient
) -> None:
    """需要が低い条件でも、固定スケジュール側はステップ30（19時相当）より前は値引きしない。"""
    _add_product(session, "唐揚げ", initial_stock=100)

    res = client.post(
        "/api/compare",
        json={"weather": "雨", "day_type": "平日", "has_event": False, "target_waste_rate": 0.05},
    )

    assert res.status_code == 200
    fixed_steps = res.json()["products"][0]["fixed_steps"]
    early = [s for s in fixed_steps if s["step"] < FIXED_SCHEDULE_30_STEP]
    assert all(s["recommended_rate"] == 0.0 for s in early)
