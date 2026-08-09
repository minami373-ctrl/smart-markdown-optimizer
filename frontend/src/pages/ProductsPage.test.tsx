import { render, screen, waitFor, within } from '@testing-library/react'
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

  it('編集ボタンを押すと、基準需要が事前分布から逆算された状態でフォームが開く', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))

    const editCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    expect(editCard).toBeInTheDocument()
    // alpha 3.12 ÷ (1.2×1.0×1.0×2.0) = 1.3
    const baseDemandInput = within(editCard).getByLabelText(
      '基準需要（平日・晴れ・1stepの平均個数）',
    ) as HTMLInputElement
    expect(baseDemandInput.value).toBe('1.3')
  })

  it('編集して保存すると、updateProductを呼び一覧を再取得して編集を閉じる', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const updateSpy = vi.spyOn(productsApi, 'updateProduct').mockResolvedValue({
      ...ONE_PRODUCT[0],
      name: '唐揚げ大盛り',
    })

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))
    const editCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    const nameInput = within(editCard).getByLabelText('商品名') as HTMLInputElement
    await user.clear(nameInput)
    await user.type(nameInput, '唐揚げ大盛り')
    await user.click(within(editCard).getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(1, {
        name: '唐揚げ大盛り',
        initial_stock: 50,
        elasticity: 0.12,
        base_demand: 1.3,
      })
    })
    expect(productsApi.fetchProducts).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('唐揚げ を編集')).not.toBeInTheDocument()
  })

  it('キャンセルを押すとupdateProductを呼ばずに編集フォームを閉じる', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const updateSpy = vi.spyOn(productsApi, 'updateProduct')

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))
    await user.click(screen.getByRole('button', { name: 'キャンセル' }))

    expect(updateSpy).not.toHaveBeenCalled()
    expect(screen.queryByText('唐揚げ を編集')).not.toBeInTheDocument()
  })
})
