from services.overstock import (
    MAX_DISCOUNT_RATE,
    OverstockOccurrence,
    detect_overstock,
    rank_overstocks,
)
from services.simulation import MAX_DISCOUNT, ProductInput, run_simulation


def test_max_discount_rate_matches_simulation_constant() -> None:
    """services/simulation.pyのMAX_DISCOUNTとズレていないことを保証する
    （§5.6は§5.3と同じ値である前提のため）。"""
    assert MAX_DISCOUNT_RATE == MAX_DISCOUNT


def test_detects_overstock_when_max_discount_reached_but_not_sold_out() -> None:
    result = detect_overstock(
        recommended_rates=[0.3, 0.5, 0.75], quantities=[2, 2, 2], initial_stock=10
    )

    assert result is not None
    assert result.final_remaining == 4  # 10 - 6
    assert result.suggested_decrease == 4


def test_not_detected_if_max_discount_never_reached() -> None:
    result = detect_overstock(
        recommended_rates=[0.3, 0.5], quantities=[2, 2, 2], initial_stock=10
    )

    assert result is None


def test_not_detected_if_sold_out_despite_max_discount() -> None:
    result = detect_overstock(
        recommended_rates=[0.5, 0.75], quantities=[5, 5], initial_stock=10
    )

    assert result is None  # ちょうど完売（残り0）


def test_not_detected_if_no_discount_recommendations_at_all() -> None:
    result = detect_overstock(recommended_rates=[], quantities=[3, 3], initial_stock=10)

    assert result is None


def test_zero_initial_stock_returns_none() -> None:
    result = detect_overstock(recommended_rates=[0.75], quantities=[], initial_stock=0)

    assert result is None


def test_rank_overstocks_sorts_by_avg_suggested_decrease_desc() -> None:
    data = {
        (1, "唐揚げ"): [OverstockOccurrence(final_remaining=5, suggested_decrease=5)],
        (2, "おでん"): [OverstockOccurrence(final_remaining=20, suggested_decrease=20)],
        (3, "寿司"): [],  # 該当なし
    }

    result = rank_overstocks(data)

    assert [r.product_id for r in result] == [2, 1]


def test_rank_overstocks_limits_to_top_n() -> None:
    data = {
        (i, f"商品{i}"): [OverstockOccurrence(final_remaining=i, suggested_decrease=i)]
        for i in range(15)
    }

    result = rank_overstocks(data, limit=10)

    assert len(result) == 10
    assert result[0].product_id == 14  # 最大のsuggested_decrease


def test_rank_overstocks_averages_multiple_occurrences() -> None:
    data = {
        (1, "唐揚げ"): [
            OverstockOccurrence(final_remaining=10, suggested_decrease=10),
            OverstockOccurrence(final_remaining=30, suggested_decrease=30),
        ],
    }

    result = rank_overstocks(data)

    assert result[0].occurrence_count == 2
    assert result[0].avg_suggested_decrease == 20
    assert result[0].avg_final_remaining == 20


def test_detect_overstock_against_real_run_simulation_output() -> None:
    """低い需要・大きい在庫の組み合わせで、実際のrun_simulationが最大値引きまで下げても
    売り切れないケースを生成することを確認する（detect_overstockの前提が現実と一致するか）。

    elasticity=0.02という低めの値を使うのは、値引き感度の式が2乗（docs/spec.md §5.3
    「値引き感度：大きい値引きほど急激に効く」。2026-08-15改訂）になったことで、以前
    使っていたelasticity=0.1では最大値引き時の需要倍率が非常に強くなり（1+0.1×7.5²=6.625倍）、
    このテストが前提とする「最大値引きまで下げても売り切れない」ケースを再現できなくなった
    （完売してしまう）ため。"""
    product = ProductInput(
        product_id=1,
        name="test",
        initial_stock=100,
        elasticity=0.02,
        prior_alpha=1.0,  # 需要が非常に低い
        prior_beta=2.0,
    )

    # seed=0（elasticity変更前は7を使っていた）：0でも過剰在庫になることを確認済み。
    # 値引き感度の値を変えたついでに、既存の慣例（0番から使う）に揃えただけで他意は無い
    outcome = run_simulation([product], target_waste_rate=0.0, seed=0)

    rates = [s.recommended_rate for s in outcome.steps if s.is_new_recommendation]
    quantities = [s.quantity for s in outcome.steps]
    final = outcome.finals[0]

    # その日に実際に作った量（朝の分＋16時の補充。§5.18）を初期在庫として判定する
    result = detect_overstock(rates, quantities, final.produced)

    assert final.final_waste_rate > 0  # 完売していない
    assert result is not None
    assert result.final_remaining == round(final.final_waste_rate * final.produced)
