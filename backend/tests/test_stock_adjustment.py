from services.stock_adjustment import compute_stock_adjustment


def test_increases_stock_on_early_sellout_without_discount() -> None:
    # 在庫10個を5ステップ（0〜4）で完売、値引きなし
    # → suggested_increase = round(10 * (48-5)/5) = 86。半分 = 43（1日48ステップ）
    log_steps = [(i, 2) for i in range(5)]
    result = compute_stock_adjustment(initial_stock=10, log_steps=log_steps, recommendation_steps=[])

    assert result is not None
    assert result.delta == 43
    assert result.new_initial_stock == 53
    assert result.reason == "opportunity"


def test_decreases_stock_on_overstock_despite_max_discount() -> None:
    # 最大値引き（70%を使ったテスト値。detect_overstockはMAX_DISCOUNT_RATE以上で判定）まで
    # 下げても、10個中3個しか売れず7個残る → suggested_decrease = 7。半分 = round(3.5) = 4
    log_steps = [(0, 1), (1, 1), (2, 1)]
    recommendation_steps = [(0, 0.75)]
    result = compute_stock_adjustment(
        initial_stock=10, log_steps=log_steps, recommendation_steps=recommendation_steps
    )

    assert result is not None
    assert result.delta == -4
    assert result.new_initial_stock == 6
    assert result.reason == "overstock"


def test_decrease_does_not_go_below_one() -> None:
    # 在庫5個のうち1個しか売れず4個残る（最大値引き済み）→ suggested_decrease=4、半分=2
    # 5 - 2 = 3 なので下限には掛からないケースと、下限に掛かるケースの両方を確認する
    log_steps = [(0, 1)]
    recommendation_steps = [(0, 0.75)]
    result = compute_stock_adjustment(
        initial_stock=2, log_steps=log_steps, recommendation_steps=recommendation_steps
    )

    assert result is not None
    # suggested_decrease=1（2-1）、半分は round(0.5)=... 最低1個は動かすので1。2-1=1（下限ちょうど）
    assert result.new_initial_stock >= 1


def test_no_adjustment_when_neither_opportunity_nor_overstock() -> None:
    # 値引きされたが最大値引きには達しておらず、かつ完売もしていない
    log_steps = [(0, 1), (1, 1)] + [(i, 0) for i in range(2, 48)]
    recommendation_steps = [(0, 0.30)]
    result = compute_stock_adjustment(
        initial_stock=10, log_steps=log_steps, recommendation_steps=recommendation_steps
    )

    assert result is None


def test_no_adjustment_when_sold_out_normally_late() -> None:
    # 閉店間際（45ステップ超）に値引きなしで完売 → 機会損失の対象外（§5.5の境界）
    log_steps = [(i, 0) for i in range(46)] + [(46, 10)]
    result = compute_stock_adjustment(initial_stock=10, log_steps=log_steps, recommendation_steps=[])

    assert result is None


def test_minimum_increase_is_one_even_if_rounds_to_zero() -> None:
    # suggested_increaseが小さくても、該当した以上は最低1個は増やす
    # steps_to_sellout=37なら suggested_increase = round(10 * (40-37)/37) = round(0.81) = 1。半分は0.5→round=0だが最低1
    log_steps = [(i, 0) for i in range(36)] + [(36, 10)]
    result = compute_stock_adjustment(initial_stock=10, log_steps=log_steps, recommendation_steps=[])

    assert result is not None
    assert result.delta >= 1
