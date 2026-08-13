from services.simulation import (
    DISCOUNT_TIERS,
    GRACE_PERIOD_STEPS,
    MAX_DISCOUNT,
    ProductInput,
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
    # 10%引きごとに elasticity 分だけ倍率が上がる
    assert discount_multiplier(0.10, elasticity=0.2) == 1.2
    assert discount_multiplier(0.30, elasticity=0.2) == 1.6


def test_discount_tiers_are_0_30_50_75() -> None:
    """docs/spec.md §5.3：実店舗の値引きシールに合わせた4段階。"""
    assert DISCOUNT_TIERS == (0.0, 0.30, 0.50, 0.75)
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


def test_first_recommendation_is_not_immediately_max_discount_for_low_alpha(
    monkeypatch,
) -> None:
    """docs/spec.md §5.2 step2c（2026-08-14改訂）の回帰テスト。以前のMAP推定（最頻値）は
    alpha<=1だと`(alpha-1)/beta`がちょうど0に潰れて「一日中売れない」と誤判定し、
    最初の値引き提案がいきなり最大値引き（75%）になっていた。事後分布の平均（0に潰れない）
    に変えたことで、alpha=1.0（旧MAP実装だと最頻値がちょうど境界で0になる値）でも
    最初の提案が75%にはならないことを、複数シードで確認する。

    コードレビュー指摘の修正：様子見期間（GRACE_PERIOD_STEPS。§5.3）により、通常は
    最初の5ステップで値引き提案自体が計算されないため、alpha=3.0のような典型的な需要では
    様子見期間が終わる頃には需要不足が解消されており、MAP推定に戻してもこのテストが
    落ちない（＝このテストが実際には何も検出できていない）ことが判明した。
    様子見期間を一時的に無効化（`GRACE_PERIOD_STEPS = 0`）してMAP0collapseが起こりうる
    ステップ0近辺を直接検証することで、このテストが本当に変更1を検出できるようにする。"""
    monkeypatch.setattr("services.simulation.GRACE_PERIOD_STEPS", 0)
    product = make_product(stock=20, elasticity=0.15, alpha=1.0, beta=2.0)
    target = 0.05

    for seed in range(20):
        outcome = run_simulation([product], target_waste_rate=target, seed=seed)
        first_recommendation = next(
            (s.recommended_rate for s in outcome.steps if s.recommended_rate > 0), None
        )
        assert first_recommendation != MAX_DISCOUNT, (
            f"seed={seed}: 最初の値引き提案がいきなり最大値引きになった（MAP推定の0collapseバグの再発）"
        )


def test_grace_period_suppresses_recommendations_in_first_five_steps() -> None:
    """docs/spec.md §5.3「開店直後の様子見期間」（2026-08-14追加）の回帰テスト。
    需要が極端に低い商品でも、最初の5ステップ（GRACE_PERIOD_STEPS）は値引き提案を
    計算・提案しない（値引き率は常に0%のまま）。"""
    # 需要が非常に低い（値引きが最も必要になりやすい）商品でも様子見期間は例外なく守られる
    product = make_product(stock=10, elasticity=0.15, alpha=0.5, beta=2.0)

    for seed in range(5):
        outcome = run_simulation([product], target_waste_rate=0.0, seed=seed)
        early_steps = [s for s in outcome.steps if s.step < GRACE_PERIOD_STEPS]
        assert len(early_steps) == GRACE_PERIOD_STEPS
        assert all(s.recommended_rate == 0.0 for s in early_steps), (
            f"seed={seed}: 様子見期間中に値引き提案が出た"
        )
        assert all(not s.is_new_recommendation for s in early_steps)


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
