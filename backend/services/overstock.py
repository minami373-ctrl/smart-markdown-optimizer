"""過剰在庫の検出（docs/spec.md §5.6）。`services/opportunity.py`（機会損失）の鏡像。
最大値引きまで下げても売り切れなかった商品を見つける。

DBもネットワークも触らない純関数の集まり。
"""

from dataclasses import dataclass

from services.simulation import MAX_DISCOUNT as MAX_DISCOUNT_RATE  # ズレ防止のためsimulation.py側の値をそのまま使う


@dataclass
class OverstockOccurrence:
    final_remaining: int
    suggested_decrease: int


def detect_overstock(
    recommended_rates: list[float], quantities: list[int], initial_stock: int
) -> OverstockOccurrence | None:
    """1つの run×product ぶんの記録から、過剰在庫（最大値引きまで下げても売れ残り）を検出する。

    `recommended_rates` はその回にその商品へ提案された値引き率の一覧（変化があった時点だけの
    記録で構わない。`DiscountRecommendation`をそのまま渡す想定）。`quantities` は
    ステップごとの購入個数の一覧（`PurchaseLog`をそのまま渡す想定。順序は問わない）。
    該当しなければ None。
    """
    if initial_stock <= 0:
        return None
    if not any(rate >= MAX_DISCOUNT_RATE for rate in recommended_rates):
        return None  # 一度も最大値引きに達していなければ対象外（値引きを目一杯効かせていない）

    final_remaining = initial_stock - sum(quantities)
    if final_remaining <= 0:
        return None  # 値引きが効いて完売したということなので、在庫は適正だった

    return OverstockOccurrence(final_remaining=final_remaining, suggested_decrease=final_remaining)


@dataclass
class ProductOverstockSummary:
    product_id: int
    product_name: str
    occurrence_count: int
    avg_final_remaining: float
    avg_suggested_decrease: float


def rank_overstocks(
    occurrences_by_product: dict[tuple[int, str], list[OverstockOccurrence]],
    limit: int = 10,
) -> list[ProductOverstockSummary]:
    """商品ごとに集計し、推奨削減在庫数の平均が大きい順に上位 limit 件を返す。
    該当0件（空リスト）の商品はキーごと渡さないこと（結果に含めたくなければ渡さない）。
    """
    summaries = [
        ProductOverstockSummary(
            product_id=product_id,
            product_name=product_name,
            occurrence_count=len(occs),
            avg_final_remaining=sum(o.final_remaining for o in occs) / len(occs),
            avg_suggested_decrease=sum(o.suggested_decrease for o in occs) / len(occs),
        )
        for (product_id, product_name), occs in occurrences_by_product.items()
        if occs
    ]
    summaries.sort(key=lambda s: s.avg_suggested_decrease, reverse=True)
    return summaries[:limit]
