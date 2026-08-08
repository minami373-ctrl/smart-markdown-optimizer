"""ベイズ更新シミュレーションエンジン（docs/spec.md §5.2, §5.3）。

DB もネットワークも触らない純関数の集まり。ガンマ分布を共役事前分布とし、
値引き率を「既知の露出（exposure）」として扱うガンマ-ポアソン更新を行う
（値引きで需要が multiplier 倍になる → その分だけ観測の重み beta を増やす）。

MAP推定（最大事後確率推定）はガンマ分布の最頻値 (alpha-1)/beta を使う
（alpha<=1 のときは 0 が最頻値になるので 0 に丸める）。
"""

import random
from dataclasses import dataclass, field

STEPS = 40
DISCOUNT_STEP_UNIT = 0.10  # 弾力性は「値引き10%あたり」の倍率として定義されている
MIN_DISCOUNT = 0.0
MAX_DISCOUNT = 0.70
#: 前回提案からこの幅（%pt）以上変化しないと新しい提案として記録しない
MIN_RATE_CHANGE = 0.05


def condition_key(weather: str, day_type: str, has_event: bool) -> str:
    return f"{weather}_{day_type}_{'あり' if has_event else 'なし'}"


def discount_multiplier(discount_rate: float, elasticity: float) -> float:
    """値引き率から需要の倍率を返す。0%引きなら1.0倍。"""
    return 1.0 + elasticity * (discount_rate / DISCOUNT_STEP_UNIT)


def posterior_mode(alpha: float, beta: float) -> float:
    """ガンマ分布の最頻値（MAP推定量）。alpha<=1 なら 0。"""
    if alpha <= 1.0 or beta <= 0:
        return 0.0
    return (alpha - 1.0) / beta


@dataclass
class ProductInput:
    product_id: int
    name: str
    initial_stock: int
    elasticity: float
    prior_alpha: float
    prior_beta: float


@dataclass
class ProductStepResult:
    product_id: int
    step: int
    quantity: int
    remaining_stock: int
    recommended_rate: float
    posterior_mean: float  # 事後分布に基づく「期待残数」（需要率そのものではない）
    is_new_recommendation: bool
    # 需要率の事後分布パラメータ（画面で確率密度曲線を描くために公開する。更新後の値）
    posterior_alpha: float
    posterior_beta: float


@dataclass
class ProductFinalResult:
    product_id: int
    final_waste_rate: float
    achieved: bool


@dataclass
class SimulationOutcome:
    steps: list[ProductStepResult] = field(default_factory=list)
    finals: list[ProductFinalResult] = field(default_factory=list)


def _required_discount_rate(
    remaining_stock: int,
    remaining_steps: int,
    target_waste_stock: float,
    baseline_rate: float,
    elasticity: float,
) -> float:
    """残り時間で目標廃棄率以内に売り切るために必要な値引き率を計算する。"""
    if remaining_steps <= 0 or remaining_stock <= 0:
        return 0.0

    required_demand = remaining_stock - target_waste_stock
    if required_demand <= 0:
        return 0.0

    baseline_projected = baseline_rate * remaining_steps
    if baseline_projected <= 0:
        # 事後分布の期待需要が0なら、割ると0除算になるため上限値引きを提案する
        # （ここに来た時点で required_demand > 0 は確定済み。上の early return 参照）
        return MAX_DISCOUNT

    if baseline_projected >= required_demand:
        return 0.0

    needed_multiplier = required_demand / baseline_projected
    if elasticity <= 0:
        return 0.0
    rate = (needed_multiplier - 1.0) * DISCOUNT_STEP_UNIT / elasticity
    return max(MIN_DISCOUNT, min(MAX_DISCOUNT, rate))


def run_simulation(
    products: list[ProductInput],
    target_waste_rate: float,
    seed: int,
    steps: int = STEPS,
) -> SimulationOutcome:
    """全商品・全ステップぶんのシミュレーションを実行し、結果を返す（DBは触らない）。

    乱数は `seed` から決定的に導出する。同じ products・target_waste_rate・seed
    なら常に同じ結果になる。商品ごとに独立した乱数列を持つため、他の商品の有無や
    順序が変わっても、ある商品の結果は変わらない（商品間で影響し合わない）。
    """
    outcome = SimulationOutcome()

    # 初期在庫0の商品は購入ログ生成をスキップする（0除算を避ける。docs/spec.md §5.2）
    active_products = [p for p in products if p.initial_stock > 0]

    states = {
        p.product_id: {
            "alpha": p.prior_alpha,
            "beta": p.prior_beta,
            "remaining": p.initial_stock,
            "discount": 0.0,
            "last_recommended": 0.0,
            # 商品ごとに独立した乱数列（他商品の有無・順序に依存しない）
            "rng": random.Random(f"{seed}-{p.product_id}"),
        }
        for p in active_products
    }

    for step in range(steps):
        remaining_steps = steps - step
        for p in active_products:
            state = states[p.product_id]

            # 1) 現在の値引き率で購入を生成（在庫を超えない）。
            #    実際の購入個数を左右する「真の需要率」は事後分布の平均（期待値）を使う。
            #    MAP（最頻値）は alpha<=1 で 0 に潰れてしまい、需要がゼロに固定されて
            #    しまうため、購入生成には使わない（MAPは §5.3 の値引き計算専用）
            demand_rate = state["alpha"] / state["beta"]
            multiplier = discount_multiplier(state["discount"], p.elasticity)
            true_rate = demand_rate * multiplier
            quantity = _sample_poisson(state["rng"], true_rate)
            quantity = min(quantity, state["remaining"])
            state["remaining"] -= quantity

            # 2) ベイズ更新（値引きによる需要倍率を「既知の露出」として扱う）
            state["alpha"] += quantity
            state["beta"] += multiplier

            # 3) 次の値引き率を計算。ここは仕様どおりMAP推定（ガンマ分布の最頻値）を使う
            updated_mean = state["alpha"] / state["beta"]
            updated_mode = posterior_mode(state["alpha"], state["beta"])
            target_waste_stock = target_waste_rate * p.initial_stock
            candidate_rate = _required_discount_rate(
                remaining_stock=state["remaining"],
                remaining_steps=remaining_steps - 1,
                target_waste_stock=target_waste_stock,
                baseline_rate=updated_mode,
                elasticity=p.elasticity,
            )

            is_new = abs(candidate_rate - state["last_recommended"]) >= MIN_RATE_CHANGE
            if is_new:
                state["last_recommended"] = candidate_rate
            state["discount"] = state["last_recommended"]

            # 画面に出す「事後分布の期待残数」（docs/spec.md §4①・§6）。
            # 「期待」＝平均を使う（残り時間で見込まれる需要の平均を在庫から差し引いた値）
            expected_remaining = max(
                state["remaining"] - updated_mean * (remaining_steps - 1), 0.0
            )

            outcome.steps.append(
                ProductStepResult(
                    product_id=p.product_id,
                    step=step,
                    quantity=quantity,
                    remaining_stock=state["remaining"],
                    recommended_rate=state["last_recommended"],
                    posterior_mean=expected_remaining,
                    is_new_recommendation=is_new,
                    posterior_alpha=state["alpha"],
                    posterior_beta=state["beta"],
                )
            )

    for p in active_products:
        state = states[p.product_id]
        final_waste_rate = state["remaining"] / p.initial_stock
        outcome.finals.append(
            ProductFinalResult(
                product_id=p.product_id,
                final_waste_rate=final_waste_rate,
                achieved=final_waste_rate <= target_waste_rate,
            )
        )

    return outcome


def _sample_poisson(rng: random.Random, rate: float) -> int:
    """Knuth のアルゴリズムでポアソン分布から1件サンプリングする（stdlib random のみで完結）。"""
    if rate <= 0:
        return 0
    l = pow(2.718281828459045, -rate)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= l:
            return k - 1
