from services.prior import generate_prior_demand


def test_generates_all_12_condition_keys() -> None:
    result = generate_prior_demand(1.0)

    assert len(result) == 12
    assert "晴れ_平日_なし" in result
    assert "雨_休日_あり" in result


def test_sunny_has_higher_demand_than_rain() -> None:
    result = generate_prior_demand(1.0)

    sunny = result["晴れ_平日_なし"]["alpha"]
    rain = result["雨_平日_なし"]["alpha"]
    assert sunny > rain


def test_holiday_and_event_increase_demand() -> None:
    result = generate_prior_demand(1.0)

    base = result["晴れ_平日_なし"]["alpha"]
    holiday = result["晴れ_休日_なし"]["alpha"]
    event = result["晴れ_平日_あり"]["alpha"]
    assert holiday > base
    assert event > base


def test_beta_is_fixed_at_2() -> None:
    result = generate_prior_demand(3.5)

    assert all(v["beta"] == 2.0 for v in result.values())


def test_alpha_scales_linearly_with_base_demand() -> None:
    small = generate_prior_demand(1.0)
    large = generate_prior_demand(2.0)

    for key in small:
        assert large[key]["alpha"] == small[key]["alpha"] * 2
