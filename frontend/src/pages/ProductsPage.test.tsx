import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProductsPage from './ProductsPage'
import * as productsApi from '../api/products'

const ONE_PRODUCT = [
  {
    id: 1,
    name: '唐揚げ',
    initial_stock: 50,
    elasticity: 0.12,
    prior_demand: { 晴れ_平日_なし: { alpha: 3.12, beta: 2.0 } },
  },
]

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

  it('フォームに入力して追加すると、createProductを呼び一覧を再取得する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const createSpy = vi.spyOn(productsApi, 'createProduct').mockResolvedValue({
      id: 2,
      name: 'たこ焼き',
      initial_stock: 20,
      elasticity: 0.15,
      prior_demand: {},
    })

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.click(screen.getByRole('button', { name: '追加' }))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({
        name: 'たこ焼き',
        initial_stock: 20,
        elasticity: 0.12,
        base_demand: 1,
      })
    })
    // 追加後にfetchProductsが再度呼ばれる（初回1回＋追加後1回）
    expect(productsApi.fetchProducts).toHaveBeenCalledTimes(2)
  })

  it('商品名が空だと追加ボタンが無効化される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    expect(screen.getByRole('button', { name: '追加' })).toBeDisabled()
  })

  it('削除ボタンを押すとdeleteProductを呼び一覧を再取得する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const deleteSpy = vi.spyOn(productsApi, 'deleteProduct').mockResolvedValue(undefined)

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '削除' }))

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(1)
    })
    expect(productsApi.fetchProducts).toHaveBeenCalledTimes(2)
  })
})
