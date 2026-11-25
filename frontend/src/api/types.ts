export type Weather = '晴れ' | '曇り' | '雨'
export type DayType = '平日' | '休日'

export interface StepOut {
  product_id: number
  step: number
  quantity: number
  // 商品が削除済みだと初期在庫が分からず追跡できないため null になりうる（履歴の再構築時のみ）
  remaining_stock: number | null
  recommended_rate: number
  posterior_mean: number | null
  is_new_recommendation: boolean
  posterior_alpha: number | null
  posterior_beta: number | null
  //: モニターに出ている値引き率（承認済み。docs/spec.md §5.11）。recommended_rateより小さければ
  // ズバリ引きがナイトマネージャーの承認待ち。古いデータでは無いことがあるので任意
  applied_rate?: number
}

export interface FinalOut {
  product_id: number
  product_name: string
  final_waste_rate: number
  achieved: boolean
}

// 在庫の自動調整通知（docs/spec.md §5.7）。POSTのその場限りの通知で、
// GET（履歴の一覧・再取得）では常に空配列になる
export interface StockAdjustmentOut {
  product_id: number
  product_name: string
  delta: number // 正なら増加、負なら減少
  new_initial_stock: number
}

export interface SimulationSummary {
  id: number
  weather: Weather
  day_type: DayType
  has_event: boolean
  target_waste_rate: number
  //: ズバリ引きをナイトマネージャーが何ステップ後に承認するか（docs/spec.md §5.11）
  approval_delay_steps?: number
  status: string
  started_at: string
  finished_at: string | null
  finals: FinalOut[]
  stock_adjustments: StockAdjustmentOut[]
}

export interface SimulationDetail extends SimulationSummary {
  steps: StepOut[]
}

export interface PriorDemand {
  alpha: number
  beta: number
}

/** 商品の種類（docs/spec.md §2.1） */
export const PRODUCT_CATEGORIES = ['弁当・丼', '揚げ物の単品', '軽食・つまみ'] as const
export type ProductCategory = (typeof PRODUCT_CATEGORIES)[number]

export interface Product {
  id: number
  name: string
  category: ProductCategory
  initial_stock: number
  elasticity: number
  prior_demand: Record<string, PriorDemand>
  unit_price: number | null
}

export interface ProductCreateInput {
  name: string
  category: ProductCategory
  initial_stock: number
  elasticity: number
  base_demand: number
  unit_price?: number | null
}

export interface Opportunity {
  product_id: number
  product_name: string
  occurrence_count: number
  avg_sellout_step: number
  avg_suggested_increase: number
}

export interface Overstock {
  product_id: number
  product_name: string
  occurrence_count: number
  avg_final_remaining: number
  avg_suggested_decrease: number
}

// 在庫調整履歴（docs/spec.md §5.8）。stock_adjustmentsとは別に、
// 発生した調整そのものは商品ごとに永続化され、GET /api/products/{id}/stock-adjustmentsで
// 発生順（created_at昇順）に取得できる
export interface StockAdjustmentLogEntry {
  id: number
  run_id: number
  reason: 'opportunity' | 'overstock'
  delta: number // 正なら増加、負なら減少
  new_initial_stock: number
  created_at: string
}

// 固定スケジュール値引きとの比較（docs/spec.md §5.9）。POST /api/compareの応答はDBに
// 保存されないその場限りの結果（stock_adjustmentsと違い、永続化バージョンも存在しない）
export interface ScheduleStepOut {
  step: number
  quantity: number
  remaining_stock: number
  recommended_rate: number
}

export interface ComparisonProduct {
  product_id: number
  product_name: string
  unit_price: number | null
  dynamic_steps: ScheduleStepOut[]
  dynamic_final_waste_rate: number
  fixed_steps: ScheduleStepOut[]
  fixed_final_waste_rate: number
}

export interface ComparisonResult {
  products: ComparisonProduct[]
  fixed_schedule_30_step: number
  fixed_schedule_50_step: number
}

// 値引きタイミングの傾向分析（docs/spec.md §5.10）。天気・曜日・イベント有無の条件ごとの集計
export interface ConditionTiming {
  weather: Weather
  day_type: DayType
  has_event: boolean
  sample_count: number
  discounted_count: number
  avg_first_discount_step: number | null
}
