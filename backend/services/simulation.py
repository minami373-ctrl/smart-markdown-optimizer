"""ベイズ更新シミュレーションエンジン（docs/spec.md §5.2, §5.3）。

DB もネットワークも触らない純関数の集まり。ガンマ分布を共役事前分布とし、
値引き率を「既知の露出（exposure）」として扱うガンマ-ポアソン更新を行う
（値引きで需要が multiplier 倍になる → その分だけ観測の重み beta を増やす）。

値引き率の計算には事後分布の平均 alpha/beta を使う（2026-08-14改訂。docs/spec.md §5.2 step2c）。
以前はMAP推定（ガンマ分布の最頻値 (alpha-1)/beta）を使っていたが、alpha<=1（観測が少ない
開店直後によく起こる）だと最頻値がちょうど0に潰れてしまい、「今のペースなら一日中売れない」
という誤判定でいきなり最大値引き（75%）が提案される不具合があった。平均は観測が少なくても
0に潰れないため、序盤は緩やかに様子を見る判定になる。

さらに、完売後もベイズ更新を続けない（§5.2 step2b。打ち切りデータの扱い）も同日に追加した。
値引きは下げない仕様（単調増加）のため、序盤にたまたま数ステップ売れなかっただけで大きな
値引きに固定されてしまうケースが実測で確認され、これを緩和するための修正。

値引きが必要かどうかの「判定」と「値引き幅の計算」を分離した（2026-08-15改訂。docs/spec.md
§5.3）。以前は「事後分布の平均から残り時間の必要ペースを毎ステップ計算し直す」という
見込みベースの判定だったが、実店舗の感覚（まだ実際に売れ残っているか確定していないのに
先回りして値引きを決めているように見える）と合わないという指摘を受けた。判定は
「実際に売れた個数」対「目標ペースで売れているべき個数」という実績ベースに変え、
判定を通った場合の値引き幅の計算だけに事後分布の平均を使う。これに伴い、旧来の
GRACE_PERIOD_STEPS（開店直後の様子見期間）は実績ベースの判定に役割を吸収されたため削除した。

値引き感度（elasticity）による需要倍率の式も比例から2乗に変更した（2026-08-15改訂）。
「半額になった瞬間に速攻売れる」という実店舗の感覚に対し、比例の式では大きい値引きの
効きが弱すぎたため。
"""

import random
from dataclasses import dataclass, field

STEPS = 40
DISCOUNT_STEP_UNIT = 0.10  # 値引き感度(elasticity)は「値引き10%あたり」の倍率として定義されている
MIN_DISCOUNT = 0.0
MAX_DISCOUNT = 0.75
#: 前回提案からこの幅（%pt）以上変化しないと新しい提案として記録しない。
#: DISCOUNT_TIERS導入後は隣接する刻み同士の差（最小20pt）が必ずこれを上回るため、
#: 実質「刻みが変わったかどうか」と同じ判定になっている（意図的な残置。壊れてはいない）
MIN_RATE_CHANGE = 0.05
#: 21時より前に使える値引きの刻み：30%引き・半額（docs/spec.md §5.3。2026-11-26改訂）
PRE_ZUBARI_TIERS: tuple[float, ...] = (0.0, 0.30, 0.50)
#: ズバリ引き（値段を直接決める値引き）が使えるようになる最初のステップ。営業時間10:00〜22:00・
#: 40ステップ（1ステップ18分）で、21:00を過ぎた最初のステップ＝37（21:06）。
#: このステップ以降に決まる値引きだけが半額より大きくなれる
ZUBARI_START_STEP = 37
#: ズバリ引きの刻み：半額より下を5%ずつ、下限は元の値段の75%引き（MAX_DISCOUNT）。
#: 画面にはこの率から計算した10円単位の値段で表示する（frontend/src/lib/discountLabel.ts）
ZUBARI_TIERS: tuple[float, ...] = (0.55, 0.60, 0.65, 0.70, MAX_DISCOUNT)
#: 値引き率が取りうる値の全体（DiscountRecommendation.recommended_rateの値の範囲）
DISCOUNT_TIERS: tuple[float, ...] = PRE_ZUBARI_TIERS + ZUBARI_TIERS
#: 値引きを検討し始める閾値（docs/spec.md §5.3「トリガー：見込みではなく実際の遅れで判定する」）。
#: 「実際に売れた個数」が「目標ペースで売れているべき個数（初期在庫の目標達成分×経過割合）」
#: よりinitial_stockのこの割合以上少なければ値引き幅の計算に進む。2026-08-15追加。
#: 数ステップぶんの偶然のブレでは反応しないための遊びで、開店直後は目標ペース自体が小さいため
#: このマージンだけで序盤の過敏な反応も抑えられる（旧GRACE_PERIOD_STEPSの役割を吸収した）
SHORTFALL_MARGIN_RATE = 0.15


def condition_key(weather: str, day_type: str, has_event: bool) -> str:
    return f"{weather}_{day_type}_{'あり' if has_event else 'なし'}"


def discount_multiplier(discount_rate: float, elasticity: float) -> float:
    """値引き率から需要の倍率を返す。0%引きなら1.0倍。

    値引きの刻み(10%単位)ぶんの2乗で効かせる（2026-08-15改訂。docs/spec.md §5.3）。
    以前は比例（1乗）だったが、「半額になった瞬間に速攻売れる」という実店舗の感覚に対し
    効きが弱すぎたため、大きい値引きほど急激に需要が伸びる非線形な式に変更した。
    """
    return 1.0 + elasticity * (discount_rate / DISCOUNT_STEP_UNIT) ** 2


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
    # 終了時点の事後分布（docs/spec.md §5.2 step4「学習の継続」で次回の事前分布として使う）
    final_alpha: float
    final_beta: float


@dataclass
class SimulationOutcome:
    steps: list[ProductStepResult] = field(default_factory=list)
    finals: list[ProductFinalResult] = field(default_factory=list)


def _is_behind_pace(
    actual_sold: int,
    initial_stock: int,
    target_waste_stock: float,
    elapsed_steps: int,
    total_steps: int,
) -> bool:
    """「実際に売れた個数」が「目標ペースで売れているべき個数」より
    `SHORTFALL_MARGIN_RATE`ぶん以上少なければTrue（docs/spec.md §5.3「トリガー」）。

    「目標ペースで売れているべき個数」は、目標廃棄率を満たすために必要な販売数
    （initial_stock - target_waste_stock）を、開店から閉店まで一定のペースで売ると
    仮定して経過ステップの割合ぶんだけ直線的に案分した値。事後分布などの統計的な見込みは
    一切使わず、その回で実際に生成された購入ログの数（actual_sold）だけを見る。
    """
    if total_steps <= 0:
        return False
    units_to_sell_total = initial_stock - target_waste_stock
    if units_to_sell_total <= 0:
        return False
    expected_sold_by_now = units_to_sell_total * (elapsed_steps / total_steps)
    shortfall = expected_sold_by_now - actual_sold
    margin = initial_stock * SHORTFALL_MARGIN_RATE
    return shortfall > margin


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


def _snap_to_tier(rate: float, allow_zubari: bool = True) -> float:
    """連続値の値引き率を、使える値引きの刻みのうちその値以上で最小のものに
    切り上げる（docs/spec.md §5.3）。

    allow_zubari=False（21時より前。ZUBARI_START_STEP未満）のときは30%引き・半額の
    2段階だけを使い、半額を超える値は半額に抑える（ズバリ引きは21時以降だけ）。

    切り下げではなく切り上げなのは、目標廃棄率を満たすのに必要な値引きが刻みの間の
    半端な値になったとき、切り下げると値引きが足りず目標未達になりやすいため
    （安全側＝売り切りやすい側に倒す）。rateが最大の刻みを超えていたら最大値に丸める。
    """
    tiers = DISCOUNT_TIERS if allow_zubari else PRE_ZUBARI_TIERS
    for tier in tiers:
        if rate <= tier:
            return tier
    return tiers[-1]


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

            # 1)〜2) 在庫が残っているステップだけ購入を生成しベイズ更新する。
            #    在庫が0（完売済み）のステップは「これ以上売れたかどうか」を観測できない
            #    （打ち切りデータ）。ここをガードせず更新を続けると、完売後も
            #    beta（既知の露出）だけがステップごとに際限なく増え続け、alphaは増えないため、
            #    事後分布の平均 alpha/beta が実際の需要より大幅に低く見えてしまう
            #    （2026-08-14に発覚。実際に完売直後から残り39ステップぶんbetaが積み上がり、
            #    「学習の継続」で次回の事前分布が回を追うごとに下振れしていく不具合があった）
            if state["remaining"] > 0:
                # 実際の購入個数を左右する「真の需要率」は事後分布の平均（期待値）を使う
                # （値引き率の計算に使う updated_mean と同じ考え方。§5.3参照）
                demand_rate = state["alpha"] / state["beta"]
                multiplier = discount_multiplier(state["discount"], p.elasticity)
                true_rate = demand_rate * multiplier
                quantity = _sample_poisson(state["rng"], true_rate)
                quantity = min(quantity, state["remaining"])
                state["remaining"] -= quantity

                # ベイズ更新（値引きによる需要倍率を「既知の露出」として扱う）
                state["alpha"] += quantity
                state["beta"] += multiplier
            else:
                quantity = 0

            # 3) 次の値引き率を計算。「判定」と「値引き幅」を分離した（2026-08-15改訂。
            #    docs/spec.md §5.3）。判定は実際に売れた個数と目標ペースの比較（統計的な
            #    見込みを使わない、実績ベース）。値引き幅の計算だけ事後分布の平均を使う
            updated_mean = state["alpha"] / state["beta"]
            target_waste_stock = target_waste_rate * p.initial_stock
            actual_sold = p.initial_stock - state["remaining"]
            behind_pace = _is_behind_pace(
                actual_sold=actual_sold,
                initial_stock=p.initial_stock,
                target_waste_stock=target_waste_stock,
                elapsed_steps=step + 1,
                total_steps=steps,
            )
            if not behind_pace:
                # まだ目標ペースの範囲内（またはマージン内の軽微な遅れ）なので、
                # 値引き幅の計算そのものを行わない（見込みで先回りしない）
                continuous_rate = 0.0
            else:
                continuous_rate = _required_discount_rate(
                    remaining_stock=state["remaining"],
                    remaining_steps=remaining_steps - 1,
                    target_waste_stock=target_waste_stock,
                    baseline_rate=updated_mean,
                    elasticity=p.elasticity,
                )
            # 連続値のままでは提案しない。実店舗の値引きの刻みに丸める（docs/spec.md §5.3）
            #    ズバリ引き（半額より大きい値引き）は21時を過ぎたステップ以降だけ（2026-11-26）
            snapped_rate = _snap_to_tier(
                continuous_rate, allow_zubari=step >= ZUBARI_START_STEP
            )
            # 値引きシールは一度貼ったら剥がせない、という物理的な制約の再現：
            # 値引き率は一度上がったら下がらない（前のステップ以上にしかならない）
            candidate_rate = max(snapped_rate, state["last_recommended"])

            # candidate_rate は必ず last_recommended 以上（値引きは下げないため）。
            # 差は常に非負なので abs() は不要
            #    ズバリ引きの刻みは5%幅なので、浮動小数点の誤差（0.60-0.55=0.0499…）で
            #    変化を見落とさないよう、差を丸めてから比べる
            is_new = round(candidate_rate - state["last_recommended"], 6) >= MIN_RATE_CHANGE
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
                final_alpha=state["alpha"],
                final_beta=state["beta"],
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
