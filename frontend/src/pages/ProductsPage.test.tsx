import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProductsPage from './ProductsPage'
import * as productsApi from '../api/products'

describe('ProductsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('商品ごとに事前分布の表を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([
      {
        id: 1,
        name: '唐揚げ',
        initial_stock: 50,
        elasticity: 0.12,
        prior_demand: {
          晴れ_平日_なし: { alpha: 3.12, beta: 2.0 },
        },
      },
    ])

    render(<ProductsPage />)

    expect(await screen.findByText(/唐揚げ/)).toBeInTheDocument()
    expect(screen.getByText('晴れ / 平日 / なし')).toBeInTheDocument()
    expect(screen.getByText('3.12')).toBeInTheDocument()
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockRejectedValue(new Error('取得できませんでした'))

    render(<ProductsPage />)

    expect(await screen.findByText('取得できませんでした')).toBeInTheDocument()
  })
})
