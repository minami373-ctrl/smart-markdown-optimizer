from services.opportunity import (
    OpportunityOccurrence,
    StepRecord,
    build_step_records,
    detect_opportunity,
    rank_opportunities,
)
from services.simulation import ProductInput, run_simulation


def steps_no_discount(quantities: list[int], start_step: int = 0) -> list[StepRecord]:
    return [
        StepRecord(step=start_step + i, quantity=q, recommended_rate=0.0)
        for i, q in enumerate(quantities)
    ]


def test_detects_early_sellout_without_discount() -> None:
    # 在庫10個を5ステップ（0〜4）で完売、値引き無し
    steps = steps_no_discount([2, 2, 2, 2, 2])

    result = detect_opportunity(steps, initial_stock=10)

    assert result is not None
    assert result.sellout_step == 4


def test_suggested_increase_extrapolates_to_full_day() -> None:
    # 在庫10個をちょうど5ステップ（steps_to_sellout=5）で完売
    # 推奨追加 = round(10 * (40-5)/5) = round(70) = 70
    steps = steps_no_discount([2, 2, 2, 2, 2])

    result = detect_opportunity(steps, initial_stock=10)

    assert result is not None
    assert result.suggested_increase == 70


def test_not_detected_if_ever_discounted() -> None:
    steps = [
        StepRecord(step=0, quantity=2, recommended_rate=0.0),
        StepRecord(step=1, quantity=2, recommended_rate=0.2),  # 値引きされている
        StepRecord(step=2, quantity=6, recommended_rate=0.2),
    ]

    result = detect_opportunity(steps, initial_stock=10)

    assert result is None


def test_not_detected_if_never_sells_out() -> None:
    steps = steps_no_discount([1] * 40)  # 40個中40個消費で在庫0だが在庫が十分にあるケース

    result = detect_opportunity(steps, initial_stock=100)

    assert result is None


def test_not_detected_if_sellout_too_close_to_closing() -> None:
    # 38ステップ目（steps_to_sellout=39）で完売 → 早期とはみなさない
    quantities = [0] * 38 + [10]
    steps = steps_no_discount(quantities)

    result = detect_opportunity(steps, initial_stock=10)

    assert result is None


def test_detected_at_exact_boundary_step_37() -> None:
    # 37ステップ目（0始まりでstep=37、steps_to_sellout=38）でちょうど完売は対象外の境界
    quantities = [0] * 37 + [10]
    steps = steps_no_discount(quantities)

    result = detect_opportunity(steps, initial_stock=10)

    assert result is not None
    assert result.sellout_step == 37


def test_zero_initial_stock_returns_none() -> None:
    steps = steps_no_discount([0, 0])

    assert detect_opportunity(steps, initial_stock=0) is None


def test_rank_opportunities_sorts_by_avg_suggested_increase_desc() -> None:
    data = {
        (1, "唐揚げ"): [OpportunityOccurrence(sellout_step=10, suggested_increase=5)],
        (2, "おでん"): [OpportunityOccurrence(sellout_step=5, suggested_increase=50)],
        (3, "寿司"): [],  # 該当なし
    }

    result = rank_opportunities(data)

    assert [r.product_id for r in result] == [2, 1]


def test_rank_opportunities_limits_to_top_n() -> None:
    data = {
        (i, f"商品{i}"): [OpportunityOccurrence(sellout_step=5, suggested_increase=i)]
        for i in range(15)
    }

    result = rank_opportunities(data, limit=10)

    assert len(result) == 10
    assert result[0].product_id == 14  # 最大のsuggested_increase


def test_rank_opportunities_averages_multiple_occurrences() -> None:
    data = {
        (1, "唐揚げ"): [
            OpportunityOccurrence(sellout_step=10, suggested_increase=10),
            OpportunityOccurrence(sellout_step=20, suggested_increase=30),
        ],
    }

    result = rank_opportunities(data)

    assert result[0].occurrence_count == 2
    assert result[0].avg_suggested_increase == 20
    assert result[0].avg_sellout_step == 15


def test_build_step_records_matches_actual_run_simulation_output() -> None:
    """build_step_recordsの「次のステップから値引きが効く」という前提が、
    実際のrun_simulation（services/simulation.py）の挙動とズレていないことを検証する。
    DiscountRecommendationはis_new_recommendationの行だけが保存される想定なので、
    それだけを渡してrun_simulationが計算したrecommended_rateを再現できるか確認する。
    """
    product = ProductInput(
        product_id=1,
        name="test",
        initial_stock=15,
        elasticity=0.1,
        prior_alpha=10.0,  # 需要が高いので値引きなしで早く完売しやすい
        prior_beta=2.0,
    )

    outcome = run_simulation([product], target_waste_rate=0.5, seed=42)

    log_steps = [(s.step, s.quantity) for s in outcome.steps]
    rec_steps = [
        (s.step, s.recommended_rate) for s in outcome.steps if s.is_new_recommendation
    ]

    records = build_step_records(log_steps, rec_steps)

    actual_rates = {s.step: s.recommended_rate for s in outcome.steps}
    for r in records:
        assert r.recommended_rate == actual_rates[r.step]


def test_build_step_records_applies_rate_from_next_step_onward() -> None:
    # step1で値引き0.2が決まったら、そのrateが効いてくるのはstep2から（step1自体は0のまま）
    log_steps = [(0, 3), (1, 3), (2, 3)]
    recommendation_steps = [(1, 0.2)]

    records = build_step_records(log_steps, recommendation_steps)

    assert records[0].recommended_rate == 0.0
    assert records[1].recommended_rate == 0.0
    assert records[2].recommended_rate == 0.2
