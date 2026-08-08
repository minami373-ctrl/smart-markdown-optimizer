import json

from fastapi.testclient import TestClient
from sqlmodel import Session

from models import Product


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
