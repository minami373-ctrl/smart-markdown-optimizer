"""固定スケジュール値引きとの比較（docs/spec.md §5.9）。

企画の出発点（値引きのタイミングが「19時=3割引・20時半=半額」で固定化されていて
機会損失・廃棄ロスが起きている。docs/spec.md §1）を、実際の数字で裏付けるための機能。
動的値引き（services/simulation.py の run_simulation）と同じ乱数シードで、
固定スケジュールの値引きポリシーによるシミュレーションを別に走らせる。

DBもネットワークも触らない純関数の集まり（run_simulationと同じ方針）。
購入生成・ガンマ-ポアソン更新のロジックはrun_simulationと重複させず、
services.simulationの_sample_poisson・discount_multiplierをそのまま使い回す。
"""

import random
from dataclasses import dataclass, field

from services.simulation import (
    MAX_DISCOUNT,
    STEPS,
    ZUBARI_START_STEP,
    ProductInput,
    _sample_poisson,
    discount_multiplier,
)

#: 固定スケジュールの値引きタイミング。frontend/src/lib/clock.tsのstepToClockTime
#: （営業時間10:00〜22:00・40ステップの換算。2026-11-26改訂）を逆算した値（docs/spec.md §5.9）：
#: 19:00 → (19:00-10:00)/(22:00-10:00)*40 = 540/720*40 = 30
#: 20:30 → (20:30-10:00)/(22:00-10:00)*40 = 630/720*40 = 35
FIXED_SCHEDULE_30_STEP = 30
FIXED_SCHEDULE_50_STEP = 35
#: 21時のズバリ引き（実際の売り場の手順。2026-11-26追加）。固定スケジュール側は売れ行きを見ないので、
#: 21時を過ぎたら下限（元の値段の75%引き）まで一気に下げる
FIXED_SCHEDULE_ZUBARI_STEP = ZUBARI_START_STEP


def _fixed_schedule_rate(step: int) -> float:
    """固定スケジュールの値引き率。19時相当のステップで30%、20時半相当のステップで半額、
    21時を過ぎたステップでズバリ引き（下限の75%引き）。
    時刻だけで機械的に決まり、事後分布や実際の遅れといった判断は一切使わない
    （これが動的値引きとの対比で示したい固定スケジュールの特徴そのもの）。
    """
    if step >= FIXED_SCHEDULE_ZUBARI_STEP:
        return MAX_DISCOUNT
    if step >= FIXED_SCHEDULE_50_STEP:
        return 0.50
    if step >= FIXED_SCHEDULE_30_STEP:
        return 0.30
    return 0.0


@dataclass
class ScheduleStepResult:
    step: int
    quantity: int
    remaining_stock: int
    recommended_rate: float


@dataclass
class ScheduleOutcome:
    steps: list[ScheduleStepResult] = field(default_factory=list)
    final_waste_rate: float = 0.0


def run_fixed_schedule_simulation(
    product: ProductInput, seed: int, steps: int = STEPS
) -> ScheduleOutcome:
    """固定スケジュールの値引きポリシーで1商品ぶんシミュレーションする（純関数）。

    run_simulationと**同じ乱数シード**（f"{seed}-{product_id}"）を使うため、値引き率が
    違って購入個数が分岐するまでは同じ乱数列から出発する（docs/spec.md §5.9）。
    """
    outcome = ScheduleOutcome()
    if product.initial_stock <= 0:
        # 初期在庫0は購入ログ生成をスキップする（run_simulationのactive_productsフィルタと同じ）
        return outcome

    alpha = product.prior_alpha
    beta = product.prior_beta
    remaining = product.initial_stock
    rng = random.Random(f"{seed}-{product.product_id}")

    for step in range(steps):
        rate = _fixed_schedule_rate(step)

        # 在庫が残っているステップだけ購入を生成しベイズ更新する。完売後は打ち切りデータの
        # 扱いで更新を止める（services/simulation.pyのrun_simulationと同じ。§5.2 step2b）
        if remaining > 0:
            demand_rate = alpha / beta
            multiplier = discount_multiplier(rate, product.elasticity)
            true_rate = demand_rate * multiplier
            quantity = _sample_poisson(rng, true_rate)
            quantity = min(quantity, remaining)
            remaining -= quantity

            alpha += quantity
            beta += multiplier
        else:
            quantity = 0

        outcome.steps.append(
            ScheduleStepResult(
                step=step,
                quantity=quantity,
                remaining_stock=remaining,
                recommended_rate=rate,
            )
        )

    outcome.final_waste_rate = remaining / product.initial_stock
    return outcome
