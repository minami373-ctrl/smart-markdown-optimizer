from services.simulation import (
    DISCOUNT_TIERS,
    MAX_DISCOUNT,
    ProductInput,
    discount_multiplier,
    run_simulation,
)


def make_product(
    product_id: int = 1,
    stock: int = 30,
    elasticity: float = 0.15,
    alpha: float = 3.0,
    beta: float = 2.0,
    true_rate: float | None = None,
) -> ProductInput:
    return ProductInput(
        product_id=product_id,
        name=f"商品{product_id}",
        initial_stock=stock,
        elasticity=elasticity,
        prior_alpha=alpha,
        prior_beta=beta,
        true_rate=true_rate,
    )


def test_discount_multiplier_at_zero_is_one() -> None:
    assert discount_multiplier(0.0, elasticity=0.2) == 1.0


def test_discount_multiplier_scales_with_elasticity() -> None:
    """docs/spec.md §5.3（2026-08-15改訂）：値引きの刻み(10%単位)の2乗で効く。
    「値引き率に比例」ではなく「大きい値引きほど急激に効く」非線形な式。"""
    # 1刻み(10%)は2乗しても1のまま。以前の比例式と同じ値になる
    assert discount_multiplier(0.10, elasticity=0.2) == 1.2
    # 3刻み(30%)は3の2乗=9倍ぶん効く。以前の比例式（1.6）より強く効く
    assert discount_multiplier(0.30, elasticity=0.2) == 2.8


def test_discount_multiplier_grows_faster_than_linear() -> None:
    """大きい値引きほど「刻み1つあたりの効き」が急激に強くなる（2乗の非線形性そのものの確認）。
    30%→50%の上げ幅と50%→75%の上げ幅を比べると、後者の方が大きくなるはず。"""
    m30 = discount_multiplier(0.30, elasticity=0.18)
    m50 = discount_multiplier(0.50, elasticity=0.18)
    m75 = discount_multiplier(0.75, elasticity=0.18)

    assert m50 - m30 < m75 - m50, "値引き率が上がるほど、効きの増分が大きくなっていない"












def test_simulation_is_deterministic() -> None:
    """同じ条件・同じ seed なら、2回実行しても同じ結果になる。"""
    products = [make_product()]

    out1 = run_simulation(products, target_waste_rate=0.05, seed=42)
    out2 = run_simulation(products, target_waste_rate=0.05, seed=42)

    assert [s.quantity for s in out1.steps] == [s.quantity for s in out2.steps]
    assert [s.recommended_rate for s in out1.steps] == [s.recommended_rate for s in out2.steps]
    assert out1.finals == out2.finals


def test_different_seed_gives_different_result() -> None:
    """乱数任せの部分がちゃんと効いていることの確認（決定性テストの裏付け）。"""
    products = [make_product()]

    out1 = run_simulation(products, target_waste_rate=0.05, seed=1)
    out2 = run_simulation(products, target_waste_rate=0.05, seed=2)

    assert [s.quantity for s in out1.steps] != [s.quantity for s in out2.steps]


def test_rain_restocks_less_and_discounts_when_still_left_over() -> None:
    """2026-11-26改訂（§5.18）：16時の補充は昼の売れ行きで増減するので、需要が低い日（雨）は
    補充が少なくなる。そのうえで、本当の需要が店の予測よりずっと低い日は、補充を減らしても
    売れ残るので値引きが出る。"""
    sunny = make_product(stock=30, alpha=1.5, beta=2.0, true_rate=0.75)
    rainy = make_product(stock=30, alpha=1.5, beta=2.0, true_rate=0.3)
    out_sunny = run_simulation([sunny], target_waste_rate=0.03, seed=100)
    out_rainy = run_simulation([rainy], target_waste_rate=0.03, seed=100)
    assert out_rainy.finals[0].restocked < out_sunny.finals[0].restocked
    assert any(s.recommended_rate > 0 for s in out_rainy.steps)
















def test_products_are_independent() -> None:
    """ある商品の結果は、他の商品が同時に計算されているかどうかに影響されない。"""
    p1 = make_product(product_id=1, alpha=2.0, beta=2.0)
    p2 = make_product(product_id=2, alpha=5.0, beta=2.0, elasticity=0.3)

    out_both = run_simulation([p1, p2], target_waste_rate=0.05, seed=7)
    out_p1_alone = run_simulation([p1], target_waste_rate=0.05, seed=7)

    p1_in_both = [s for s in out_both.steps if s.product_id == 1]
    assert [s.quantity for s in p1_in_both] == [s.quantity for s in out_p1_alone.steps]
    assert [s.recommended_rate for s in p1_in_both] == [
        s.recommended_rate for s in out_p1_alone.steps
    ]


def test_zero_stock_product_is_skipped_without_crashing() -> None:
    """初期在庫0の商品は購入ログ生成をスキップし、0除算を起こさない（docs/spec.md §5.2）。"""
    zero_stock = make_product(product_id=99, stock=0)
    normal = make_product(product_id=1, stock=20)

    outcome = run_simulation([zero_stock, normal], target_waste_rate=0.05, seed=3)

    assert all(s.product_id != 99 for s in outcome.steps)
    assert all(f.product_id != 99 for f in outcome.finals)
    # 他の商品の計算は普通に行われる
    assert any(f.product_id == 1 for f in outcome.finals)


def test_posterior_stops_updating_after_product_sells_out() -> None:
    """docs/spec.md §5.2 step2b（2026-08-14追加）の回帰テスト。完売後は「これ以上売れたか」を
    観測できない打ち切りデータのため、alpha/betaの更新を止める。ガードが無いと、完売後の
    残りステップぶんbetaだけが増え続け、事後分布の平均が実際の需要より大幅に低く見えてしまう
    （「学習の継続」でその下振れが次回の事前分布に持ち越される不具合があった）。"""
    # 需要が非常に高く在庫が少ないため、ほぼ確実に序盤で完売する
    product = make_product(stock=5, elasticity=0.12, alpha=20.0, beta=2.0)

    outcome = run_simulation([product], target_waste_rate=0.03, seed=1)
    steps_in_order = sorted(outcome.steps, key=lambda s: s.step)

    sellout_step = next(s for s in steps_in_order if s.remaining_stock == 0)
    assert sellout_step is not None, "このテストの前提（完売する）が崩れている"

    # 完売した瞬間のalpha/betaを基準に、それ以降のステップで値が変化していないことを確認する
    after_sellout = [s for s in steps_in_order if s.step > sellout_step.step]
    assert len(after_sellout) > 0, "完売がステップ39ちょうどで、検証対象のステップが残っていない"
    assert all(s.posterior_alpha == sellout_step.posterior_alpha for s in after_sellout)
    assert all(s.posterior_beta == sellout_step.posterior_beta for s in after_sellout)


def test_final_waste_rate_matches_remaining_stock() -> None:
    product = make_product(stock=30, alpha=3.0, beta=2.0)
    out = run_simulation([product], target_waste_rate=0.05, seed=9)

    final = out.finals[0]
    last_remaining = next(
        s.remaining_stock for s in reversed(out.steps) if s.product_id == product.product_id
    )
    assert final.final_waste_rate == last_remaining / product.initial_stock


def test_final_alpha_beta_matches_last_step_posterior() -> None:
    """学習の継続（docs/spec.md §5.2 step4）の書き戻し元になる値の検証。
    ProductFinalResult.final_alpha/final_beta は最終ステップの事後分布と一致する。"""
    product = make_product(stock=30, alpha=3.0, beta=2.0)
    out = run_simulation([product], target_waste_rate=0.05, seed=11)

    final = out.finals[0]
    last_step = next(
        s for s in reversed(out.steps) if s.product_id == product.product_id
    )
    assert final.final_alpha == last_step.posterior_alpha
    assert final.final_beta == last_step.posterior_beta
    # betaは毎ステップ露出ぶん必ず増えるので、初期値より大きくなっているはず
    assert final.final_beta > product.prior_beta


def test_recommended_rate_is_always_one_of_the_discount_tiers() -> None:
    """docs/spec.md §5.3：連続値のまま提案されることは無く、常に4段階のいずれかになる。
    需要が高い商品・低い商品・複数シードを混ぜて、幅広いケースで刻みから外れないか確認する。"""
    products = [
        make_product(product_id=1, alpha=1.0, beta=2.0),  # 需要低め（値引き不要になりやすい）
        make_product(product_id=2, alpha=8.0, beta=2.0),  # 需要高め（在庫不足になりやすい）
        make_product(product_id=3, alpha=3.0, beta=2.0, elasticity=0.05),  # 感度が低い
    ]

    for seed in range(5):
        outcome = run_simulation(products, target_waste_rate=0.03, seed=seed)
        rates = {s.recommended_rate for s in outcome.steps}
        assert rates <= set(DISCOUNT_TIERS), f"seed={seed}: 刻み以外の値引き率が出た: {rates}"


def test_recommended_rate_never_decreases_within_a_run() -> None:
    """docs/spec.md §5.3「値引きは下げない」：値引きシールは一度貼ったら剥がせない、
    という物理的な制約の再現。1回のシミュレーション内で、ステップ順に見た値引き率が
    後戻りしない（前のステップ以上）ことを、複数商品・複数シードで確認する。"""
    products = [
        make_product(product_id=1, alpha=1.0, beta=2.0),
        make_product(product_id=2, alpha=8.0, beta=2.0),
        make_product(product_id=3, alpha=3.0, beta=2.0, elasticity=0.05),
    ]

    for seed in range(5):
        outcome = run_simulation(products, target_waste_rate=0.03, seed=seed)
        for product_id in (1, 2, 3):
            rates_in_order = [
                s.recommended_rate
                for s in sorted(outcome.steps, key=lambda s: s.step)
                if s.product_id == product_id
            ]
            assert rates_in_order == sorted(rates_in_order), (
                f"seed={seed} product_id={product_id}: 値引き率が途中で下がった: {rates_in_order}"
            )


def test_recommended_rate_stays_at_max_once_reached() -> None:
    """一度75%（最大値引き）に達したら、その回の残りは75%のまま維持される。"""
    # 需要が非常に低い（在庫が余りやすい）商品で、確実に最大値引きに到達させる
    product = make_product(stock=100, alpha=0.5, beta=2.0)

    outcome = run_simulation([product], target_waste_rate=0.0, seed=1)
    rates_in_order = [s.recommended_rate for s in sorted(outcome.steps, key=lambda s: s.step)]

    assert MAX_DISCOUNT in rates_in_order, "このテストの前提（最大値引きに到達する）が崩れている"
    first_max_index = rates_in_order.index(MAX_DISCOUNT)
    assert all(r == MAX_DISCOUNT for r in rates_in_order[first_max_index:])


# --- ズバリ引き（docs/spec.md §5.3。2026-11-26追加） ---










# --- ナイトマネージャーの承認（docs/spec.md §5.11。2026-11-26追加） ---


def _low_demand_products() -> list[ProductInput]:
    return [make_product(product_id=i, stock=100, alpha=0.5, beta=2.0) for i in (1, 2, 3)]


def test_approval_delay_zero_applies_every_proposal_immediately() -> None:
    """承認の遅れ0（すぐ承認）なら、モニターに出る値引きは常に提案と同じ（以前と同じ動き）。"""
    for seed in range(5):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        assert all(s.applied_rate == s.recommended_rate for s in outcome.steps)


def test_below_55_percent_is_applied_without_waiting_for_approval() -> None:
    """承認が遅れても、55%未満は提案と同時にモニターに出る（承認が要るのは55%以上だけ。§5.19）。"""
    for seed in range(5):
        outcome = run_simulation(
            _low_demand_products(), target_waste_rate=0.0, seed=seed, approval_delay_steps=3
        )
        for s in outcome.steps:
            if s.recommended_rate < 0.55:
                assert s.applied_rate == s.recommended_rate


def test_55_percent_or_more_is_applied_only_after_the_approval_delay() -> None:
    """55%以上の値引きは、最初に承認待ちになったステップから approval_delay_steps 後に初めて
    モニターに出る。それまでは前の値引き（50%）のまま。承認待ちのあいだにさらに上がっても、
    承認される時刻は延びない（§5.19）。"""
    checked = 0
    for seed in range(10):
        outcome = run_simulation(
            _low_demand_products(), target_waste_rate=0.0, seed=seed, approval_delay_steps=2
        )
        for pid in (1, 2, 3):
            steps = sorted((s for s in outcome.steps if s.product_id == pid), key=lambda s: s.step)
            first = next((s for s in steps if s.recommended_rate >= 0.55), None)
            if first is None or first.step + 2 >= len(steps):
                continue
            by_step = {s.step: s for s in steps}
            assert by_step[first.step].applied_rate <= 0.50
            assert by_step[first.step + 1].applied_rate <= 0.50
            assert by_step[first.step + 2].applied_rate >= 0.55
            checked += 1
    assert checked >= 1, "テストの前提（55%以上まで上がる）が崩れている"


def test_approval_delay_never_lowers_what_is_on_the_monitor() -> None:
    """承認待ちがあっても、モニターに出る値引きは下がらない（お客さんの信頼のためのルール）。"""
    for seed in range(5):
        outcome = run_simulation(
            _low_demand_products(), target_waste_rate=0.0, seed=seed, approval_delay_steps=3
        )
        for pid in (1, 2, 3):
            applied = [s.applied_rate for s in sorted(outcome.steps, key=lambda s: s.step) if s.product_id == pid]
            assert applied == sorted(applied)


# --- 1日の売れ方・16時の補充（docs/spec.md §5.12。2026-11-26追加） ---


def test_demand_curve_has_mean_one_and_peaks_at_noon() -> None:
    from services.simulation import demand_curve

    curve = demand_curve(40)
    assert abs(sum(curve) / len(curve) - 1.0) < 1e-9
    # 12:00〜13:00（ステップ7〜9）が一番の山、17時台が2番目の山
    assert curve.index(max(curve)) in (7, 8, 9)
    assert max(curve[23:27]) > curve[15]  # 17時台 > 15時台


def test_split_stock_puts_half_in_the_morning_rounding_up() -> None:
    from services.simulation import split_stock

    assert split_stock(20) == (10, 10)
    assert split_stock(15) == (8, 7)
    assert split_stock(1) == (1, 0)


def test_morning_sales_never_exceed_the_morning_stock() -> None:
    """16時の補充（ステップ20）より前は、朝に並べた分しか売れない。"""
    from services.simulation import RESTOCK_STEP, split_stock

    product = make_product(stock=20, alpha=20.0, beta=2.0)  # 需要がとても高い＝昼に売り切れる
    outcome = run_simulation([product], target_waste_rate=0.0, seed=1)
    morning_sold = sum(s.quantity for s in outcome.steps if s.step < RESTOCK_STEP)
    assert morning_sold <= split_stock(20)[0]
    # 補充後はまた売れる
    assert sum(s.quantity for s in outcome.steps if s.step >= RESTOCK_STEP) > 0


def test_no_discount_is_decided_before_18() -> None:
    """昼に値引きは無く、17時台の夕方の山も定価で売る。値引きの判断は18時（ステップ32）から。"""
    from services.simulation import EARLIEST_DISCOUNT_STEP

    assert EARLIEST_DISCOUNT_STEP == 32  # 18:00
    for seed in range(5):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        for s in outcome.steps:
            if s.step < EARLIEST_DISCOUNT_STEP:
                assert s.recommended_rate == 0.0, f"seed={seed} step={s.step}"




def test_sellout_step_is_not_learned_as_low_demand() -> None:
    """売り切れたステップ（欲しい数より在庫が少なかった）は打ち切りデータなので学習しない
    （2026-11-26修正）。需要がとても高く在庫が少ない商品でも、学習後の平均需要が事前分布より
    大きく下がらない（以前は売れた数＝在庫で頭打ちの数を需要として学習し、どんどん下がっていた）。"""
    product = make_product(stock=4, alpha=6.0, beta=2.0)  # 平均需要3/ステップ、在庫4個
    prior_mean = 6.0 / 2.0
    for seed in range(5):
        outcome = run_simulation([product], target_waste_rate=0.0, seed=seed)
        final = outcome.finals[0]
        assert final.final_alpha / final.final_beta > prior_mean * 0.5


# --- 本当の需要と店側の予測を分ける（docs/spec.md §5.14。2026-11-26追加） ---


def test_prediction_moves_toward_true_demand_from_a_wrong_start() -> None:
    """購入は本当の需要から作り、店側の予測はそれを見て学ぶ。最初の予測が本当の需要の半分でも、
    学習の継続（終わった時点の事後分布を次回の事前分布に）を重ねると本当の需要に近づく。"""
    true_rate = 1.0
    alpha, beta = 1.0, 2.0  # 予測の平均0.5（本当の半分）
    for day in range(15):
        product = ProductInput(
            product_id=1, name="x", initial_stock=60, elasticity=0.15,
            prior_alpha=alpha, prior_beta=beta, true_rate=true_rate,
        )
        final = run_simulation([product], target_waste_rate=0.05, seed=100 + day).finals[0]
        alpha, beta = final.final_alpha, final.final_beta
    assert 0.85 < alpha / beta / true_rate < 1.15


def test_prediction_does_not_drift_to_zero_over_many_days() -> None:
    """以前は購入を店側の予測から作っていたため、予測がたまたま下がると翌日の客も減り、
    0に向かって流れていった（たこ焼きが10日で0.374→0.004）。本当の需要を別に持つと流れない。"""
    alpha, beta = 0.75, 2.0  # 平均0.375（seedのたこ焼き相当）
    for day in range(20):
        product = ProductInput(
            product_id=1, name="x", initial_stock=15, elasticity=0.14,
            prior_alpha=alpha, prior_beta=beta, true_rate=0.375,
        )
        final = run_simulation([product], target_waste_rate=0.05, seed=500 + day).finals[0]
        alpha, beta = final.final_alpha, final.final_beta
    assert alpha / beta > 0.375 * 0.7


def test_learn_shrinks_exposure_when_the_step_sold_out() -> None:
    """売り切れたステップは「売り切れるまでの間だけ売っていた」とみなし、露出を縮めて学ぶ。"""
    from services.simulation import _learn

    # ふつうのステップ：そのまま
    assert _learn(2.0, 2.0, quantity=3, demanded=3, exposure=1.5) == (5.0, 3.5)
    # 売り切れ（欲しい5個に対し在庫2個）：予測の平均1.0なら、2個売れるのにかかった露出は2.0だが
    # このステップの露出1.5を超えないので1.5のまま。予測の平均が4.0なら露出は2÷4＝0.5に縮む
    assert _learn(2.0, 2.0, quantity=2, demanded=5, exposure=1.5) == (4.0, 3.5)
    assert _learn(8.0, 2.0, quantity=2, demanded=5, exposure=1.5) == (10.0, 2.5)


# --- 古いデータを少しずつ忘れる（docs/spec.md §5.15。2026-11-26追加） ---


def _learn_days(true_rates: list[float], forget: bool) -> float:
    from services.simulation import carry_over

    alpha, beta = 2.0, 2.0
    for day, true_rate in enumerate(true_rates):
        product = ProductInput(
            product_id=1, name="x", initial_stock=80, elasticity=0.15,
            prior_alpha=alpha, prior_beta=beta, true_rate=true_rate,
        )
        final = run_simulation([product], target_waste_rate=0.05, seed=900 + day).finals[0]
        alpha, beta = (carry_over(final.final_alpha, final.final_beta) if forget
                       else (final.final_alpha, final.final_beta))
    return alpha / beta


def test_carry_over_keeps_the_mean_and_weakens_confidence() -> None:
    from services.simulation import FORGETTING_FACTOR, carry_over

    a, b = carry_over(30.0, 20.0)
    assert a / b == 30.0 / 20.0
    assert b == 20.0 * FORGETTING_FACTOR


def test_forgetting_catches_up_faster_when_demand_changes() -> None:
    """客層が変わって本当の需要が1.0→0.6に下がったとき、古いデータを忘れる方が早く追いつく。"""
    days = [1.0] * 15 + [0.6] * 5
    with_forgetting = _learn_days(days, forget=True)
    without = _learn_days(days, forget=False)
    assert abs(with_forgetting - 0.6) < abs(without - 0.6)


# --- 「いつもと違う」の知らせ（docs/spec.md §5.16。2026-11-26追加） ---


def test_unusual_sales_alert_thresholds() -> None:
    from services.simulation import unusual_sales_alert

    assert unusual_sales_alert(sold=7, expected=10.0) == "low"
    assert unusual_sales_alert(sold=8, expected=10.0) is None
    assert unusual_sales_alert(sold=14, expected=10.0) == "high"
    assert unusual_sales_alert(sold=0, expected=2.0) is None  # 予測が少なすぎる商品は判定しない


def test_alert_appears_only_from_the_alert_step_when_true_demand_is_much_lower() -> None:
    """本当の需要が店の予測の半分（例：長期休みの入れ忘れ）なら、昼過ぎ（ALERT_STEP）から「low」が付く。"""
    from services.simulation import ALERT_STEP

    product = ProductInput(
        product_id=1, name="x", initial_stock=200, elasticity=0.15,
        prior_alpha=8.0, prior_beta=2.0, true_rate=2.0,
    )
    outcome = run_simulation([product], target_waste_rate=0.05, seed=3)
    assert all(s.alert is None for s in outcome.steps if s.step < ALERT_STEP)
    assert all(s.alert == "low" for s in outcome.steps if s.step >= ALERT_STEP)


def test_planned_stock_is_the_full_price_demand_of_the_day() -> None:
    """予測から作る量を決める（§5.17）：予測の平均×1日の時間帯の重みの合計（＝40）を四捨五入。"""
    from services.simulation import planned_stock

    assert planned_stock(1.0, 2.0) == 24  # 平均0.5 × 48ステップ（15分ごと）
    assert planned_stock(0.01, 2.0) == 1  # 最低1個


def test_shelf_stock_goes_up_at_the_16_restock() -> None:
    """店頭の在庫（shelf_stock）は16時の補充（ステップ20）で増える。1日の残り（remaining_stock）は
    補充前の分も含むので増えない。店頭＋まだ補充していない分＝1日の残り。"""
    from services.simulation import RESTOCK_STEP, split_stock

    product = make_product(stock=40, alpha=0.4, beta=2.0)
    steps = sorted(run_simulation([product], target_waste_rate=0.05, seed=2).steps, key=lambda s: s.step)
    before, at = steps[RESTOCK_STEP - 1], steps[RESTOCK_STEP]
    outcome_final = run_simulation([product], target_waste_rate=0.05, seed=2).finals[0]
    restock = outcome_final.restocked
    assert at.shelf_stock == before.shelf_stock + restock - at.quantity
    for s in steps:
        pending = restock if s.step < RESTOCK_STEP else 0
        assert s.shelf_stock + pending == s.remaining_stock


# --- 16時に売り場を満杯にする補充（docs/spec.md §5.18。2026-11-26改訂） ---


def test_restock_fills_the_floor_to_the_standard_level() -> None:
    from services.simulation import restock_amount

    # 昼の売れ行きが予測どおり：夜の標準10個まで満杯に。昼の残りが3個なら補充は7個
    assert restock_amount(10, shelf_now=3, lunch_sold=7, lunch_predicted=7.0) == 7
    # 昼の残りが多ければ、その分だけ補充を減らす
    assert restock_amount(10, shelf_now=8, lunch_sold=7, lunch_predicted=7.0) == 2


def test_restock_is_smaller_after_a_slow_lunch_and_bigger_after_a_busy_one() -> None:
    from services.simulation import restock_amount

    # 昼が予測の半分しか売れなかった → 倍率は下限0.7 → 目標7個
    assert restock_amount(10, shelf_now=2, lunch_sold=4, lunch_predicted=8.0) == 5
    # 昼が予測の1.2倍売れた → 目標12個
    assert restock_amount(10, shelf_now=2, lunch_sold=12, lunch_predicted=10.0) == 10
    # 昼に売り切れた（店頭0）→ 欲しい人がもっといたかもしれないので上限1.3 → 目標13個
    assert restock_amount(10, shelf_now=0, lunch_sold=10, lunch_predicted=10.0) == 13
    # 昼の残りが目標より多ければ、補充しない
    assert restock_amount(10, shelf_now=9, lunch_sold=4, lunch_predicted=8.0) == 0



# --- 15分ごとに「上げる」か「そのまま」、5%刻み（docs/spec.md §5.19。2026-11-26） ---


def test_discount_tiers_are_20_to_75_in_5_percent_steps() -> None:
    assert DISCOUNT_TIERS == (0.0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75)
    assert DISCOUNT_TIERS[-1] == MAX_DISCOUNT


def test_next_discount_starts_at_20_and_goes_up_5_percent() -> None:
    from services.simulation import next_discount

    assert next_discount(0.0) == 0.20
    assert next_discount(0.20) == 0.25
    assert next_discount(0.50) == 0.55
    assert next_discount(0.75) == 0.75  # 上限


def test_should_raise_when_the_forecast_cannot_sell_out_by_closing() -> None:
    """予測（平均1.0/15分）× 残り5の重み × 今の値引きの倍率（0%なら1）＝5個しか売れない見込み。
    残り10個なら上げる、残り4個ならそのまま。"""
    from services.simulation import should_raise_discount

    kwargs = dict(target_waste_stock=0.0, predicted_rate=1.0, remaining_exposure=5.0,
                  current_rate=0.0, elasticity=0.15)
    assert should_raise_discount(remaining_stock=10, **kwargs) is True
    assert should_raise_discount(remaining_stock=4, **kwargs) is False


def test_discount_goes_up_at_most_one_5_percent_step_every_15_minutes() -> None:
    """値引きは1回の判断（15分）で1段（+5%）まで。最初は20%。下がらない。"""
    for seed in range(10):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        for pid in (1, 2, 3):
            rates = [s.recommended_rate for s in sorted(outcome.steps, key=lambda s: s.step) if s.product_id == pid]
            assert rates == sorted(rates)
            nonzero = [r for r in rates if r > 0]
            if nonzero:
                assert nonzero[0] == 0.20
            for a, b in zip(rates, rates[1:]):
                assert round(b - a, 6) in (0.0, 0.05) or (a == 0.0 and b == 0.20)
