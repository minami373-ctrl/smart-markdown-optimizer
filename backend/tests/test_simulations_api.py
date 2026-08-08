import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import Product, SimulationRun

PRIOR_DEMAND = {
    "晴れ_平日_なし": {"alpha": 3.0, "beta": 2.0},
    "雨_平日_なし": {"alpha": 1.0, "beta": 2.0},
    "晴れ_休日_あり": {"alpha": 5.0, "beta": 2.0},
}


def _add_products(session: Session) -> list[Product]:
    products = [
        Product(
            name="唐揚げ",
            initial_stock=30,
            elasticity=0.12,
            prior_demand=json.dumps(PRIOR_DEMAND, ensure_ascii=False),
        ),
        Product(
            name="おでん",
            initial_stock=20,
            elasticity=0.10,
            prior_demand=json.dumps(PRIOR_DEMAND, ensure_ascii=False),
        ),
    ]
    for p in products:
        session.add(p)
    session.commit()
    for p in products:
        session.refresh(p)
    return products


VALID_BODY = {
    "weather": "晴れ",
    "day_type": "平日",
    "has_event": False,
    "target_waste_rate": 0.05,
}


def test_create_simulation_returns_steps_and_finals(
    session: Session, client: TestClient
) -> None:
    products = _add_products(session)

    res = client.post("/api/simulations", json=VALID_BODY)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "finished"
    assert len(body["finals"]) == len(products)
    # 商品数 × 40ステップぶんの明細が返る
    assert len(body["steps"]) == len(products) * 40


def test_create_simulation_steps_include_growing_posterior_beta(
    session: Session, client: TestClient
) -> None:
    """フロントが確率分布グラフを描けるよう、betaが単調に増えていく様子が返る。"""
    _add_products(session)

    res = client.post("/api/simulations", json=VALID_BODY)

    body = res.json()
    product_steps = sorted(
        (s for s in body["steps"] if s["product_id"] == body["finals"][0]["product_id"]),
        key=lambda s: s["step"],
    )
    betas = [s["posterior_beta"] for s in product_steps]
    assert all(a is not None for a in betas)
    assert betas == sorted(betas)  # 露出が積み上がるので単調非減少
    assert product_steps[0]["posterior_alpha"] is not None


def test_create_simulation_rejects_out_of_range_target_waste_rate(
    session: Session, client: TestClient
) -> None:
    _add_products(session)

    res = client.post("/api/simulations", json={**VALID_BODY, "target_waste_rate": 0.5})

    assert res.status_code == 422


def test_create_simulation_rejects_invalid_weather(session: Session, client: TestClient) -> None:
    _add_products(session)

    res = client.post("/api/simulations", json={**VALID_BODY, "weather": "台風"})

    assert res.status_code == 422


def test_create_simulation_missing_condition_key_returns_500(
    session: Session, client: TestClient
) -> None:
    session.add(
        Product(
            name="寿司",
            initial_stock=20,
            elasticity=0.18,
            prior_demand=json.dumps({"晴れ_平日_なし": {"alpha": 2.0, "beta": 2.0}}),
        )
    )
    session.commit()

    # 「雨_休日_あり」の事前分布が無い状態でリクエスト
    res = client.post(
        "/api/simulations",
        json={"weather": "雨", "day_type": "休日", "has_event": True, "target_waste_rate": 0.05},
    )

    assert res.status_code == 500
    # 検証失敗時は SimulationRun を作らない（running のまま孤立するレコードを残さない）
    assert session.exec(select(SimulationRun)).all() == []


def test_list_simulations_returns_history_newest_first(
    session: Session, client: TestClient
) -> None:
    _add_products(session)
    first = client.post("/api/simulations", json=VALID_BODY).json()
    second = client.post("/api/simulations", json=VALID_BODY).json()

    res = client.get("/api/simulations")

    assert res.status_code == 200
    ids = [r["id"] for r in res.json()]
    assert ids[0] == second["id"]
    assert second["id"] in ids and first["id"] in ids


def test_get_simulation_detail_reconstructs_quantities_from_db(
    session: Session, client: TestClient
) -> None:
    _add_products(session)
    created = client.post("/api/simulations", json=VALID_BODY).json()
    run_id = created["id"]

    res = client.get(f"/api/simulations/{run_id}")

    assert res.status_code == 200
    detail = res.json()

    created_quantities = sorted(
        (s["product_id"], s["step"], s["quantity"]) for s in created["steps"]
    )
    reconstructed_quantities = sorted(
        (s["product_id"], s["step"], s["quantity"]) for s in detail["steps"]
    )
    assert created_quantities == reconstructed_quantities

    created_rates = {
        (s["product_id"], s["step"]): s["recommended_rate"] for s in created["steps"]
    }
    for s in detail["steps"]:
        assert s["recommended_rate"] == created_rates[(s["product_id"], s["step"])]

    # 分布パラメータはライブ実行直後（POST）だけに入り、履歴の再構築（GET）では持たない
    # （docs/spec.md §4①：「履歴画面では表示しない」）
    assert all(s["posterior_alpha"] is not None for s in created["steps"])
    assert all(s["posterior_alpha"] is None for s in detail["steps"])
    assert all(s["posterior_beta"] is None for s in detail["steps"])


def test_get_simulation_not_found_returns_404(session: Session, client: TestClient) -> None:
    res = client.get("/api/simulations/9999")

    assert res.status_code == 404


def test_get_simulation_survives_deleted_product(session: Session, client: TestClient) -> None:
    """商品を削除した後でも、その商品を含む過去の履歴の取得はエラーにならない
    （docs/spec.md §4②・§7）。remaining_stock は初期在庫が分からないため null になる。"""
    products = _add_products(session)
    created = client.post("/api/simulations", json=VALID_BODY).json()
    run_id = created["id"]
    deleted_id = products[0].id

    del_res = client.delete(f"/api/products/{deleted_id}")
    assert del_res.status_code == 204

    res = client.get(f"/api/simulations/{run_id}")

    assert res.status_code == 200
    detail = res.json()
    deleted_steps = [s for s in detail["steps"] if s["product_id"] == deleted_id]
    assert deleted_steps, "削除した商品ぶんのstepsが無くなってはいけない（quantityの記録は残す）"
    assert all(s["remaining_stock"] is None for s in deleted_steps)
    # 削除していない商品は通常どおり数値が入る
    other_steps = [s for s in detail["steps"] if s["product_id"] != deleted_id]
    assert all(s["remaining_stock"] is not None for s in other_steps)

    # 履歴一覧側は既存の "?" フォールバックで壊れない
    list_res = client.get("/api/simulations")
    assert list_res.status_code == 200
    names = {f["product_name"] for r in list_res.json() for f in r["finals"]}
    assert "?" in names


def test_deleted_product_id_is_not_reused_by_sqlite(
    session: Session, client: TestClient
) -> None:
    """SQLiteはAUTOINCREMENT無しだと削除した行のidを使い回すため、
    別商品を新規作成したときに過去の履歴と衝突しないことを確認する。"""
    products = _add_products(session)
    deleted_id = products[0].id

    client.delete(f"/api/products/{deleted_id}")

    res = client.post(
        "/api/products",
        json={"name": "新商品", "initial_stock": 10, "elasticity": 0.1, "base_demand": 1.0},
    )

    assert res.status_code == 201
    assert res.json()["id"] != deleted_id
