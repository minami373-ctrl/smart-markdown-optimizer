import { apiFetch } from './client'
import type { Product } from './types'

export function fetchProducts(): Promise<Product[]> {
  return apiFetch<Product[]>('/products')
}
