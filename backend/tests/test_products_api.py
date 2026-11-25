import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import Product, SimulationRun, StockAdjustmentLog


def _add_product(session: Session, name: str = "唐揚げ") -> Product:
    p = Product(
        name=name,
        initial_stock=30,
        elasticity=0.12,
        prior_demand=json.dumps({"晴れ_平日_なし": {"alpha": 3.0, "beta": 2.0}}),
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _add_extreme_demand_product(
    session: Session, *, initial_stock: int, alpha: float
) -> Product:
    """docs/spec.md §5.7の在庫の自動調整を確実に発生させるための、需要が極端な商品。"""
    p = Product(
        name="極端商品",
        initial_stock=initial_stock,
        elasticity=0.12,
        prior_demand=json.dumps({"晴れ_平日_なし": {"alpha": alpha, "beta": 2.0}}),
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


SIM_BODY = {"weather": "晴れ", "day_type": "平日", "has_event": False, "target_waste_rate": 0.05}


def test_list_products_returns_seeded_products(session: Session, client: TestClient) -> None:
    _add_product(session, "唐揚げ")
    _add_product(session, "おでん")

    res = client.get("/api/products")

    assert res.status_code == 200
    names = {p["name"] for p in res.json()}
    assert names == {"唐揚げ", "おでん"}
    assert res.json()[0]["prior_demand"]["晴れ_平日_なし"]["alpha"] == 3.0


def test_create_product_generates_12_prior_conditions(
    session: Session, client: TestClient
) -> None:
    res = client.post(
        "/api/products",
        json={"name": "たこ焼き", "initial_stock": 25, "elasticity": 0.15, "base_demand": 1.0},
    )

    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "たこ焼き"
    assert len(body["prior_demand"]) == 12
    assert body["prior_demand"]["晴れ_平日_なし"]["alpha"] > body["prior_demand"]["雨_平日_なし"]["alpha"]

    # 一覧にも反映される
    listed = client.get("/api/products").json()
    assert any(p["name"] == "たこ焼き" for p in listed)


def test_create_product_without_unit_price_defaults_to_null(
    session: Session, client: TestClient
) -> None:
    res = client.post(
        "/api/products",
        json={"name": "たこ焼き", "initial_stock": 25, "elasticity": 0.15, "base_demand": 1.0},
    )

    assert res.status_code == 201
    assert res.json()["unit_price"] is None


def test_create_product_with_unit_price(session: Session, client: TestClient) -> None:
    res = client.post(
        "/api/products",
        json={
            "name": "たこ焼き",
            "initial_stock": 25,
            "elasticity": 0.15,
            "base_demand": 1.0,
            "unit_price": 400,
        },
    )

    assert res.status_code == 201
    assert res.json()["unit_price"] == 400


def test_create_product_rejects_negative_unit_price(
    session: Session, client: TestClient
) -> None:
    res = client.post(
        "/api/products",
        json={
            "name": "たこ焼き",
            "initial_stock": 25,
            "elasticity": 0.15,
            "base_demand": 1.0,
            "unit_price": -100,
        },
    )

    assert res.status_code == 422


def test_create_product_rejects_non_positive_values(
    session: Session, client: TestClient
) -> None:
    res = client.post(
        "/api/products",
        json={"name": "無効商品", "initial_stock": 0, "elasticity": 0.1, "base_demand": 1.0},
    )
    assert res.status_code == 422


def test_create_product_rejects_blank_name(session: Session, client: TestClient) -> None:
    res = client.post(
        "/api/products",
        json={"name": "  ", "initial_stock": 10, "elasticity": 0.1, "base_demand": 1.0},
    )
    assert res.status_code == 422


def test_create_product_strips_surrounding_whitespace_from_name(
    session: Session, client: TestClient
) -> None:
    res = client.post(
        "/api/products",
        json={"name": "  たこ焼き  ", "initial_stock": 10, "elasticity": 0.1, "base_demand": 1.0},
    )
    assert res.status_code == 201
    assert res.json()["name"] == "たこ焼き"


def test_delete_product_removes_it_from_list(session: Session, client: TestClient) -> None:
    product = _add_product(session, "削除対象")

    res = client.delete(f"/api/products/{product.id}")

    assert res.status_code == 204
    listed = client.get("/api/products").json()
    assert all(p["id"] != product.id for p in listed)


def test_delete_nonexistent_product_returns_404(session: Session, client: TestClient) -> None:
    res = client.delete("/api/products/9999")
    assert res.status_code == 404


def test_update_product_regenerates_prior_demand(session: Session, client: TestClient) -> None:
    created = client.post(
        "/api/products",
        json={"name": "たこ焼き", "initial_stock": 20, "elasticity": 0.15, "base_demand": 1.0},
    ).json()

    res = client.patch(
        f"/api/products/{created['id']}",
        json={"name": "たこ焼き", "initial_stock": 30, "elasticity": 0.2, "base_demand": 2.0},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["initial_stock"] == 30
    assert body["elasticity"] == 0.2
    # base_demandが2倍になったので alpha も2倍になっているはず
    old_alpha = created["prior_demand"]["晴れ_平日_なし"]["alpha"]
    new_alpha = body["prior_demand"]["晴れ_平日_なし"]["alpha"]
    assert new_alpha == old_alpha * 2


def test_update_product_changes_unit_price(session: Session, client: TestClient) -> None:
    created = client.post(
        "/api/products",
        json={
            "name": "たこ焼き",
            "initial_stock": 20,
            "elasticity": 0.15,
            "base_demand": 1.0,
            "unit_price": 300,
        },
    ).json()
    assert created["unit_price"] == 300

    res = client.patch(
        f"/api/products/{created['id']}",
        json={
            "name": "たこ焼き",
            "initial_stock": 20,
            "elasticity": 0.15,
            "base_demand": 1.0,
            "unit_price": 450,
        },
    )

    assert res.status_code == 200
    assert res.json()["unit_price"] == 450


def test_update_product_can_clear_unit_price(session: Session, client: TestClient) -> None:
    created = client.post(
        "/api/products",
        json={
            "name": "たこ焼き",
            "initial_stock": 20,
            "elasticity": 0.15,
            "base_demand": 1.0,
            "unit_price": 300,
        },
    ).json()

    res = client.patch(
        f"/api/products/{created['id']}",
        json={"name": "たこ焼き", "initial_stock": 20, "elasticity": 0.15, "base_demand": 1.0},
    )

    assert res.status_code == 200
    assert res.json()["unit_price"] is None


def test_update_product_resets_learned_prior_demand(
    session: Session, client: TestClient
) -> None:
    """学習の継続（docs/spec.md §4②・§6）：シミュレーションで書き換わった事前分布も、
    編集（PATCH）すると12条件ぶん作り直され、学習内容はリセットされる。"""
    created = client.post(
        "/api/products",
        json={"name": "たこ焼き", "initial_stock": 20, "elasticity": 0.15, "base_demand": 1.0},
    ).json()
    key = "晴れ_平日_なし"

    client.post(
        "/api/simulations",
        json={
            "weather": "晴れ",
            "day_type": "平日",
            "has_event": False,
            "target_waste_rate": 0.05,
        },
    )
    learned = client.get("/api/products").json()
    learned_product = next(p for p in learned if p["id"] == created["id"])
    # シミュレーションでalphaが書き換わっている（露出が積み上がるので必ず初期値より大きい）
    assert learned_product["prior_demand"][key]["alpha"] > created["prior_demand"][key]["alpha"]

    res = client.patch(
        f"/api/products/{created['id']}",
        json={"name": "たこ焼き", "initial_stock": 20, "elasticity": 0.15, "base_demand": 1.0},
    )

    assert res.status_code == 200
    # base_demandを変えずに保存し直すと、学習で書き換わった値ではなく元の生成式の値に戻る
    assert res.json()["prior_demand"][key]["alpha"] == created["prior_demand"][key]["alpha"]


def test_update_product_can_rename(session: Session, client: TestClient) -> None:
    product = _add_product(session, "旧名前")

    res = client.patch(
        f"/api/products/{product.id}",
        json={"name": "新名前", "initial_stock": 10, "elasticity": 0.1, "base_demand": 1.0},
    )

    assert res.status_code == 200
    assert res.json()["name"] == "新名前"


def test_update_nonexistent_product_returns_404(session: Session, client: TestClient) -> None:
    res = client.patch(
        "/api/products/9999",
        json={"name": "x", "initial_stock": 10, "elasticity": 0.1, "base_demand": 1.0},
    )
    assert res.status_code == 404


def test_update_product_rejects_non_positive_values(
    session: Session, client: TestClient
) -> None:
    product = _add_product(session)

    res = client.patch(
        f"/api/products/{product.id}",
        json={"name": "x", "initial_stock": -1, "elasticity": 0.1, "base_demand": 1.0},
    )
    assert res.status_code == 422


def test_stock_adjustments_empty_when_none_happened(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.8：一度も自動調整が発生していない商品は空配列（エラーにしない）。"""
    product = _add_product(session)

    res = client.get(f"/api/products/{product.id}/stock-adjustments")

    assert res.status_code == 200
    assert res.json() == []


def test_stock_adjustments_returns_404_for_nonexistent_product(
    session: Session, client: TestClient
) -> None:
    res = client.get("/api/products/9999/stock-adjustments")
    assert res.status_code == 404


def test_stock_adjustments_records_opportunity_increase(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.7・§5.8：早期完売した商品は在庫が自動で増え、
    その調整がreason="opportunity"のログとして残る。"""
    product = _add_extreme_demand_product(session, initial_stock=5, alpha=20.0)

    sim_res = client.post("/api/simulations", json=SIM_BODY)
    assert sim_res.status_code == 200
    adjustments = {a["product_id"]: a for a in sim_res.json()["stock_adjustments"]}
    assert product.id in adjustments, f"stock_adjustments: {sim_res.json()['stock_adjustments']}"

    res = client.get(f"/api/products/{product.id}/stock-adjustments")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["reason"] == "opportunity"
    assert body[0]["delta"] == adjustments[product.id]["delta"]
    assert body[0]["new_initial_stock"] == adjustments[product.id]["new_initial_stock"]
    assert body[0]["run_id"] == sim_res.json()["id"]


def test_stock_adjustments_records_overstock_decrease(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.7・§5.8：最大値引きしても売れ残った商品は在庫が自動で減り、
    その調整がreason="overstock"のログとして残る。"""
    product = _add_extreme_demand_product(session, initial_stock=100, alpha=0.5)

    sim_res = client.post(
        "/api/simulations",
        json={"weather": "晴れ", "day_type": "平日", "has_event": False, "target_waste_rate": 0.0},
    )
    assert sim_res.status_code == 200
    adjustments = {a["product_id"]: a for a in sim_res.json()["stock_adjustments"]}
    assert product.id in adjustments, f"stock_adjustments: {sim_res.json()['stock_adjustments']}"

    res = client.get(f"/api/products/{product.id}/stock-adjustments")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["reason"] == "overstock"
    assert body[0]["delta"] < 0


def test_stock_adjustments_are_returned_in_occurrence_order(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.8：複数回の調整は発生順（created_at昇順）で返る。"""
    product = _add_extreme_demand_product(session, initial_stock=5, alpha=20.0)

    first = client.post("/api/simulations", json=SIM_BODY).json()
    second = client.post("/api/simulations", json=SIM_BODY).json()
    first_stock = next(
        a["new_initial_stock"] for a in first["stock_adjustments"] if a["product_id"] == product.id
    )
    second_stock = next(
        a["new_initial_stock"] for a in second["stock_adjustments"] if a["product_id"] == product.id
    )

    res = client.get(f"/api/products/{product.id}/stock-adjustments")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert body[0]["new_initial_stock"] == first_stock
    assert body[1]["new_initial_stock"] == second_stock
    assert body[0]["run_id"] == first["id"]
    assert body[1]["run_id"] == second["id"]


def test_stock_adjustments_use_id_as_tiebreak_for_identical_created_at(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.8：同一created_atになった場合でも、id（挿入順）でタイブレークして
    発生順どおりに返す（コードレビュー指摘の再発防止。「連続実行」§4①のようにPOSTを
    間隔を空けず繰り返すと、環境によってはdatetime.now()の分解能の都合で
    同一runの複数件が同じcreated_atになりうるため）。"""
    product = _add_product(session)
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

    same_time = datetime(2026, 8, 1, 12, 0, 0)
    session.add(
        StockAdjustmentLog(
            run_id=run.id,
            product_id=product.id,
            reason="opportunity",
            delta=10,
            new_initial_stock=40,
            created_at=same_time,
        )
    )
    session.commit()
    session.add(
        StockAdjustmentLog(
            run_id=run.id,
            product_id=product.id,
            reason="overstock",
            delta=-5,
            new_initial_stock=35,
            created_at=same_time,  # 1件目と全く同じcreated_at
        )
    )
    session.commit()

    res = client.get(f"/api/products/{product.id}/stock-adjustments")

    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    # 挿入順（=id順）どおりに返る
    assert body[0]["new_initial_stock"] == 40
    assert body[1]["new_initial_stock"] == 35


def test_stock_adjustment_log_survives_product_deletion(
    session: Session, client: TestClient
) -> None:
    """docs/spec.md §5.8：商品を削除してもStockAdjustmentLog自体は消えない
    （画面（このAPI）からは見えなくなるだけ）。"""
    product = _add_extreme_demand_product(session, initial_stock=5, alpha=20.0)
    client.post("/api/simulations", json=SIM_BODY)

    res = client.delete(f"/api/products/{product.id}")
    assert res.status_code == 204

    # このAPI自体は商品が無いので404になる
    assert client.get(f"/api/products/{product.id}/stock-adjustments").status_code == 404

    # しかしDB上のログ行は残っている
    remaining = session.exec(
        select(StockAdjustmentLog).where(StockAdjustmentLog.product_id == product.id)
    ).all()
    assert len(remaining) == 1


# --- 商品の種類（docs/spec.md §2.1・§6。2026-11-26追加） ---

_CREATE_BODY = {
    "name": "ロースカツ",
    "initial_stock": 25,
    "elasticity": 0.06,
    "base_demand": 0.45,
    "unit_price": 250,
}


def test_create_product_saves_category(client: TestClient) -> None:
    res = client.post("/api/products", json={**_CREATE_BODY, "category": "揚げ物の単品"})
    assert res.status_code == 201
    assert res.json()["category"] == "揚げ物の単品"
    listed = client.get("/api/products").json()
    assert listed[0]["category"] == "揚げ物の単品"


def test_create_product_without_category_defaults_to_bento(client: TestClient) -> None:
    res = client.post("/api/products", json=_CREATE_BODY)
    assert res.status_code == 201
    assert res.json()["category"] == "弁当・丼"


def test_create_product_rejects_unknown_category(client: TestClient) -> None:
    res = client.post("/api/products", json={**_CREATE_BODY, "category": "寿司"})
    assert res.status_code == 422


def test_update_product_overwrites_category(client: TestClient) -> None:
    created = client.post("/api/products", json={**_CREATE_BODY, "category": "揚げ物の単品"}).json()
    res = client.patch(
        f"/api/products/{created['id']}", json={**_CREATE_BODY, "category": "軽食・つまみ"}
    )
    assert res.status_code == 200
    assert res.json()["category"] == "軽食・つまみ"


def test_seed_has_12_products_in_3_categories(session: Session) -> None:
    from collections import Counter

    from seed.load import load_products

    n = load_products(session)
    products = session.exec(select(Product)).all()
    assert n == 12
    assert len(products) == 12
    assert Counter(p.category for p in products) == {
        "弁当・丼": 4,
        "揚げ物の単品": 4,
        "軽食・つまみ": 4,
    }
    # 売り場での観察（§2.1）：値引き感度は 弁当・丼 > 軽食・つまみ > 揚げ物の単品
    by_cat = {p.category: p.elasticity for p in products}
    assert by_cat["弁当・丼"] > by_cat["軽食・つまみ"] > by_cat["揚げ物の単品"]
