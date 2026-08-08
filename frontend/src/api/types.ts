export type Weather = '晴れ' | '曇り' | '雨'
export type DayType = '平日' | '休日'

export interface StepOut {
  product_id: number
  step: number
  quantity: number
  remaining_stock: number
  recommended_rate: number
  posterior_mean: number | null
  is_new_recommendation: boolean
}

export interface FinalOut {
  product_id: number
  product_name: string
  final_waste_rate: number
  achieved: boolean
}

export interface SimulationSummary {
  id: number
  weather: Weather
  day_type: DayType
  has_event: boolean
  target_waste_rate: number
  status: string
  started_at: string
  finished_at: string | null
  finals: FinalOut[]
}

export interface SimulationDetail extends SimulationSummary {
  steps: StepOut[]
}

export interface PriorDemand {
  alpha: number
  beta: number
}

export interface Product {
  id: number
  name: string
  initial_stock: number
  elasticity: number
  prior_demand: Record<string, PriorDemand>
}
