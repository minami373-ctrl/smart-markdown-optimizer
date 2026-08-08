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
