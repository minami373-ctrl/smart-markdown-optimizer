import { apiFetch } from './client'
import type { DayType, SimulationDetail, SimulationSummary, Weather } from './types'

export interface CreateSimulationInput {
  weather: Weather
  day_type: DayType
  has_event: boolean
  target_waste_rate: number
}

export function createSimulation(input: CreateSimulationInput): Promise<SimulationDetail> {
  return apiFetch<SimulationDetail>('/simulations', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function fetchSimulations(): Promise<SimulationSummary[]> {
  return apiFetch<SimulationSummary[]>('/simulations')
}

export function fetchSimulation(id: number): Promise<SimulationDetail> {
  return apiFetch<SimulationDetail>(`/simulations/${id}`)
}
