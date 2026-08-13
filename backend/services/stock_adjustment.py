"""在庫の自動調整（docs/spec.md §5.7）。

早期完売（機会損失・`services/opportunity.py`）・売れ残り（過剰在庫・`services/overstock.py`）を、
過去の履歴全体を集計する`/opportunities`・`/overstock`とは別に、**その回の結果だけ**を見て
シミュレーション終了時点でその場で`Product.initial_stock`へ反映する。

DBもネットワークも触らない純関数の集まり。
"""

from dataclasses import dataclass
from typing import Literal

from services.opportunity import StepRecord, build_step_records, detect_opportunity
from services.overstock import detect_overstock

#: 提案量をそのまま反映すると振れ幅が大きすぎるため、1回の実行では半分だけ反映する（§5.7）
DAMPING_FACTOR = 0.5


@dataclass
class StockAdjustment:
    delta: int  # 正なら増加、負なら減少
    new_initial_stock: int
    # opportunity（機会損失で増加）/ overstock（過剰在庫で減少）。§5.8の履歴ログの分類に使う
    reason: Literal["opportunity", "overstock"]


def compute_stock_adjustment(
    initial_stock: int,
    log_steps: list[tuple[int, int]],
    recommendation_steps: list[tuple[int, float]],
) -> StockAdjustment | None:
    """1回のシミュレーションの1商品ぶんのステップデータから、在庫調整量を計算する。

    `log_steps`は(step, quantity)の全ステップぶん、`recommendation_steps`は
    値引きが変化した(step, recommended_rate)だけ（`is_new_recommendation=True`のもの）。
    機会損失と過剰在庫はdetect_opportunity/detect_overstockの判定条件が両立しないため、
    該当してもどちらか一方だけになる。どちらにも該当しなければNone（在庫は変更しない）。
    """
    step_records: list[StepRecord] = build_step_records(log_steps, recommendation_steps)

    opportunity = detect_opportunity(step_records, initial_stock)
    if opportunity is not None:
        damped = max(1, round(opportunity.suggested_increase * DAMPING_FACTOR))
        return StockAdjustment(
            delta=damped, new_initial_stock=initial_stock + damped, reason="opportunity"
        )

    quantities = [quantity for _, quantity in log_steps]
    rates = [rate for _, rate in recommendation_steps]
    overstock = detect_overstock(rates, quantities, initial_stock)
    if overstock is not None:
        damped = max(1, round(overstock.suggested_decrease * DAMPING_FACTOR))
        new_stock = max(1, initial_stock - damped)  # 0以下にはしない（§5.2の対象外フィルタに落ちるため）
        return StockAdjustment(
            delta=new_stock - initial_stock, new_initial_stock=new_stock, reason="overstock"
        )

    return None
