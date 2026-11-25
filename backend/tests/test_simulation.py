from services.simulation import (
    DISCOUNT_TIERS,
    MAX_DISCOUNT,
    SHORTFALL_MARGIN_RATE,
    ProductInput,
    _is_behind_pace,
    _required_discount_rate,
    _snap_to_tier,
    discount_multiplier,
    run_simulation,
)


def make_product(
    product_id: int = 1,
    stock: int = 30,
    elasticity: float = 0.15,
    alpha: float = 3.0,
    beta: float = 2.0,
) -> ProductInput:
    return ProductInput(
        product_id=product_id,
        name=f"商品{product_id}",
        initial_stock=stock,
        elasticity=elasticity,
        prior_alpha=alpha,
        prior_beta=beta,
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


def test_discount_tiers_are_30_half_and_zubari() -> None:
    """docs/spec.md §5.3：実店舗の値引きシールに合わせた4段階。"""
    assert DISCOUNT_TIERS == (0.0, 0.30, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75)
    assert DISCOUNT_TIERS[-1] == MAX_DISCOUNT


def test_snap_to_tier_rounds_up_not_down() -> None:
    # 42%は30%と50%の間。切り下げ（30%）ではなく切り上げ（50%）になる
    assert _snap_to_tier(0.42) == 0.50
    # ちょうど刻みの値はそのまま
    assert _snap_to_tier(0.30) == 0.30
    assert _snap_to_tier(0.50) == 0.50


def test_snap_to_tier_zero_stays_zero() -> None:
    assert _snap_to_tier(0.0) == 0.0


def test_snap_to_tier_low_value_rounds_up_to_30() -> None:
    # 値引きが1%でも必要なら、実際に使える最小の刻みである30%まで切り上げる
    assert _snap_to_tier(0.01) == 0.30


def test_snap_to_tier_clamps_above_max_to_max_discount() -> None:
    assert _snap_to_tier(0.9) == MAX_DISCOUNT


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


def test_rain_triggers_discount_earlier_than_sunny() -> None:
    """基準需要が低い（雨）方が、基準需要が高い（晴れ）より早く値引き提案が出る。"""
    sunny = make_product(alpha=7.0, beta=2.0)  # 平均需要 3.5/step（在庫30・40stepなら余裕で完売）
    rainy = make_product(alpha=1.0, beta=2.0)  # 平均需要 0.5/step（需要不足で売れ残りやすい）
    target = 0.03

    out_sunny = run_simulation([sunny], target_waste_rate=target, seed=100)
    out_rainy = run_simulation([rainy], target_waste_rate=target, seed=100)

    first_sunny = next((s.step for s in out_sunny.steps if s.recommended_rate > 0), None)
    first_rainy = next((s.step for s in out_rainy.steps if s.recommended_rate > 0), None)

    assert first_rainy is not None, "需要不足なのに値引き提案が一度も出なかった"
    assert first_sunny is None or first_rainy < first_sunny


def test_is_behind_pace_within_margin_is_false() -> None:
    """docs/spec.md §5.3「トリガー」：目標ペースからの遅れがマージン以内ならFalse。"""
    # 目標100個・経過50%なら目標ペースは50個。45個売れていれば遅れは5個（マージンは初期在庫100の15%=15）
    assert (
        _is_behind_pace(
            actual_sold=45,
            initial_stock=100,
            target_waste_stock=0,
            elapsed_steps=20,
            total_steps=40,
        )
        is False
    )


def test_is_behind_pace_beyond_margin_is_true() -> None:
    """マージンを超えて遅れていればTrue。"""
    # 目標ペース50個に対し30個しか売れていない＝遅れ20個 > マージン15個
    assert (
        _is_behind_pace(
            actual_sold=30,
            initial_stock=100,
            target_waste_stock=0,
            elapsed_steps=20,
            total_steps=40,
        )
        is True
    )


def test_is_behind_pace_boundary_is_exclusive() -> None:
    """遅れがちょうどマージンと同値のときはFalse（マージン「以内」に含む。>で判定するため）。"""
    margin = 100 * SHORTFALL_MARGIN_RATE  # 15
    assert (
        _is_behind_pace(
            actual_sold=50 - margin,
            initial_stock=100,
            target_waste_stock=0,
            elapsed_steps=20,
            total_steps=40,
        )
        is False
    )


def test_is_behind_pace_early_steps_have_small_target_and_rarely_trigger() -> None:
    """開店直後は目標ペースの絶対量自体が小さいため、実際に0個しか売れていなくても
    マージン内に収まりやすい（旧GRACE_PERIOD_STEPSの役割をこの仕組みが自然に吸収している
    ことの確認）。"""
    # 初期在庫50・目標廃棄率0（全部売り切るのが目標）でも、ステップ1時点の目標ペースは
    # 50 * (1/40) = 1.25個。0個しか売れていなくても遅れは1.25 < マージン(50*0.15=7.5)
    assert (
        _is_behind_pace(
            actual_sold=0,
            initial_stock=50,
            target_waste_stock=0,
            elapsed_steps=1,
            total_steps=40,
        )
        is False
    )


def test_required_discount_rate_does_not_force_max_for_small_positive_baseline() -> None:
    """docs/spec.md §5.2 step2c（2026-08-14改訂）の回帰テスト。以前のMAP推定（最頻値）は
    alpha<=1だと`(alpha-1)/beta`がちょうど0に潰れ、`_required_discount_rate`の
    「baseline_projected<=0→無条件でMAX_DISCOUNT」という0除算回避の分岐に落ちて、
    残り時間や不足量の大きさに関係なく問答無用で最大値引きになっていた。事後分布の平均
    （alpha>0なら常に正）に変えたことで、この無条件MAX分岐そのものを踏まなくなったことを
    直接確認する。

    2026-08-15改訂：値引きの「トリガー」を実績ベースの`_is_behind_pace`に変更したことで、
    様子見のぶん遅れが蓄積してから初めて値引き幅を計算するようになった。そのため
    `run_simulation`レベルでは「最初の提案がいきなり75%になる」こと自体は起こりうる
    （様子見していた間の遅れを一括で取り戻す必要があるため。これはバグではなく実績ベースの
    トリガーの自然な帰結）。したがってこのテストは`run_simulation`ではなく
    `_required_discount_rate`を直接呼び、baseline_rateが「0（旧MAPの0collapse相当）」と
    「tinyだが正の値（新しい平均ベース）」でどう挙動が変わるかを比較する。"""
    # baseline_rate=0.0（旧MAP実装が起こしうる0collapse相当）は、不足量や残り時間の大きさに
    # 関係なく無条件でMAX_DISCOUNTになる（これ自体は0除算回避の既存の安全側フォールバックで
    # バグではない。だからこそ「baseline_rateが0にならない」ことが重要）
    forced_max = _required_discount_rate(
        remaining_stock=20, remaining_steps=30, target_waste_stock=1, baseline_rate=0.0, elasticity=0.15
    )
    assert forced_max == MAX_DISCOUNT

    # 同じ不足量・残り時間でも、tinyだが正の値（alpha>0なら平均alpha/betaは必ず正になる）
    # なら、残り時間が十分にあるぶん無条件MAXにはならず、不足量に見合った緩やかな値引きになる
    mild = _required_discount_rate(
        remaining_stock=20, remaining_steps=30, target_waste_stock=1, baseline_rate=0.5, elasticity=0.15
    )
    assert mild != MAX_DISCOUNT
    assert 0.0 < mild < MAX_DISCOUNT


def test_recommendation_is_suppressed_while_within_pace_margin() -> None:
    """docs/spec.md §5.3「トリガー：見込みではなく実際の遅れで判定する」の回帰テスト。
    需要が極端に低い商品でも、目標ペースからの遅れがマージン以内のうちは
    値引き提案が一切出ない（値引き率は常に0%のまま）ことを、開店直後の数ステップで確認する。"""
    # 需要が非常に低い（値引きが最も必要になりやすい）商品でも、開店直後は
    # 目標ペースの絶対量が小さいためマージン内に収まりやすい
    product = make_product(stock=10, elasticity=0.15, alpha=0.5, beta=2.0)

    for seed in range(5):
        outcome = run_simulation([product], target_waste_rate=0.0, seed=seed)
        # 初期在庫10・目標廃棄率0のとき、マージンは10*0.15=1.5個。
        # ステップ1(経過1/40)の目標ペースは10*(1/40)=0.25個で、実際の販売数が0でも
        # 遅れ0.25 < マージン1.5なので、少なくとも最初の数ステップは提案が出ないはず
        first_step = next(s for s in sorted(outcome.steps, key=lambda s: s.step) if s.step == 0)
        assert first_step.recommended_rate == 0.0, f"seed={seed}: 開店直後から値引き提案が出た"
        assert not first_step.is_new_recommendation


def test_required_discount_rate_stricter_target_needs_more_discount() -> None:
    """§5.3の計算式そのものを直接検証する（シミュレーションのばらつきに左右されない）。"""
    strict = _required_discount_rate(
        remaining_stock=10, remaining_steps=10, target_waste_stock=0, baseline_rate=0.5, elasticity=0.15
    )
    lenient = _required_discount_rate(
        remaining_stock=10, remaining_steps=10, target_waste_stock=3, baseline_rate=0.5, elasticity=0.15
    )
    assert strict > lenient > 0


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


def test_snap_to_tier_before_21_caps_at_half() -> None:
    """21時より前（allow_zubari=False）は30%引き・半額の2段階だけ。半額を超える値は半額に抑える。"""
    assert _snap_to_tier(0.42, allow_zubari=False) == 0.50
    assert _snap_to_tier(0.62, allow_zubari=False) == 0.50
    assert _snap_to_tier(0.9, allow_zubari=False) == 0.50


def test_snap_to_tier_after_21_uses_5_percent_zubari_steps() -> None:
    assert _snap_to_tier(0.52) == 0.55
    assert _snap_to_tier(0.61) == 0.65
    assert _snap_to_tier(0.9) == MAX_DISCOUNT


def test_zubari_discount_only_appears_from_step_37() -> None:
    """半額より大きい値引き（ズバリ引き）は、21時を過ぎたステップ（37）以降にしか出ない。
    需要が非常に低い商品（ふつうなら早くから最大値引きになる）でも、37より前は半額で止まる。"""
    from services.simulation import ZUBARI_START_STEP

    product = make_product(stock=100, alpha=0.5, beta=2.0)
    reached_zubari = 0
    for seed in range(5):
        outcome = run_simulation([product], target_waste_rate=0.0, seed=seed)
        for s in outcome.steps:
            if s.step < ZUBARI_START_STEP:
                assert s.recommended_rate <= 0.50, f"seed={seed} step={s.step}: {s.recommended_rate}"
        if max(s.recommended_rate for s in outcome.steps) > 0.50:
            reached_zubari += 1
    # 売れ行きがよい乱数では半額のままで間に合うこともある（それは正しい動き）。
    # テストの前提として、少なくとも1つのseedでは21時以降にズバリ引きへ進むことを確認する
    assert reached_zubari >= 1


def test_required_discount_rate_is_inverse_of_discount_multiplier() -> None:
    """値引き幅の逆算は、需要倍率の式（2乗。discount_multiplier）とぴったり逆になっている
    （2026-11-26修正。以前は1乗の式で逆算していて、必要な値引きを大きめに見積もっていた）。
    求めた値引き率で需要倍率を計算し直すと、必要だった倍率に戻ることを確認する。"""
    rate = _required_discount_rate(
        remaining_stock=20, remaining_steps=10, target_waste_stock=0, baseline_rate=1.0, elasticity=0.15
    )
    # 必要な倍率 = 20 / (1.0 × 10) = 2.0
    assert 0.0 < rate < MAX_DISCOUNT
    assert abs(discount_multiplier(rate, elasticity=0.15) - 2.0) < 1e-9
    # 1乗の式なら 1.0 × 0.1 ÷ 0.15 ≈ 0.667 になっていた。2乗の逆算は 0.1 × √(1 ÷ 0.15) ≈ 0.258
    assert abs(rate - 0.1 * (1 / 0.15) ** 0.5) < 1e-9


# --- ナイトマネージャーの承認（docs/spec.md §5.11。2026-11-26追加） ---


def _low_demand_products() -> list[ProductInput]:
    return [make_product(product_id=i, stock=100, alpha=0.5, beta=2.0) for i in (1, 2, 3)]


def test_approval_delay_zero_applies_every_proposal_immediately() -> None:
    """承認の遅れ0（すぐ承認）なら、モニターに出る値引きは常に提案と同じ（以前と同じ動き）。"""
    for seed in range(5):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        assert all(s.applied_rate == s.recommended_rate for s in outcome.steps)


def test_30_percent_and_half_are_applied_without_waiting_for_approval() -> None:
    """承認が遅れても、30%引き・半額は提案と同時にモニターに出る（承認が要るのはズバリ引きだけ）。"""
    for seed in range(5):
        outcome = run_simulation(
            _low_demand_products(), target_waste_rate=0.0, seed=seed, approval_delay_steps=3
        )
        for s in outcome.steps:
            if s.recommended_rate <= 0.50:
                assert s.applied_rate == s.recommended_rate


def test_zubari_is_applied_only_after_the_approval_delay() -> None:
    """ズバリ引きは、提案されたステップから approval_delay_steps 後に初めてモニターに出る。
    それまでは前の値引き（半額）のまま。"""
    checked = 0
    for seed in range(10):
        outcome = run_simulation(
            _low_demand_products(), target_waste_rate=0.0, seed=seed, approval_delay_steps=2
        )
        for pid in (1, 2, 3):
            steps = sorted((s for s in outcome.steps if s.product_id == pid), key=lambda s: s.step)
            first = next((s for s in steps if s.recommended_rate > 0.50), None)
            if first is None or first.step + 2 >= len(steps):
                continue
            by_step = {s.step: s for s in steps}
            assert by_step[first.step].applied_rate <= 0.50
            assert by_step[first.step + 1].applied_rate <= 0.50
            assert by_step[first.step + 2].applied_rate > 0.50
            checked += 1
    assert checked >= 1, "テストの前提（ズバリ引きが承認されるまでの時間がある）が崩れている"


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
    """昼に値引きは無く、17時台の夕方の山も定価で売る。値引きの判断は18時（ステップ27）から。"""
    from services.simulation import EARLIEST_DISCOUNT_STEP

    assert EARLIEST_DISCOUNT_STEP == 27
    for seed in range(5):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        for s in outcome.steps:
            if s.step < EARLIEST_DISCOUNT_STEP:
                assert s.recommended_rate == 0.0, f"seed={seed} step={s.step}"


def test_discount_never_skips_30_percent_and_holds_it_for_3_steps() -> None:
    """段階を飛ばさない（docs/spec.md §5.3。2026-11-26）：半額の前に必ず30%引きがあり、
    30%引きは最低MIN_STEPS_AT_30ステップ続く。"""
    from services.simulation import MIN_STEPS_AT_30

    for seed in range(10):
        outcome = run_simulation(_low_demand_products(), target_waste_rate=0.0, seed=seed)
        for pid in (1, 2, 3):
            steps = sorted((s for s in outcome.steps if s.product_id == pid), key=lambda s: s.step)
            first_30 = next((s.step for s in steps if s.recommended_rate == 0.30), None)
            first_half = next((s.step for s in steps if s.recommended_rate >= 0.50), None)
            if first_half is None:
                continue
            assert first_30 is not None, f"seed={seed} pid={pid}: 30%引きを飛ばして半額になった"
            assert first_half - first_30 >= MIN_STEPS_AT_30
