from services.schedule_comparison import (
    FIXED_SCHEDULE_30_STEP,
    FIXED_SCHEDULE_50_STEP,
    _fixed_schedule_rate,
    run_fixed_schedule_simulation,
)
from services.simulation import STEPS, ProductInput, run_simulation


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


def test_fixed_schedule_rate_is_zero_before_first_threshold() -> None:
    assert _fixed_schedule_rate(0) == 0.0
    assert _fixed_schedule_rate(FIXED_SCHEDULE_30_STEP - 1) == 0.0


def test_fixed_schedule_rate_is_30_percent_between_thresholds() -> None:
    assert _fixed_schedule_rate(FIXED_SCHEDULE_30_STEP) == 0.30
    assert _fixed_schedule_rate(FIXED_SCHEDULE_50_STEP - 1) == 0.30


def test_fixed_schedule_rate_is_half_after_second_threshold() -> None:
    from services.schedule_comparison import FIXED_SCHEDULE_ZUBARI_STEP

    assert _fixed_schedule_rate(FIXED_SCHEDULE_50_STEP) == 0.50
    # 21時を過ぎるとズバリ引き（2026-11-26追加）になるので、半額はその手前まで
    assert _fixed_schedule_rate(FIXED_SCHEDULE_ZUBARI_STEP - 1) == 0.50
    assert _fixed_schedule_rate(STEPS - 1) == 0.75


def test_fixed_schedule_never_decreases() -> None:
    """docs/spec.md §5.9：時刻だけで単調に決まるため、値引き率が下がることは無い。"""
    rates = [_fixed_schedule_rate(step) for step in range(STEPS)]
    assert rates == sorted(rates)


def test_run_fixed_schedule_simulation_is_deterministic() -> None:
    product = make_product()

    out1 = run_fixed_schedule_simulation(product, seed=1)
    out2 = run_fixed_schedule_simulation(product, seed=1)

    assert [s.quantity for s in out1.steps] == [s.quantity for s in out2.steps]
    assert out1.final_waste_rate == out2.final_waste_rate


def test_run_fixed_schedule_simulation_zero_stock_returns_empty_outcome() -> None:
    product = make_product(stock=0)

    outcome = run_fixed_schedule_simulation(product, seed=1)

    assert outcome.steps == []
    assert outcome.final_waste_rate == 0.0


def test_run_fixed_schedule_simulation_never_discounts_before_step_30() -> None:
    """需要が極端に低い商品でも、固定スケジュールはステップ30（19時相当）より前は
    値引きしない（動的値引きと違い、実際の売れ行きを一切見ないため）。"""
    product = make_product(stock=100, alpha=0.1, beta=2.0)  # 需要が非常に低い

    outcome = run_fixed_schedule_simulation(product, seed=1)

    early_steps = [s for s in outcome.steps if s.step < FIXED_SCHEDULE_30_STEP]
    assert all(s.recommended_rate == 0.0 for s in early_steps)


def test_run_fixed_schedule_simulation_stops_updating_after_sellout() -> None:
    """完売後は購入生成・事後分布の更新を止める（services/simulation.pyの打ち切りデータの
    扱いと同じ。§5.2 step2b）。remaining_stockが0になった以降のステップでquantityが常に0。"""
    product = make_product(stock=5, elasticity=0.12, alpha=20.0, beta=2.0)  # 高需要・低在庫

    outcome = run_fixed_schedule_simulation(product, seed=1)
    steps_in_order = sorted(outcome.steps, key=lambda s: s.step)

    sellout_step = next((s for s in steps_in_order if s.remaining_stock == 0), None)
    assert sellout_step is not None, "このテストの前提（完売する）が崩れている"

    after_sellout = [s for s in steps_in_order if s.step > sellout_step.step]
    assert all(s.quantity == 0 for s in after_sellout)


def test_dynamic_and_fixed_schedule_share_the_same_starting_random_stream() -> None:
    """docs/spec.md §5.9：同じ乱数シードを使うため、値引き率が分岐するまでは
    run_simulation（動的）とrun_fixed_schedule_simulation（固定）で同じ購入個数になる。
    このテストは、需要が高くどちらの方式でも早期には値引きが発生しない商品を使うことで、
    「最初の数ステップは完全に一致する」ことを直接確認する。"""
    product = make_product(stock=100, elasticity=0.15, alpha=8.0, beta=2.0)  # 需要が高く値引き不要

    dynamic = run_simulation([product], target_waste_rate=0.10, seed=42)
    fixed = run_fixed_schedule_simulation(product, seed=42)

    dynamic_quantities = [s.quantity for s in sorted(dynamic.steps, key=lambda s: s.step)]
    fixed_quantities = [s.quantity for s in fixed.steps]

    # ステップ30（固定スケジュールが最初に動くステップ）より前は、動的値引き側も
    # 値引きしていない前提（高需要のため）なので、両者の購入個数は完全に一致するはず
    assert dynamic_quantities[:FIXED_SCHEDULE_30_STEP] == fixed_quantities[:FIXED_SCHEDULE_30_STEP]


def test_fixed_schedule_goes_to_zubari_floor_after_21() -> None:
    """実際の売り場の手順どおり、21時を過ぎたら固定スケジュール側もズバリ引き（下限75%引き）。"""
    from services.schedule_comparison import FIXED_SCHEDULE_ZUBARI_STEP

    assert FIXED_SCHEDULE_ZUBARI_STEP == 44  # 21:00
    assert _fixed_schedule_rate(FIXED_SCHEDULE_ZUBARI_STEP - 1) == 0.50
    assert _fixed_schedule_rate(FIXED_SCHEDULE_ZUBARI_STEP) == 0.75


def test_customer_anticipation_lowers_fixed_schedule_sales_only_around_the_known_times() -> None:
    """「お客さんが待つ」効果（§5.12。仮定）を入れると、18時台と30%引きの間だけ売れにくくなる。
    それより前（昼・夕方の山）の売れ方は変わらない。"""
    from services.schedule_comparison import ANTICIPATION_START_STEP

    product = ProductInput(
        product_id=1, name="x", initial_stock=200, elasticity=0.15, prior_alpha=10.0, prior_beta=2.0
    )
    total_without = total_with = 0
    for seed in range(10):
        without = run_fixed_schedule_simulation(product, seed=seed)
        with_ = run_fixed_schedule_simulation(product, seed=seed, customer_anticipation=True)
        before = [s.quantity for s in without.steps if s.step < ANTICIPATION_START_STEP]
        assert before == [s.quantity for s in with_.steps if s.step < ANTICIPATION_START_STEP]
        window = range(ANTICIPATION_START_STEP, FIXED_SCHEDULE_50_STEP)
        total_without += sum(s.quantity for s in without.steps if s.step in window)
        total_with += sum(s.quantity for s in with_.steps if s.step in window)
    assert total_with < total_without
