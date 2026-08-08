"""seed/products.json を SQLite に投入する。

自分が扱うテーブル（Product）だけを入れ替える。他のテーブル（実行履歴等）は消さない。
"""

import json
from pathlib import Path

from sqlmodel import Session, delete, select

from db import engine, init_db
from models import Product

SEED_DIR = Path(__file__).parent


def load_products(session: Session) -> int:
    data = json.loads((SEED_DIR / "products.json").read_text(encoding="utf-8"))
    session.exec(delete(Product))
    for item in data:
        session.add(
            Product(
                name=item["name"],
                initial_stock=item["initial_stock"],
                elasticity=item["elasticity"],
                prior_demand=json.dumps(item["prior_demand"], ensure_ascii=False),
            )
        )
    session.commit()
    return len(data)


def main() -> None:
    init_db()
    with Session(engine) as session:
        n = load_products(session)
        print(f"products.json: 商品 {n} 件")


if __name__ == "__main__":
    main()
