"""商品追加時の事前分布の自動生成（docs/spec.md §5.4）。

DBもネットワークも触らない純関数。seed/products.jsonを作ったときと同じ倍率テーブルを使う。
"""

from services.simulation import condition_key
from models import WEATHERS, DAY_TYPES

BETA = 2.0

WEATHER_MULTIPLIER: dict[str, float] = {"晴れ": 1.2, "曇り": 1.0, "雨": 0.7}
DAY_TYPE_MULTIPLIER: dict[str, float] = {"平日": 1.0, "休日": 1.3}
EVENT_MULTIPLIER: dict[bool, float] = {False: 1.0, True: 1.4}
#: 長期休み（大学の休み・帰省の期間。docs/spec.md §5.13）の需要の倍率。学生の多い町で学生が帰省すると
#: 客が減る、という本人の指摘をもとにした仮の値
VACATION_MULTIPLIER: dict[bool, float] = {False: 1.0, True: 0.7}


def generate_true_demand(base_demand: float) -> dict[str, float]:
    """お客さんの本当の需要（docs/spec.md §5.14）。事前分布と同じ倍率表で、条件ごとの
    1ステップあたりの平均需要を返す（＝最初の予測は本当の需要と同じ平均から始まる）。"""
    return {k: round(v["alpha"] / v["beta"], 4) for k, v in generate_prior_demand(base_demand).items()}


def generate_prior_demand(base_demand: float) -> dict[str, dict[str, float]]:
    """基準需要（平日・晴れ・イベントなしの1step平均需要）から24条件ぶん
    （天気3×曜日2×イベント2×長期休み2。docs/spec.md §5.13）のガンマ分布パラメータ
    （alpha, beta）を計算する。betaは2.0固定。
    """
    result: dict[str, dict[str, float]] = {}
    for weather in WEATHERS:
        for day_type in DAY_TYPES:
            for has_event in (False, True):
                for is_long_vacation in (False, True):
                    multiplier = (
                        WEATHER_MULTIPLIER[weather]
                        * DAY_TYPE_MULTIPLIER[day_type]
                        * EVENT_MULTIPLIER[has_event]
                        * VACATION_MULTIPLIER[is_long_vacation]
                    )
                    mean = base_demand * multiplier
                    key = condition_key(weather, day_type, has_event, is_long_vacation)
                    result[key] = {"alpha": round(mean * BETA, 4), "beta": BETA}
    return result
