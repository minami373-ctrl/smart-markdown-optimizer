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

#: 営業時間10:00〜22:00を15分ごとに区切る（2026-11-26改訂：40ステップ・18分→48ステップ・15分。
#: 15分ごとに売れた数を集め、予測を更新し、値引きを「上げる」か「そのまま」か決める。docs/spec.md §5.19）
STEPS = 48
DISCOUNT_STEP_UNIT = 0.10  # 値引き感度(elasticity)は「値引き10%あたり」の倍率として定義されている
MIN_DISCOUNT = 0.0
MAX_DISCOUNT = 0.75
#: 前回提案からこの幅（%pt）以上変化しないと新しい提案として記録しない（5%刻みなので刻みが変わったら記録）
MIN_RATE_CHANGE = 0.05
#: 最初の値引き（§5.19。本人と決定）と、1回の判断で上げる幅
FIRST_DISCOUNT = 0.20
DISCOUNT_INCREMENT = 0.05
#: 値引き率が取りうる値：0%、20%〜75%の5%刻み
DISCOUNT_TIERS: tuple[float, ...] = (0.0,) + tuple(
    round(FIRST_DISCOUNT + DISCOUNT_INCREMENT * i, 2)
    for i in range(int(round((MAX_DISCOUNT - FIRST_DISCOUNT) / DISCOUNT_INCREMENT)) + 1)
)
#: これ以上の値引きはナイトマネージャーの承認を通す（半額より大きい値引きは取り返しがつかないため。§5.11）
APPROVAL_RATE = 0.55
#: 実際の売り場の21時（ズバリ引きの時刻）。固定スケジュール比較の固定側だけが使う（§5.9）
ZUBARI_START_STEP = 44

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
RESTOCK_STEP = 24  # 16:00（15分×24）
#: 1日の在庫（Product.initial_stock）のうち朝に並べる割合。残りを16時に補充する。
#: 実際の割合は分からないため、いったん半分ずつにしている（本人と決定）
MORNING_STOCK_RATIO = 0.5
#: 値引きの判断を始める最初のステップ（§5.12）。17時台は夕方の山で定価で売れる（売り場の聞き取り）
#: ため、18時を過ぎた最初のステップ（27＝18:06）から判断する。夜の在庫は1商品あたり十数個と少なく、
#: 1〜2個の偶然の遅れで17時台に値引きしてしまうのを防ぐ
EARLIEST_DISCOUNT_STEP = 32  # 18:00（15分×32）


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


#: 16時の補充（docs/spec.md §5.18。2026-11-26改訂）：売り場を「夜の標準の量」まで満杯にする。
#: 昼（16時まで）の売れ行きが予測より悪ければ少なめ、よければ多めにする倍率の範囲
RESTOCK_MIN_FACTOR = 0.7
RESTOCK_MAX_FACTOR = 1.3


def restock_amount(
    standard_evening: int, shelf_now: int, lunch_sold: int, lunch_predicted: float
) -> int:
    """16時に補充する数（§5.18）。

    夜の標準の量（standard_evening）×昼の売れ行きの倍率まで、売り場をいっぱいにする。
    昼の売れ残り（shelf_now）があれば、その分だけ補充を減らす（足りない分だけ作る）。
    倍率＝昼に売れた数÷昼の予測（0.7〜1.3に収める）。昼に売り切れた（店頭0）なら、欲しい人がもっと
    いたかもしれないので上限の1.3にする。
    """
    if shelf_now <= 0:
        factor = RESTOCK_MAX_FACTOR
    elif lunch_predicted <= 0:
        factor = 1.0
    else:
        factor = min(RESTOCK_MAX_FACTOR, max(RESTOCK_MIN_FACTOR, lunch_sold / lunch_predicted))
    target = round(standard_evening * factor)
    return max(0, target - shelf_now)


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


#: 古いデータを少しずつ忘れる割合（docs/spec.md §5.15。2026-11-26追加）。営業の終わりの事後分布を
#: 次の日の事前分布にするとき、alpha・betaの両方にこの値を掛ける。平均（予測そのもの）は変わらず、
#: 確信の強さだけが毎日1割ずつ弱まる＝おおよそ直近10日分を重く見る。状況がゆっくり変わったときに
#: 早く追いつくため（客層の変化など）。前もって分かる変化は長期休みの条件で、当日の変化は通知で扱う
FORGETTING_FACTOR = 0.9


#: 「いつもと違う」を判定するステップ（docs/spec.md §5.16。2026-11-26追加）。昼の山（12時台）が終わった
#: 13:00＝ステップ10の販売の後。夜の作る量はもう決まっているので、値引きの判断の参考と、
#: 次の日に条件（長期休み・イベント）の入れ忘れに気づくための知らせ
ALERT_STEP = 12  # 13:00（15分×12）
#: 開店からここまでに売れた数が、店側の予測（その日の事前分布の平均）の何倍より少ない／多いと知らせるか
ALERT_LOW_RATIO = 0.75  # 0.7だと長期休み（需要0.7倍）がちょうど境目になり、入れ忘れの日の73%しか気づけなかった。
# 0.75で入れ忘れの87%に気づき、いつもどおりの日の誤報は7%（0.8だと誤報20%で、知らせが無視されやすくなる）
ALERT_HIGH_RATIO = 1.3
#: 予測した数がこれより少ない商品は、ばらつきが大きいので判定しない
ALERT_MIN_EXPECTED = 3.0


def unusual_sales_alert(sold: int, expected: float) -> str | None:
    """開店から昼過ぎまでに売れた数を予測と比べ、大きく外れていたら知らせの種類を返す（§5.16）。"""
    if expected < ALERT_MIN_EXPECTED:
        return None
    ratio = sold / expected
    if ratio < ALERT_LOW_RATIO:
        return "low"
    if ratio > ALERT_HIGH_RATIO:
        return "high"
    return None


def planned_stock(prior_alpha: float, prior_beta: float, steps: int = STEPS) -> int:
    """その日の条件の予測から作る量を決める（docs/spec.md §5.17。2026-11-26追加）。
    定価で1日に売れる見込み＝予測の平均（1ステップあたり）×1日の時間帯の重みの合計。四捨五入、最低1個。"""
    return max(1, round(prior_alpha / prior_beta * sum(demand_curve(steps))))


def carry_over(alpha: float, beta: float) -> tuple[float, float]:
    """営業の終わりの事後分布を、次の日の事前分布にする（学習の継続＋古いデータを忘れる。§5.15）。"""
    return alpha * FORGETTING_FACTOR, beta * FORGETTING_FACTOR


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
    # 「いつもと違う」の知らせ（§5.16）。ALERT_STEP以降のステップに付く。"low"＝いつもより売れていない、
    # "high"＝いつもより売れている、None＝いつもどおり（または判定前・判定できない）
    alert: str | None = None
    # 店頭の在庫（2026-11-26追加。§5.12）。remaining_stockは「1日の残り（店頭＋まだ補充していない分）」で、
    # 16時の補充で増えないため、画面のモニター・表・在庫推移はこちらを使う
    shelf_stock: int | None = None


@dataclass
class ProductFinalResult:
    product_id: int
    final_waste_rate: float
    achieved: bool
    # 終了時点の事後分布（docs/spec.md §5.2 step4「学習の継続」で次回の事前分布として使う）
    final_alpha: float
    final_beta: float
    # その日に実際に作った量（朝の分＋16時の補充）と、16時に補充した数（§5.18）
    produced: int = 0
    restocked: int = 0


@dataclass
class SimulationOutcome:
    steps: list[ProductStepResult] = field(default_factory=list)
    finals: list[ProductFinalResult] = field(default_factory=list)


def next_discount(current: float) -> float:
    """1回の判断で上げる先（§5.19）：値引きなしなら最初の20%、それ以外は+5%（上限75%）。"""
    if current <= 0:
        return FIRST_DISCOUNT
    return min(MAX_DISCOUNT, round(current + DISCOUNT_INCREMENT, 2))


def should_raise_discount(
    remaining_stock: int,
    target_waste_stock: float,
    predicted_rate: float,
    remaining_exposure: float,
    current_rate: float,
    elasticity: float,
) -> bool:
    """今の値引きのまま閉店までに売り切れる見込みがなければTrue（＝+5%上げる。§5.19）。

    見込み＝予測の平均（前日までの学習＋今日の売れ方でベイズ更新した事後分布の平均）
    × 残りの時間帯の重みの合計 × 今の値引きの需要倍率。これが「残りの在庫−目標の廃棄」に届かなければ上げる。
    """
    expected = predicted_rate * remaining_exposure * discount_multiplier(current_rate, elasticity)
    return expected < remaining_stock - target_waste_stock


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
            # 16時に実際に補充した数（§5.18）。補充する前はNone
            "restocked": None,
            # 16時の補充直後の在庫（夜の値引き判定の基準。補充するまではNone）
            "evening_stock": None,
            # お客さんの本当の需要（§5.14）。店側の予測とは別に持ち、学習しても変わらない
            "true_rate": p.true_rate if p.true_rate is not None else p.prior_alpha / p.prior_beta,
            "discount": 0.0,
            "last_recommended": 0.0,
            # モニターに出ている値引き率（承認済み）と、承認待ちのズバリ引き（率, 承認されるステップ）
            "applied": 0.0,
            "pending": None,
            # 「いつもと違う」の知らせ（§5.16）と、開店からの販売数
            "alert": None,
            "sold_so_far": 0,
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
                # 夜の標準の量まで満杯にする。昼の売れ行きで少なめ／多めに（§5.18。2026-11-26改訂）
                morning = split_stock(p.initial_stock)[0]
                lunch_predicted = min(
                    (p.prior_alpha / p.prior_beta) * sum(curve[:RESTOCK_STEP]), morning
                )
                added = restock_amount(
                    state["restock"], state["remaining"], state["sold_so_far"], lunch_predicted
                )
                state["remaining"] += added
                state["restocked"] = added
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

            # 2.5) 「いつもと違う」の判定（§5.16）。昼の山が終わった時点で、開店からの販売数を
            #      その日の店側の予測（事前分布の平均×時間帯の重み）と比べる。朝の分しか並んでいないので、
            #      予測が朝の分より多ければ朝の分を上限にする
            state["sold_so_far"] += quantity
            if step == ALERT_STEP:
                predicted = (p.prior_alpha / p.prior_beta) * sum(curve[: step + 1])
                predicted = min(predicted, split_stock(p.initial_stock)[0])
                state["alert"] = unusual_sales_alert(state["sold_so_far"], predicted)

            # 3) 15分ごとの値引きの判断（§5.19。2026-11-26改訂）。この15分の売れた数で予測を更新した
            #    うえで（上の2)）、「今の値引きのまま閉店までに売り切れる見込みか」を予測で確かめる。
            #    見込みがなければ+5%（最初は20%）、見込みがあればそのまま。下げることはしない。
            #    判断は18:00（EARLIEST_DISCOUNT_STEP）から。16時に補充したあとの夜の分が対象
            updated_mean = state["alpha"] / state["beta"]
            target_waste_stock = target_waste_rate * p.initial_stock
            # 1日の残り＝店頭在庫＋まだ補充していない分
            day_remaining = state["remaining"] + state["restock"]
            remaining_exposure = sum(curve[step + 1 :])
            current = state["last_recommended"]
            candidate_rate = current
            if (
                step >= EARLIEST_DISCOUNT_STEP
                and state["remaining"] > 0
                and current < MAX_DISCOUNT
                and should_raise_discount(
                    remaining_stock=state["remaining"],
                    target_waste_stock=target_waste_stock,
                    predicted_rate=updated_mean,
                    remaining_exposure=remaining_exposure,
                    current_rate=current,
                    elasticity=p.elasticity,
                )
            ):
                candidate_rate = next_discount(current)

            # candidate_rate は必ず last_recommended 以上（値引きは下げないため）。
            # 差は常に非負なので abs() は不要
            #    ズバリ引きの刻みは5%幅なので、浮動小数点の誤差（0.60-0.55=0.0499…）で
            #    変化を見落とさないよう、差を丸めてから比べる
            is_new = round(candidate_rate - state["last_recommended"], 6) >= MIN_RATE_CHANGE
            if is_new:
                state["last_recommended"] = candidate_rate
                if candidate_rate >= APPROVAL_RATE:
                    # 55%以上はナイトマネージャーの承認待ち（docs/spec.md §5.11）。承認待ちのあいだに
                    # さらに上がったら、承認するのはその時点の最新の提案。承認される時刻は最初に
                    # 承認待ちになったときから数える（15分ごとに上がっても承認が永遠に来ない、を防ぐ）
                    ready = (
                        state["pending"][1]
                        if state["pending"] is not None
                        else step + approval_delay_steps
                    )
                    state["pending"] = (candidate_rate, ready)
                else:
                    # 55%未満は自動で出る（承認待ちにしない）
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
                    shelf_stock=state["remaining"],
                    recommended_rate=state["last_recommended"],
                    posterior_mean=expected_remaining,
                    is_new_recommendation=is_new,
                    posterior_alpha=state["alpha"],
                    posterior_beta=state["beta"],
                    applied_rate=state["applied"],
                    alert=state["alert"],
                )
            )

    for p in active_products:
        state = states[p.product_id]
        # その日に実際に作った量＝朝の分＋16時に補充した数（§5.18。補充しないまま終わったら朝の分だけ）
        restocked = state["restocked"] if state["restocked"] is not None else 0
        produced = split_stock(p.initial_stock)[0] + restocked
        # 16時より前のステップの「1日の残り」は、実際に補充した数で数え直す
        # （1日の残り＝作った量−それまでに売れた数。履歴の再構築・機会損失の判定と同じ数え方）
        for s in outcome.steps:
            if s.product_id == p.product_id and s.step < RESTOCK_STEP and s.shelf_stock is not None:
                s.remaining_stock = s.shelf_stock + restocked
        final_waste_rate = state["remaining"] / produced if produced > 0 else 0.0
        outcome.finals.append(
            ProductFinalResult(
                product_id=p.product_id,
                final_waste_rate=final_waste_rate,
                achieved=final_waste_rate <= target_waste_rate,
                final_alpha=state["alpha"],
                final_beta=state["beta"],
                produced=produced,
                restocked=restocked,
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
