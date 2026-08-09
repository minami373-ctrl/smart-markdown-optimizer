import { apiFetch } from './client'
import type { Product, ProductCreateInput } from './types'

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
