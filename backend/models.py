"""SQLModel テーブル定義（docs/spec.md §6）。

仕様書 §6 に無いカラムを勝手に足さない。追加が必要なら先に仕様書を直す。
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

#: 天気・曜日区分・イベント有無の許容値（services/simulation.py と共有）
WEATHERS: tuple[str, ...] = ("晴れ", "曇り", "雨")
DAY_TYPES: tuple[str, ...] = ("平日", "休日")


class Product(SQLModel, table=True):
    """商品（seed固定・3件）。prior_demand は12通り（天気3×曜日2×イベント2）の
    ガンマ分布パラメータを JSON 文字列で持つ。
    キー形式: f"{weather}_{day_type}_{'あり' if has_event else 'なし'}"
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str
    initial_stock: int
    elasticity: float  # 値引き10%あたりの需要増加倍率
    prior_demand: str  # JSON文字列（12キー、各 {"alpha": float, "beta": float}）


class SimulationRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    weather: str
    day_type: str
    has_event: bool
    target_waste_rate: float
    status: str = Field(default="running")  # running / finished
    started_at: datetime
    finished_at: datetime | None = None


class PurchaseLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    step: int
    quantity: int


class DiscountRecommendation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    step: int
    recommended_rate: float  # 0.0〜0.70
    posterior_mean: float  # このときの事後分布の期待残数


class SimulationResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulationrun.id")
    product_id: int = Field(foreign_key="product.id")
    final_waste_rate: float
    achieved: bool
