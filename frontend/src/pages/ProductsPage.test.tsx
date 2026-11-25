import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProductsPage from './ProductsPage'
import * as productsApi from '../api/products'
import type { Product } from '../api/types'

// jsdomはcanvasを実装していないため、在庫調整履歴グラフ（StockAdjustmentHistory）のLineは
// 軽量スタブに差し替える（SimulationPage.test.tsxと同じ理由。データ整形ロジック自体は
// lib/stockAdjustmentHistoryData.test.tsで直接テストする）
vi.mock('react-chartjs-2', () => ({
  Line: () => null,
}))

const ONE_PRODUCT: Product[] = [
  {
    id: 1,
    name: '唐揚げ',
    category: '弁当・丼',
    initial_stock: 50,
    elasticity: 0.12,
    prior_demand: { 晴れ_平日_なし: { alpha: 3.12, beta: 2.0 } },
    unit_price: null,
  },
]

describe('ProductsPage', () => {
  beforeEach(() => {
    // 在庫調整履歴（docs/spec.md §5.8）：この機能を検証するテスト以外では
    // 「まだ一度も調整が発生していない」状態（空配列）をデフォルトにする
    vi.spyOn(productsApi, 'fetchStockAdjustments').mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('商品ごとに事前分布の表を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([
      {
        id: 1,
        name: '唐揚げ',
        category: '弁当・丼',
        initial_stock: 50,
        elasticity: 0.12,
        prior_demand: {
          晴れ_平日_なし: { alpha: 3.12, beta: 2.0 },
        },
        unit_price: null,
      },
    ])

    render(<ProductsPage />)

    expect(await screen.findByText(/唐揚げ/)).toBeInTheDocument()
    expect(screen.getByText('晴れ / 平日 / なし')).toBeInTheDocument()
    expect(screen.getByText('3.12')).toBeInTheDocument()
  })

  it('単価が設定されている商品は一覧に単価を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([
      { ...ONE_PRODUCT[0], unit_price: 350 },
    ])

    render(<ProductsPage />)

    expect(await screen.findByText(/単価 ¥350/)).toBeInTheDocument()
  })

  it('単価が未設定の商品は単価を表示しない', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    render(<ProductsPage />)

    await screen.findByText(/唐揚げ/)
    // 「商品を追加」フォームには常に「単価（円・任意）」ラベルがあるため、
    // 商品カードの見出し（h2）だけを絞り込んで確認する
    const productHeading = screen.getByRole('heading', { level: 2, name: /唐揚げ/ })
    expect(productHeading.textContent).not.toContain('単価')
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
      category: '弁当・丼',
      initial_stock: 20,
      elasticity: 0.15,
      prior_demand: {},
      unit_price: null,
    })

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.click(screen.getByRole('button', { name: '追加' }))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({
        name: 'たこ焼き',
        category: '弁当・丼',
        initial_stock: 20,
        elasticity: 0.12,
        base_demand: 1,
        unit_price: null,
      })
    })
    // 追加後にfetchProductsが再度呼ばれる（初回1回＋追加後1回）
    expect(productsApi.fetchProducts).toHaveBeenCalledTimes(2)
  })

  it('単価を入力して追加すると、createProductに数値として渡される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const createSpy = vi.spyOn(productsApi, 'createProduct').mockResolvedValue({
      id: 2,
      name: 'たこ焼き',
      category: '弁当・丼',
      initial_stock: 20,
      elasticity: 0.15,
      prior_demand: {},
      unit_price: 300,
    })

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.type(screen.getByLabelText('単価（円・任意）'), '300')
    await user.click(screen.getByRole('button', { name: '追加' }))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'たこ焼き', unit_price: 300 }),
      )
    })
  })

  it('商品名が空だと追加ボタンが無効化される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    expect(screen.getByRole('button', { name: '追加' })).toBeDisabled()
  })

  it('商品名が空のときは「商品名を入力してください」のヒントを表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    expect(screen.getByText('商品名を入力してください')).toBeInTheDocument()
  })

  it('APIエラーと入力ヒントが同時に出ても、別クラス（.error/.hint）で見分けられる', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    vi.spyOn(productsApi, 'createProduct').mockRejectedValue(new Error('サーバーエラー'))

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.click(screen.getByRole('button', { name: '追加' }))
    const apiError = await screen.findByText('サーバーエラー')
    expect(apiError).toHaveClass('error')

    // 送信後に商品名を空へ戻すと、APIエラーは残ったまま入力ヒントも出る
    await user.clear(screen.getByLabelText('商品名'))
    const hint = await screen.findByText('商品名を入力してください')
    expect(hint).toHaveClass('hint')
    expect(screen.getByText('サーバーエラー')).toHaveClass('error')
  })

  it('商品名を埋めても初期在庫が0だとヒントが切り替わる（最初の1件だけを出す）', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    const stockInput = screen.getByLabelText('初期在庫')
    await user.clear(stockInput)
    await user.type(stockInput, '0')

    expect(screen.queryByText('商品名を入力してください')).not.toBeInTheDocument()
    expect(screen.getByText('初期在庫は1以上にしてください')).toBeInTheDocument()
  })

  it('すべての項目を満たすとヒントが消える', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')

    expect(screen.queryByText('商品名を入力してください')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '追加' })).not.toBeDisabled()
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

  it('編集の保存に失敗すると、編集中のカード自身にエラーを表示する（トップの「商品を追加」カードには出さない）', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    vi.spyOn(productsApi, 'updateProduct').mockRejectedValue(new Error('保存失敗'))

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))
    const editCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    await user.click(within(editCard).getByRole('button', { name: '保存' }))

    const errorInEditCard = await within(editCard).findByText('保存失敗')
    expect(errorInEditCard).toHaveClass('error')

    // トップの「商品を追加」カードには出ない
    const addCard = screen.getByText('商品を追加').closest('.card') as HTMLElement
    expect(within(addCard).queryByText('保存失敗')).not.toBeInTheDocument()
  })

  it('編集を開始すると、トップに残っていた追加失敗のエラーも一緒に消える', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    vi.spyOn(productsApi, 'createProduct').mockRejectedValue(new Error('追加失敗'))

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.click(screen.getByRole('button', { name: '追加' }))
    await screen.findByText('追加失敗')

    await user.click(screen.getByRole('button', { name: '編集' }))

    expect(screen.queryByText('追加失敗')).not.toBeInTheDocument()
  })

  it('編集の保存に失敗した後キャンセルすると、エラーも一緒に消える', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    vi.spyOn(productsApi, 'updateProduct').mockRejectedValue(new Error('保存失敗'))

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))
    const editCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    await user.click(within(editCard).getByRole('button', { name: '保存' }))
    await within(editCard).findByText('保存失敗')

    await user.click(within(editCard).getByRole('button', { name: 'キャンセル' }))

    expect(screen.queryByText('保存失敗')).not.toBeInTheDocument()
  })

  it('編集失敗後に別の商品の編集に切り替えると、前の失敗メッセージは残らない', async () => {
    const anotherProduct = { ...ONE_PRODUCT[0], id: 2, name: 'おでん' }
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([ONE_PRODUCT[0], anotherProduct])
    vi.spyOn(productsApi, 'updateProduct').mockRejectedValue(new Error('保存失敗'))

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    const [karaageEditButton] = screen.getAllByRole('button', { name: '編集' })
    await user.click(karaageEditButton)
    const karaageCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    await user.click(within(karaageCard).getByRole('button', { name: '保存' }))
    await within(karaageCard).findByText('保存失敗')

    // キャンセルせず、直接おでんの編集に切り替える
    const odenEditButton = screen.getByRole('button', { name: '編集' }) // 唐揚げは編集フォーム中なのでもう「編集」ボタンが無い
    await user.click(odenEditButton)

    expect(screen.queryByText('保存失敗')).not.toBeInTheDocument()
    expect(screen.getByText('おでん を編集')).toBeInTheDocument()
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
      '基準需要（晴れの平日・18分あたりに売れる平均の個数）',
    ) as HTMLInputElement
    expect(baseDemandInput.value).toBe('1.3')
  })

  it('編集ボタンを押すと、単価が現在の値でプリフィルされる', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([
      { ...ONE_PRODUCT[0], unit_price: 350 },
    ])

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.click(screen.getByRole('button', { name: '編集' }))

    const editCard = screen.getByText('唐揚げ を編集').closest('.card') as HTMLElement
    const unitPriceInput = within(editCard).getByLabelText('単価（円・任意）') as HTMLInputElement
    expect(unitPriceInput.value).toBe('350')
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
        category: '弁当・丼',
        initial_stock: 50,
        elasticity: 0.12,
        base_demand: 1.3,
        unit_price: null,
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

  it('在庫調整履歴が無い商品には履歴グラフを表示しない', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    // beforeEachのデフォルト（空配列）のまま

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    expect(screen.queryByText(/在庫調整履歴/)).not.toBeInTheDocument()
  })

  it('在庫調整履歴がある商品には発生理由の凡例つきでグラフを表示する（docs/spec.md §5.8）', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    vi.spyOn(productsApi, 'fetchStockAdjustments').mockResolvedValue([
      {
        id: 1,
        run_id: 10,
        reason: 'opportunity',
        delta: 20,
        new_initial_stock: 70,
        created_at: '2026-08-01T12:00:00',
      },
      {
        id: 2,
        run_id: 11,
        reason: 'overstock',
        delta: -5,
        new_initial_stock: 65,
        created_at: '2026-08-02T12:00:00',
      },
    ])

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    expect(await screen.findByText(/在庫調整履歴/)).toBeInTheDocument()
    expect(screen.getByText(/完売で増加/)).toBeInTheDocument()
    expect(screen.getByText(/売れ残りで減少/)).toBeInTheDocument()
  })

  it('商品ごとに別のfetchStockAdjustmentsを呼ぶ', async () => {
    const anotherProduct = { ...ONE_PRODUCT[0], id: 2, name: 'おでん' }
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([ONE_PRODUCT[0], anotherProduct])
    const adjustmentsSpy = vi.spyOn(productsApi, 'fetchStockAdjustments').mockResolvedValue([])

    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await waitFor(() => {
      expect(adjustmentsSpy).toHaveBeenCalledWith(1)
      expect(adjustmentsSpy).toHaveBeenCalledWith(2)
    })
  })

  it('種類を選んで追加すると、createProductに種類が渡される（docs/spec.md §2.1）', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue(ONE_PRODUCT)
    const createSpy = vi.spyOn(productsApi, 'createProduct').mockResolvedValue({
      id: 2,
      name: 'たこ焼き',
      category: '軽食・つまみ',
      initial_stock: 20,
      elasticity: 0.15,
      prior_demand: {},
      unit_price: null,
    })

    const user = userEvent.setup()
    render(<ProductsPage />)
    await screen.findByText(/唐揚げ/)

    await user.type(screen.getByLabelText('商品名'), 'たこ焼き')
    await user.selectOptions(screen.getByLabelText('種類'), '軽食・つまみ')
    await user.click(screen.getByRole('button', { name: '追加' }))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(expect.objectContaining({ category: '軽食・つまみ' }))
    })
  })
})
