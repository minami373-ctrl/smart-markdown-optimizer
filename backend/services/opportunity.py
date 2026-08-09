"""機会損失の検出（docs/spec.md §5.5）。値引きを一切せず早期完売した商品を見つける。

DBもネットワークも触らない純関数の集まり。
"""

from dataclasses import dataclass

TOTAL_STEPS = 40
#: これ以下のステップで完売したら「早期完売」とみなす（閉店3ステップ以上前）
MAX_SELLOUT_STEP_FOR_EARLY = 37


@dataclass
class StepRecord:
    step: int
    quantity: int
    #: このステップの販売中に適用されていた値引き率（0なら値引きなし）
    recommended_rate: float


@dataclass
class OpportunityOccurrence:
    sellout_step: int
    suggested_increase: int


def detect_opportunity(
    steps: list[StepRecord], initial_stock: int
) -> OpportunityOccurrence | None:
    """1つの run×product ぶんのステップ列から、早期完売（値引きなし）を検出する。
    steps は step の昇順で渡すこと。該当しなければ None。
    """
    if initial_stock <= 0:
        return None

    remaining = initial_stock
    for s in sorted(steps, key=lambda r: r.step):
        if s.recommended_rate > 0:
            return None  # 一度でも値引きされていたら対象外
        remaining -= s.quantity
        if remaining <= 0:
            sellout_step = s.step
            if sellout_step > MAX_SELLOUT_STEP_FOR_EARLY:
                return None  # 閉店間際の完売は正常な在庫量とみなす
            steps_to_sellout = sellout_step + 1
            suggested_increase = round(
                initial_stock * (TOTAL_STEPS - steps_to_sellout) / steps_to_sellout
            )
            return OpportunityOccurrence(
                sellout_step=sellout_step, suggested_increase=suggested_increase
            )
    return None  # 最後まで売り切らなかった


@dataclass
class ProductOpportunitySummary:
    product_id: int
    product_name: str
    occurrence_count: int
    avg_sellout_step: float
    avg_suggested_increase: float


def rank_opportunities(
    occurrences_by_product: dict[tuple[int, str], list[OpportunityOccurrence]],
    limit: int = 10,
) -> list[ProductOpportunitySummary]:
    """商品ごとに集計し、推奨追加在庫数の平均が大きい順に上位 limit 件を返す。
    該当0件（空リスト）の商品はキーごと渡さないこと（結果に含めたくなければ渡さない）。
    """
    summaries = [
        ProductOpportunitySummary(
            product_id=product_id,
            product_name=product_name,
            occurrence_count=len(occs),
            avg_sellout_step=sum(o.sellout_step for o in occs) / len(occs),
            avg_suggested_increase=sum(o.suggested_increase for o in occs) / len(occs),
        )
        for (product_id, product_name), occs in occurrences_by_product.items()
        if occs
    ]
    summaries.sort(key=lambda s: s.avg_suggested_increase, reverse=True)
    return summaries[:limit]


def build_step_records(
    log_steps: list[tuple[int, int]], recommendation_steps: list[tuple[int, float]]
) -> list[StepRecord]:
    """PurchaseLog（全ステップの (step, quantity)）と DiscountRecommendation
    （変化があったステップだけの (step, recommended_rate)）から、
    「そのステップの販売時に適用されていた値引き率」を含む StepRecord 列を作る。

    値引き提案はそのステップの販売**後**に決まり、次のステップから効いてくる
    （services/simulation.py の run_simulation と同じ順序）ため、
    このステップの記録を作ってから rate を更新する。
    """
    rate_after_step: dict[int, float] = dict(recommendation_steps)
    current_rate = 0.0
    records: list[StepRecord] = []
    for step, quantity in sorted(log_steps, key=lambda x: x[0]):
        records.append(StepRecord(step=step, quantity=quantity, recommended_rate=current_rate))
        if step in rate_after_step:
            current_rate = rate_after_step[step]
    return records
