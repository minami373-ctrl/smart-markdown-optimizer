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

import math
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
#: 半額。これより大きい値引き（ズバリ引き）だけがナイトマネージャーの承認待ちになる（§5.11）
HALF_PRICE_RATE = 0.50
#: 30%引きを最低何ステップ続けてから半額に上げるか（docs/spec.md §5.3。2026-11-26追加）。
#: 3ステップ＝54分。実際の売り場は19時に30%引き・20時半に半額で、30%引きで売れる時間がある
MIN_STEPS_AT_30 = 3
#: 値引き率が取りうる値の全体（DiscountRecommendation.recommended_rateの値の範囲）
DISCOUNT_TIERS: tuple[float, ...] = PRE_ZUBARI_TIERS + ZUBARI_TIERS
#: 値引きを検討し始める閾値（docs/spec.md §5.3「トリガー：見込みではなく実際の遅れで判定する」）。
#: 「実際に売れた個数」が「目標ペースで売れているべき個数（初期在庫の目標達成分×経過割合）」
#: よりinitial_stockのこの割合以上少なければ値引き幅の計算に進む。2026-08-15追加。
#: 数ステップぶんの偶然のブレでは反応しないための遊びで、開店直後は目標ペース自体が小さいため
#: このマージンだけで序盤の過敏な反応も抑えられる（旧GRACE_PERIOD_STEPSの役割を吸収した）
SHORTFALL_MARGIN_RATE = 0.15

#: 1日の売れ方（docs/spec.md §5.12。2026-11-26追加）。売り場の聞き取りをもとにした、時間帯ごとの
#: 需要の重み（値は相対値。demand_curveで1ステップあたり平均1.0になるよう正規化する）。
#: 12時が一番の山、16時に補充、17時は12時より少ないが定価で売れる、19時以降は値引きで売る時間帯。
#: (その時間帯が終わる時刻[分], 重み)
_HOURLY_WEIGHTS: tuple[tuple[int, float], ...] = (
    (11 * 60, 0.6),  # 10:00〜11:00
    (12 * 60, 1.2),  # 11:00〜12:00
    (13 * 60, 2.0),  # 12:00〜13:00（昼の山）
    (16 * 60, 0.6),  # 13:00〜16:00
    (17 * 60, 0.9),  # 16:00〜17:00（補充）
    (18 * 60, 1.4),  # 17:00〜18:00（夕方の山）
    (19 * 60, 1.2),  # 18:00〜19:00
    (22 * 60, 0.8),  # 19:00〜22:00
)
BUSINESS_START_MINUTES = 10 * 60
BUSINESS_END_MINUTES = 22 * 60
#: 16時の補充（docs/spec.md §5.12）。16:00 = (16:00-10:00)/(22:00-10:00)*40 = ステップ20。
#: このステップの販売の前に補充分が並ぶ。値引きの判定もこのステップから始める（昼の値引きは無い）
RESTOCK_STEP = 20
#: 1日の在庫（Product.initial_stock）のうち朝に並べる割合。残りを16時に補充する。
#: 実際の割合は分からないため、いったん半分ずつにしている（本人と決定）
MORNING_STOCK_RATIO = 0.5
#: 値引きの判断を始める最初のステップ（§5.12）。17時台は夕方の山で定価で売れる（売り場の聞き取り）
#: ため、18時を過ぎた最初のステップ（27＝18:06）から判断する。夜の在庫は1商品あたり十数個と少なく、
#: 1〜2個の偶然の遅れで17時台に値引きしてしまうのを防ぐ
EARLIEST_DISCOUNT_STEP = 27


def demand_curve(steps: int = STEPS) -> list[float]:
    """各ステップの需要の重み（平均1.0）。ステップの開始時刻が入る時間帯の重みを使う。"""
    if steps <= 0:
        return []
    minutes_per_step = (BUSINESS_END_MINUTES - BUSINESS_START_MINUTES) / steps
    raw: list[float] = []
    for step in range(steps):
        minute = BUSINESS_START_MINUTES + minutes_per_step * step
        weight = _HOURLY_WEIGHTS[-1][1]
        for end, w in _HOURLY_WEIGHTS:
            if minute < end:
                weight = w
                break
        raw.append(weight)
    mean = sum(raw) / len(raw)
    return [w / mean for w in raw]


def split_stock(initial_stock: int) -> tuple[int, int]:
    """1日の在庫を(朝に並べる分, 16時に補充する分)に分ける。朝の分は切り上げ。"""
    morning = initial_stock - int(initial_stock * (1 - MORNING_STOCK_RATIO))
    return morning, initial_stock - morning


def condition_key(
    weather: str, day_type: str, has_event: bool, is_long_vacation: bool = False
) -> str:
    """事前分布の条件キー。長期休み（docs/spec.md §5.13。2026-11-26追加）の日は末尾に
    `_長期休み`を付けた別のキーにする。ふだんの日のキーは以前と同じ形式のまま。"""
    key = f"{weather}_{day_type}_{'あり' if has_event else 'なし'}"
    return f"{key}_長期休み" if is_long_vacation else key


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
    #: お客さんの本当の需要（1ステップあたりの平均。docs/spec.md §5.14。2026-11-26追加）。
    #: 購入はこの値から作り、店側の予測（prior_alpha/prior_beta → 事後分布）はその購入を見て学ぶ。
    #: 省略時は事前分布の平均を本当の需要として固定する（予測は更新されても需要は動かない）
    true_rate: float | None = None


def _learn(alpha: float, beta: float, quantity: int, demanded: int, exposure: float) -> tuple[float, float]:
    """1ステップぶんのベイズ更新（ガンマ-ポアソン共役。docs/spec.md §5.2・§5.14）。

    ふつうは alpha += 売れた数、beta += 露出（時間帯の重み×値引きの需要倍率）。
    このステップで売り切れた（欲しい数より在庫が少なかった）ときは、本当に欲しかった数が分からない
    打ち切りデータになる。捨てると「需要が少なかったステップ」だけを学ぶ偏りが出るので、
    「売り切れるまでの間だけ売っていた」とみなし、露出をその割合（売れた数 ÷ 予測の需要）に縮めて学ぶ。
    """
    if demanded <= quantity:
        return alpha + quantity, beta + exposure
    mean = alpha / beta
    effective = exposure if mean <= 0 else min(exposure, quantity / mean)
    return alpha + quantity, beta + effective


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
    # 実際に売り場（モニター）に出す値引き率（docs/spec.md §5.11。2026-11-26追加）。
    # recommended_rateと同じく「次のステップから使う値」。30%・半額は提案と同時に出るが、
    # ズバリ引きはナイトマネージャーが承認するまで前の値引きのまま
    applied_rate: float = 0.0


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
    elapsed_fraction: float | None = None,
) -> bool:
    """「実際に売れた個数」が「目標ペースで売れているべき個数」より
    `SHORTFALL_MARGIN_RATE`ぶん以上少なければTrue（docs/spec.md §5.3「トリガー」）。

    「目標ペースで売れているべき個数」は、目標廃棄率を満たすために必要な販売数
    （initial_stock - target_waste_stock）を、開店から閉店まで一定のペースで売ると
    仮定して経過ステップの割合ぶんだけ直線的に案分した値。事後分布などの統計的な見込みは
    一切使わず、その回で実際に生成された購入ログの数（actual_sold）だけを見る。

    elapsed_fractionを渡すと、経過ステップの割合の代わりにそれを使う（2026-11-26追加。
    1日の売れ方〔demand_curve〕に沿った目標ペース。docs/spec.md §5.12）。
    """
    if total_steps <= 0:
        return False
    units_to_sell_total = initial_stock - target_waste_stock
    if units_to_sell_total <= 0:
        return False
    fraction = elapsed_steps / total_steps if elapsed_fraction is None else elapsed_fraction
    expected_sold_by_now = units_to_sell_total * fraction
    shortfall = expected_sold_by_now - actual_sold
    margin = initial_stock * SHORTFALL_MARGIN_RATE
    return shortfall > margin


def _required_discount_rate(
    remaining_stock: int,
    remaining_steps: float,
    target_waste_stock: float,
    baseline_rate: float,
    elasticity: float,
) -> float:
    """残り時間で目標廃棄率以内に売り切るために必要な値引き率を計算する。

    remaining_stepsは「残り時間の長さ」。1日の売れ方（docs/spec.md §5.12）を入れてからは、
    残りステップの需要の重みの合計（売れやすい時間帯ほど長く数える）を渡す。
    """
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
    # discount_multiplier（需要倍率 = 1 + 感度 × (値引き率 ÷ 10%)²）の逆算。
    # 2026-11-26修正：需要倍率の式は2026-08-15に1乗から2乗へ変えていたが、ここの逆算だけ
    # 1乗の式（(倍率-1) × 10% ÷ 感度）のまま残っていて、必要な値引き幅を大きめに見積もっていた
    rate = DISCOUNT_STEP_UNIT * math.sqrt((needed_multiplier - 1.0) / elasticity)
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
    approval_delay_steps: int = 0,
) -> SimulationOutcome:
    """全商品・全ステップぶんのシミュレーションを実行し、結果を返す（DBは触らない）。

    approval_delay_steps：ズバリ引き（半額より大きい値引き）の提案を、ナイトマネージャーが
    何ステップ後に承認するか（docs/spec.md §5.11）。0なら提案と同時に承認（以前と同じ動き）。
    30%引き・半額は自動で出るので、この値の影響を受けない。

    乱数は `seed` から決定的に導出する。同じ products・target_waste_rate・seed
    なら常に同じ結果になる。商品ごとに独立した乱数列を持つため、他の商品の有無や
    順序が変わっても、ある商品の結果は変わらない（商品間で影響し合わない）。
    """
    outcome = SimulationOutcome()

    # 初期在庫0の商品は購入ログ生成をスキップする（0除算を避ける。docs/spec.md §5.2）
    active_products = [p for p in products if p.initial_stock > 0]

    curve = demand_curve(steps)
    # その時点までの需要の重みの累積割合（目標ペースの計算に使う。§5.12）
    # 夜（16時の補充以降）の需要の重みの累積割合。値引きの判定は、補充した時点の在庫
    # （昼の売れ残り＋補充分）を、夜の売れ方に沿って売り切れているかで見る（§5.12）
    evening_weight = sum(curve[RESTOCK_STEP:]) if steps > RESTOCK_STEP else 0.0
    evening_cumulative = {
        i: sum(curve[RESTOCK_STEP : i + 1]) / evening_weight
        for i in range(RESTOCK_STEP, steps)
    } if evening_weight > 0 else {}

    states = {
        p.product_id: {
            "alpha": p.prior_alpha,
            "beta": p.prior_beta,
            # 店頭の在庫（朝の分）と、16時に補充する分（docs/spec.md §5.12）
            "remaining": split_stock(p.initial_stock)[0],
            "restock": split_stock(p.initial_stock)[1],
            # 16時の補充直後の在庫（夜の値引き判定の基準。補充するまではNone）
            "evening_stock": None,
            # お客さんの本当の需要（§5.14）。店側の予測とは別に持ち、学習しても変わらない
            "true_rate": p.true_rate if p.true_rate is not None else p.prior_alpha / p.prior_beta,
            "discount": 0.0,
            "last_recommended": 0.0,
            # モニターに出ている値引き率（承認済み）と、承認待ちのズバリ引き（率, 承認されるステップ）
            "applied": 0.0,
            "pending": None,
            # 最後に値引きを上げたステップ（30%引きを続けた長さを数えるため）
            "raised_at": -1,
            # 商品ごとに独立した乱数列（他商品の有無・順序に依存しない）
            "rng": random.Random(f"{seed}-{p.product_id}"),
        }
        for p in active_products
    }

    for step in range(steps):
        remaining_steps = steps - step
        weight = curve[step]
        for p in active_products:
            state = states[p.product_id]

            # 0) 16時の補充（§5.12）。昼の売れ残りと補充分を合わせて夜まで売る
            if step == RESTOCK_STEP:
                state["remaining"] += state["restock"]
                state["restock"] = 0
                state["evening_stock"] = state["remaining"]

            # 1)〜2) 在庫が残っているステップだけ購入を生成しベイズ更新する。
            #    在庫が0（完売済み）のステップは「これ以上売れたかどうか」を観測できない
            #    （打ち切りデータ）。ここをガードせず更新を続けると、完売後も
            #    beta（既知の露出）だけがステップごとに際限なく増え続け、alphaは増えないため、
            #    事後分布の平均 alpha/beta が実際の需要より大幅に低く見えてしまう
            #    （2026-08-14に発覚。実際に完売直後から残り39ステップぶんbetaが積み上がり、
            #    「学習の継続」で次回の事前分布が回を追うごとに下振れしていく不具合があった）
            if state["remaining"] > 0:
                # 購入はお客さんの本当の需要から作る（§5.14。2026-11-26修正）。以前は店側の予測
                # （事後分布の平均）から作っていたため、正しい答えが無く、予測がたまたま下がると
                # 翌日の客も減ってまた下がる…と0に向かって流れていった
                demand_rate = state["true_rate"]
                multiplier = discount_multiplier(state["discount"], p.elasticity)
                # その時間帯の売れやすさ（§5.12）も値引きと同じく「既知の露出」として掛ける
                exposure = weight * multiplier
                true_rate = demand_rate * exposure
                demanded = _sample_poisson(state["rng"], true_rate)
                quantity = min(demanded, state["remaining"])
                state["remaining"] -= quantity

                # ベイズ更新（値引きによる需要倍率と時間帯の重みを「既知の露出」として扱う）。
                # 売り切れたステップは打ち切りデータとして扱う（_learn。2026-11-26修正：以前は
                # 在庫で頭打ちになった売れた数をそのまま需要として学び、大きく下に見積もっていた）
                state["alpha"], state["beta"] = _learn(
                    state["alpha"], state["beta"], quantity, demanded, exposure
                )
            else:
                quantity = 0

            # 3) 次の値引き率を計算。「判定」と「値引き幅」を分離した（2026-08-15改訂。
            #    docs/spec.md §5.3）。判定は実際に売れた個数と目標ペースの比較（統計的な
            #    見込みを使わない、実績ベース）。値引き幅の計算だけ事後分布の平均を使う
            updated_mean = state["alpha"] / state["beta"]
            target_waste_stock = target_waste_rate * p.initial_stock
            # 1日の残り＝店頭在庫＋まだ補充していない分
            day_remaining = state["remaining"] + state["restock"]
            remaining_exposure = sum(curve[step + 1 :])
            evening_stock = state["evening_stock"]
            behind_pace = (
                step >= EARLIEST_DISCOUNT_STEP
                and evening_stock is not None
                and evening_stock > 0
                and _is_behind_pace(
                    actual_sold=evening_stock - day_remaining,
                    initial_stock=evening_stock,
                    target_waste_stock=target_waste_stock,
                    elapsed_steps=step + 1,
                    total_steps=steps,
                    elapsed_fraction=evening_cumulative[step],
                )
            )
            if not behind_pace:
                # 16時の補充より前は値引きしない（昼に値引きは絶対に無い。§5.12）。
                # 補充後も、1日の売れ方に沿った目標ペースの範囲内なら値引きしない
                # まだ目標ペースの範囲内（またはマージン内の軽微な遅れ）なので、
                # 値引き幅の計算そのものを行わない（見込みで先回りしない）
                continuous_rate = 0.0
            else:
                continuous_rate = _required_discount_rate(
                    remaining_stock=day_remaining,
                    remaining_steps=remaining_exposure,
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
            # 段階を飛ばさない（2026-11-26追加。§5.3）：半額までは「値引きなし→30%引き→半額」を
            # 1段ずつ上げ、30%引きは最低MIN_STEPS_AT_30ステップ続ける。ブラウザで確認したところ、
            # 18時台にいきなり半額になる商品が多く、実際の売り場の流れと合わなかったため。
            # 半額からズバリ引き（21時以降）は残り時間が少ないので、必要な刻みまで一度に上げてよい
            current = state["last_recommended"]
            if candidate_rate > current and current < HALF_PRICE_RATE:
                if current == 0.0:
                    candidate_rate = 0.30
                elif step - state["raised_at"] < MIN_STEPS_AT_30:
                    candidate_rate = current
                else:
                    candidate_rate = HALF_PRICE_RATE

            # candidate_rate は必ず last_recommended 以上（値引きは下げないため）。
            # 差は常に非負なので abs() は不要
            #    ズバリ引きの刻みは5%幅なので、浮動小数点の誤差（0.60-0.55=0.0499…）で
            #    変化を見落とさないよう、差を丸めてから比べる
            is_new = round(candidate_rate - state["last_recommended"], 6) >= MIN_RATE_CHANGE
            if is_new:
                state["last_recommended"] = candidate_rate
                state["raised_at"] = step
                if candidate_rate > HALF_PRICE_RATE:
                    # ズバリ引きはナイトマネージャーの承認待ち（docs/spec.md §5.11）。
                    # 新しいズバリ引きが出たら、承認待ちをその提案に置き換える
                    state["pending"] = (candidate_rate, step + approval_delay_steps)
                else:
                    # 30%引き・半額は自動で出る（承認待ちにしない）
                    state["applied"] = candidate_rate
            if state["pending"] is not None and step >= state["pending"][1]:
                state["applied"] = state["pending"][0]
                state["pending"] = None
            # 実際の購入に効くのはモニターに出ている値引き（承認済み）
            state["discount"] = state["applied"]

            # 画面に出す「事後分布の期待残数」（docs/spec.md §4①・§6）。
            # 「期待」＝平均を使う（残り時間で見込まれる需要の平均を在庫から差し引いた値）
            expected_remaining = max(day_remaining - updated_mean * remaining_exposure, 0.0)

            outcome.steps.append(
                ProductStepResult(
                    product_id=p.product_id,
                    step=step,
                    quantity=quantity,
                    # 1日の残り（店頭在庫＋まだ補充していない分。§5.12）。履歴の再構築
                    # （初期在庫−累計販売数）と同じ数え方にそろえる
                    remaining_stock=day_remaining,
                    recommended_rate=state["last_recommended"],
                    posterior_mean=expected_remaining,
                    is_new_recommendation=is_new,
                    posterior_alpha=state["alpha"],
                    posterior_beta=state["beta"],
                    applied_rate=state["applied"],
                )
            )

    for p in active_products:
        state = states[p.product_id]
        final_waste_rate = (state["remaining"] + state["restock"]) / p.initial_stock
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
