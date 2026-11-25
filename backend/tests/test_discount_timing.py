from services.discount_timing import first_discount_step, summarize_condition_timing


def test_first_discount_step_returns_smallest_positive_step() -> None:
    assert first_discount_step([(5, 0.30), (10, 0.50), (20, 0.75)]) == 5


def test_first_discount_step_ignores_order() -> None:
    # DiscountRecommendationはstep順とは限らない前提でも正しく動くことを確認
    assert first_discount_step([(20, 0.75), (5, 0.30), (10, 0.50)]) == 5


def test_first_discount_step_returns_none_when_no_discount() -> None:
    assert first_discount_step([]) == None  # noqa: E711


def test_first_discount_step_ignores_non_positive_rates() -> None:
    # recommended_rate <= 0 の行は無視する（そもそもDiscountRecommendationには
    # 0%の行は記録されない設計だが、念のため0以下は値引きとして数えない）
    assert first_discount_step([(0, 0.0)]) is None


def test_summarize_condition_timing_with_no_samples() -> None:
    result = summarize_condition_timing("晴れ", "平日", False, [])

    assert result.sample_count == 0
    assert result.discounted_count == 0
    assert result.avg_first_discount_step is None


def test_summarize_condition_timing_all_discounted() -> None:
    result = summarize_condition_timing("雨", "平日", False, [5, 10, 15])

    assert result.sample_count == 3
    assert result.discounted_count == 3
    assert result.avg_first_discount_step == 10.0


def test_summarize_condition_timing_mixed_none_and_values() -> None:
    """値引きが無かった組（None）は平均の計算から除外されるが、sample_countには数える。"""
    result = summarize_condition_timing("晴れ", "休日", True, [None, None, 20])

    assert result.sample_count == 3
    assert result.discounted_count == 1
    assert result.avg_first_discount_step == 20.0


def test_summarize_condition_timing_all_none() -> None:
    result = summarize_condition_timing("晴れ", "平日", False, [None, None])

    assert result.sample_count == 2
    assert result.discounted_count == 0
    assert result.avg_first_discount_step is None


def test_summarize_condition_timing_preserves_condition_fields() -> None:
    result = summarize_condition_timing("雨", "休日", True, [3])

    assert result.weather == "雨"
    assert result.day_type == "休日"
    assert result.has_event is True
