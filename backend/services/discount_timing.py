"""値引きタイミングの傾向分析（docs/spec.md §5.10）。

過去の全シミュレーション履歴から、天気・曜日・イベント有無の条件ごとに、値引きが平均何
ステップ目から始まっているかを集計する。「雨の日は値引きが早まる」という主張を、単発の
デモではなく履歴の蓄積で裏付けるための機能（/opportunities・/overstockと同じ
「履歴全体を俯瞰する」方針だが、商品ごとではなく条件ごとに集計する点が違う）。

DBもネットワークも触らない純関数の集まり。
"""

from dataclasses import dataclass


def first_discount_step(recommendation_steps: list[tuple[int, float]]) -> int | None:
    """1つの (run, product) ぶんの DiscountRecommendation（変化があったステップだけの
    (step, recommended_rate)）から、値引きが最初に必要になったステップを返す。

    DiscountRecommendationは値引き率が変化した瞬間だけを記録している（docs/spec.md
    §5.2 step2c）ため、recommended_rate > 0 の最小stepがそのまま「初回値引きステップ」になる。
    該当する行が無ければ、その回はその商品に値引きが一度も発生しなかったことを意味しNoneを返す。
    """
    positive_steps = [step for step, rate in recommendation_steps if rate > 0]
    return min(positive_steps) if positive_steps else None


@dataclass
class ConditionTimingSummary:
    weather: str
    day_type: str
    has_event: bool
    sample_count: int  # 該当する (run_id, product_id) の組の総数
    discounted_count: int  # そのうち値引きが1回でも発生した組の数
    avg_first_discount_step: float | None  # discounted_count=0ならNone


def summarize_condition_timing(
    weather: str,
    day_type: str,
    has_event: bool,
    first_discount_steps: list[int | None],
) -> ConditionTimingSummary:
    """1つの条件（天気・曜日・イベント有無）ぶんの初回値引きステップのリストから集計する。
    リストの各要素は (run_id, product_id) の組1つぶんの first_discount_step()の結果
    （値引きが無かった組はNoneのまま渡すこと。平均の計算からは除外される）。
    """
    sample_count = len(first_discount_steps)
    discounted_steps = [s for s in first_discount_steps if s is not None]
    avg = sum(discounted_steps) / len(discounted_steps) if discounted_steps else None
    return ConditionTimingSummary(
        weather=weather,
        day_type=day_type,
        has_event=has_event,
        sample_count=sample_count,
        discounted_count=len(discounted_steps),
        avg_first_discount_step=avg,
    )
