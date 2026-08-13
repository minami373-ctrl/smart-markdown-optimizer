import { apiFetch } from './client'
import type { Product, ProductCreateInput, StockAdjustmentLogEntry } from './types'

export function fetchProducts(): Promise<Product[]> {
  return apiFetch<Product[]>('/products')
}

export function createProduct(input: ProductCreateInput): Promise<Product> {
  return apiFetch<Product>('/products', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateProduct(id: number, input: ProductCreateInput): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}

// 在庫調整履歴（docs/spec.md §5.8）。発生順（created_at昇順）で返る
export function fetchStockAdjustments(productId: number): Promise<StockAdjustmentLogEntry[]> {
  return apiFetch<StockAdjustmentLogEntry[]>(`/products/${productId}/stock-adjustments`)
}
