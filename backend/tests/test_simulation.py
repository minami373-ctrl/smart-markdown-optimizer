from services.simulation import (
    ProductInput,
    _required_discount_rate,
    discount_multiplier,
    posterior_mode,
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


def test_posterior_mode_at_or_below_one_is_zero() -> None:
    assert posterior_mode(alpha=1.0, beta=2.0) == 0.0
    assert posterior_mode(alpha=0.5, beta=2.0) == 0.0


def test_posterior_mode_formula() -> None:
    assert posterior_mode(alpha=5.0, beta=2.0) == 2.0


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


def test_final_waste_rate_matches_remaining_stock() -> None:
    product = make_product(stock=30, alpha=3.0, beta=2.0)
    out = run_simulation([product], target_waste_rate=0.05, seed=9)

    final = out.finals[0]
    last_remaining = next(
        s.remaining_stock for s in reversed(out.steps) if s.product_id == product.product_id
    )
    assert final.final_waste_rate == last_remaining / product.initial_stock
