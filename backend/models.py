"""SQLModel テーブル定義（docs/spec.md §6）。

仕様書 §6 に無いカラムを勝手に足さない。追加が必要なら先に仕様書を直す。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

#: 天気・曜日区分・イベント有無の許容値（services/simulation.py と共有）
WEATHERS: tuple[str, ...] = ("晴れ", "曇り", "雨")
DAY_TYPES: tuple[str, ...] = ("平日", "休日")
#: 商品の種類（docs/spec.md §2.1・§6。2026-11-26追加）。先頭が既定値
CATEGORIES: tuple[str, ...] = ("弁当・丼", "揚げ物の単品", "軽食・つまみ")


class Product(SQLModel, table=True):
    """商品（初期状態は12件・seed投入。画面から追加・削除できる）。prior_demand は
    12通り（天気3×曜日2×イベント2）のガンマ分布パラメータを JSON 文字列で持つ。
    キー形式: f"{weather}_{day_type}_{'あり' if has_event else 'なし'}"
    """

    # sqlite_autoincrement: 削除した商品のidをSQLiteが使い回すと、過去の
    # PurchaseLog等が別の新しい商品を指してしまう（履歴の誤帰属）。それを防ぐ
    __table_args__ = {"sqlite_autoincrement": True}

    id: int | None = Field(default=None, primary_key=True)
    name: str
    # 種類（docs/spec.md §2.1）。売れ方の違いを値引き感度の差として表すための区分
    category: str = Field(default=CATEGORIES[0])
    initial_stock: int
    elasticity: float  # 値引き10%あたりの需要増加倍率
    prior_demand: str  # JSON文字列（12キー、各 {"alpha": float, "beta": float}）
    # 単価（円）。任意項目（docs/spec.md §6）。設定されている商品だけシミュレーション画面に
    # 推定売上を表示する。既存のapp.dbには自動マイグレーションされないため再作成が必要
    unit_price: int | None = None


class SimulationRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    weather: str
    day_type: str
    has_event: bool
    target_waste_rate: float
    # ズバリ引きをナイトマネージャーが何ステップ後に承認するか（docs/spec.md §5.11。0〜3）
    approval_delay_steps: int = 0
    status: str = Field(default="running")  # running / finished
    started_at: datetime
    finished_at: datetime | None = None


class PurchaseLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    step: int
    quantity: int
    # このステップの販売後に決まり、次のステップからモニターに出る値引き率（承認済み。§5.11）
    applied_rate: float = 0.0


class DiscountRecommendation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    step: int
    recommended_rate: float  # services/simulation.py の DISCOUNT_TIERS のいずれか（0/30%/半額、21時以降は55〜75%のズバリ引き）
    posterior_mean: float  # このときの事後分布の期待残数


class SimulationResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    final_waste_rate: float
    achieved: bool
    # この回を実行した時点の初期在庫のスナップショット（在庫の自動調整・§5.7で
    # Product.initial_stockが後から変わっても、/opportunities・/overstockが過去のrunを
    # 「実行当時と違う初期在庫」で誤って再評価しないようにするため）
    initial_stock: int


class StockAdjustmentLog(SQLModel, table=True):
    """在庫の自動調整（§5.7）が発生するたびに1行残る履歴（§5.8）。
    Product.initial_stockが「今いくつか」しか示さないのに対し、こちらは「どう変わってきたか」を
    後から追うためのもの。商品を削除しても消さない（Productと同じ「履歴は消さない」方針）。
    """

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    reason: str  # opportunity（機会損失で増加）/ overstock（過剰在庫で減少）
    delta: int  # 正なら増加、負なら減少
    new_initial_stock: int  # この調整の直後のProduct.initial_stock
    created_at: datetime
