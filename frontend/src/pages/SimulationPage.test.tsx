import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SimulationPage from './SimulationPage'
import * as productsApi from '../api/products'
import * as simulationsApi from '../api/simulations'
import type { Product, SimulationDetail } from '../api/types'

// jsdomはcanvasを実装していない。responsive:trueのLine（在庫推移グラフ）は、chart.js内部の
// リサイズ監視（bindResponsiveEvents → Chart._resize → getComputedStyle）がsetIntervalによる
// 連続更新の途中でcanvas未添付を検知した際に `getComputedStyle(null)` で例外を投げる
// （jsdom環境固有の問題でアプリの不具合ではない。原因を実測で確認済み）。
// 描画結果ではなくページのロジックを検証したいテストのため、Lineは軽量スタブに差し替える。
// 在庫推移グラフのデータ整形ロジック自体は lib/stockChartData.test.ts で直接テストする。
vi.mock('react-chartjs-2', () => ({
  Line: () => null,
}))

const PRODUCT: Product = {
  id: 1,
  name: '唐揚げ',
  initial_stock: 10,
  elasticity: 0.12,
  prior_demand: { 晴れ_平日_なし: { alpha: 3.0, beta: 2.0 } },
  unit_price: null,
}

function makeDetail(id: number, wasteRate: number): SimulationDetail {
  return {
    id,
    weather: '晴れ',
    day_type: '平日',
    has_event: false,
    target_waste_rate: 0.03,
    status: 'finished',
    started_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: wasteRate, achieved: true }],
    stock_adjustments: [],
    steps: [
      {
        product_id: 1,
        step: 0,
        quantity: 0,
        remaining_stock: 10,
        recommended_rate: 0,
        posterior_mean: 3.5,
        is_new_recommendation: false,
        posterior_alpha: 5.0,
        posterior_beta: 2.0,
      },
    ],
  }
}

describe('SimulationPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('初期状態では条件設定を促す文言を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])

    render(<SimulationPage />)

    expect(await screen.findByText('条件を設定して「営業開始」を押してください。')).toBeInTheDocument()
  })

  it('開始前は現在時刻を表示せず、開始後は営業時間内の時刻（開始10:00→終了21:00）を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue(makeDetail(1, 0))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')
    expect(screen.queryByText(/^現在 /)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    await screen.findByText('現在 10:00')

    await waitFor(
      () => {
        expect(screen.getByText('現在 21:00')).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })

  it('目標廃棄率のプリセットボタンを押すと、スライダーの値と表示が切り替わる', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue({
      id: 1,
      weather: '晴れ',
      day_type: '平日',
      has_event: false,
      target_waste_rate: 0.05,
      status: 'finished',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      finals: [],
      stock_adjustments: [],
      steps: [],
    })

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    expect(screen.getByText('目標廃棄率（3%）')).toBeInTheDocument() // 既定3%

    await user.click(screen.getByRole('button', { name: '5%' }))

    expect(screen.getByText('目標廃棄率（5%）')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({ target_waste_rate: 0.05 }),
    )
  })

  it('営業開始を押すと、現在の条件でシミュレーションを作成し、完了後に実績が表示される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const detail: SimulationDetail = {
      id: 1,
      weather: '雨',
      day_type: '休日',
      has_event: true,
      target_waste_rate: 0.03,
      status: 'finished',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.1, achieved: false }],
      stock_adjustments: [],
      // 1ステップだけにして、アニメーションがすぐ終わるようにする
      steps: [
        {
          product_id: 1,
          step: 0,
          quantity: 2,
          remaining_stock: 8,
          recommended_rate: 0.2,
          posterior_mean: 3.5,
          is_new_recommendation: true,
          posterior_alpha: 5.0,
          posterior_beta: 2.0,
        },
      ],
    }
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue(detail)

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    await user.selectOptions(screen.getByLabelText('天気'), '雨')
    await user.selectOptions(screen.getByLabelText('曜日'), '休日')
    await user.click(screen.getByLabelText('イベント'))
    await user.click(screen.getByRole('button', { name: '営業開始' }))

    expect(createSpy).toHaveBeenCalledWith({
      weather: '雨',
      day_type: '休日',
      has_event: true,
      target_waste_rate: 0.03,
    })

    // アニメーション完了（0.5秒間隔で1ステップぶん）を待ってから実績が出る
    await waitFor(
      () => {
        expect(screen.getByText(/実績廃棄率: 10%/)).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
    expect(screen.getByText('目標未達')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '営業開始' })).not.toBeDisabled()
    // 在庫推移グラフはシミュレーション開始後に表示される（docs/spec.md §4①）
    expect(screen.getByText('在庫推移')).toBeInTheDocument()
    // このテストのPRODUCTはunit_priceが未設定なので推定売上は表示されない
    expect(screen.queryByText(/推定売上/)).not.toBeInTheDocument()
    // このテストのdetailにはstock_adjustmentsが無いので自動調整の通知も出ない
    expect(screen.queryByText(/在庫を自動調整/)).not.toBeInTheDocument()
  })

  it('在庫が自動調整された商品は、終了後にその通知を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const detail: SimulationDetail = {
      ...makeDetail(1, 0),
      stock_adjustments: [
        { product_id: 1, product_name: '唐揚げ', delta: 25, new_initial_stock: 35 },
      ],
    }
    vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue(detail)

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    expect(
      await screen.findByText('在庫を自動調整：+25個（次回の初期在庫 35個）'),
    ).toBeInTheDocument()
  })

  it('単価が設定されている商品は、シミュレーション終了後に推定売上を表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([
      { ...PRODUCT, unit_price: 100 },
    ])
    const detail: SimulationDetail = {
      id: 1,
      weather: '晴れ',
      day_type: '平日',
      has_event: false,
      target_waste_rate: 0.03,
      status: 'finished',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.0, achieved: true }],
      stock_adjustments: [],
      steps: [
        {
          // 値引き0%（決定前）で2個販売 → 2 * 100 = 200円
          product_id: 1,
          step: 0,
          quantity: 2,
          remaining_stock: 8,
          recommended_rate: 0.5, // ここで決まった値引きはstep1から効く
          posterior_mean: 3.5,
          is_new_recommendation: true,
          posterior_alpha: 5.0,
          posterior_beta: 2.0,
        },
        {
          // 前ステップで決まった50%引きが効く → 4 * 100 * 0.5 = 200円
          product_id: 1,
          step: 1,
          quantity: 4,
          remaining_stock: 4,
          recommended_rate: 0.5,
          posterior_mean: 2.0,
          is_new_recommendation: false,
          posterior_alpha: 6.0,
          posterior_beta: 3.0,
        },
      ],
    }
    vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue(detail)

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    // 200円 + 200円 = 400円
    await waitFor(
      () => {
        expect(screen.getByText('推定売上: ¥400')).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })

  it('営業開始が完了すると、学習の継続で書き換わった事前分布を反映するため商品一覧を取り直す', async () => {
    const fetchSpy = vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const detail: SimulationDetail = {
      id: 1,
      weather: '晴れ',
      day_type: '平日',
      has_event: false,
      target_waste_rate: 0.03,
      status: 'finished',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.0, achieved: true }],
      stock_adjustments: [],
      steps: [
        {
          product_id: 1,
          step: 0,
          quantity: 2,
          remaining_stock: 8,
          recommended_rate: 0.0,
          posterior_mean: 3.5,
          is_new_recommendation: false,
          posterior_alpha: 5.0,
          posterior_beta: 2.0,
        },
      ],
    }
    vi.spyOn(simulationsApi, 'createSimulation').mockResolvedValue(detail)

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')
    expect(fetchSpy).toHaveBeenCalledTimes(1) // マウント時の初回取得ぶん

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    // createSimulation成功直後にfetchProductsが呼び直される（マウント時＋完了後の2回）
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(2)
    })
  })

  it('連続実行を押すと指定回数ぶんcreateSimulationが直列で呼ばれ、学習曲線グラフが表示される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation')
    createSpy.mockResolvedValueOnce(makeDetail(1, 0.3))
    createSpy.mockResolvedValueOnce(makeDetail(2, 0.1))
    createSpy.mockResolvedValueOnce(makeDetail(3, 0.02))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    const countInput = screen.getByLabelText('連続実行（同条件で学習を進める）')
    await user.clear(countInput)
    await user.type(countInput, '3')
    await user.click(screen.getByRole('button', { name: '連続実行' }))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledTimes(3)
    })
    expect(await screen.findByText('学習曲線（連続実行 3回）')).toBeInTheDocument()
    // 最後（3回目）の結果が、通常の営業開始と同じアニメーションで再生されて画面に出る
    await waitFor(
      () => {
        expect(screen.getByText(/実績廃棄率: 2%/)).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })

  it('連続実行が本当に直列であること：前の回の完了前に次のcreateSimulationを呼ばない', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    let resolveFirst: (v: SimulationDetail) => void = () => {}
    const firstPending = new Promise<SimulationDetail>((resolve) => {
      resolveFirst = resolve
    })
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation')
    createSpy.mockReturnValueOnce(firstPending)
    createSpy.mockResolvedValueOnce(makeDetail(2, 0.1))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    const countInput = screen.getByLabelText('連続実行（同条件で学習を進める）')
    await user.clear(countInput)
    await user.type(countInput, '2')
    await user.click(screen.getByRole('button', { name: '連続実行' }))

    // 1回目がまだ解決していない間は、2回目はまだ呼ばれていないはず（並列実装なら失敗する）
    expect(createSpy).toHaveBeenCalledTimes(1)

    resolveFirst(makeDetail(1, 0.3))

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledTimes(2)
    })
  })

  it('連続実行後に営業開始（単発実行）を押すと、学習曲線グラフは消える', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation')
    createSpy.mockResolvedValueOnce(makeDetail(1, 0.3))
    createSpy.mockResolvedValueOnce(makeDetail(2, 0.1))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    const countInput = screen.getByLabelText('連続実行（同条件で学習を進める）')
    await user.clear(countInput)
    await user.type(countInput, '2')
    await user.click(screen.getByRole('button', { name: '連続実行' }))

    expect(await screen.findByText('学習曲線（連続実行 2回）')).toBeInTheDocument()

    // 連続実行の最後の回のアニメーション再生が終わる（営業開始ボタンが再度押せるようになる）まで待つ
    await waitFor(
      () => {
        expect(screen.getByRole('button', { name: '営業開始' })).not.toBeDisabled()
      },
      { timeout: 2000 },
    )

    createSpy.mockResolvedValueOnce(makeDetail(3, 0.05))
    await user.click(screen.getByRole('button', { name: '営業開始' }))

    await waitFor(() => {
      expect(screen.queryByText(/学習曲線/)).not.toBeInTheDocument()
    })
  })

  it('連続実行前は学習曲線グラフを表示しない', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])

    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    expect(screen.queryByText(/学習曲線/)).not.toBeInTheDocument()
  })

  it('連続実行の途中でエラーが起きたら打ち切ってエラーメッセージを表示する', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    const createSpy = vi.spyOn(simulationsApi, 'createSimulation')
    createSpy.mockResolvedValueOnce(makeDetail(1, 0.3))
    createSpy.mockRejectedValueOnce(new Error('2回目で失敗'))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    // デフォルトの5回のうち2回目で失敗させる
    await user.click(screen.getByRole('button', { name: '連続実行' }))

    expect(await screen.findByText('2回目で失敗')).toBeInTheDocument()
    expect(createSpy).toHaveBeenCalledTimes(2) // 3回目以降は呼ばれない
    expect(screen.queryByText(/学習曲線/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '連続実行' })).not.toBeDisabled()
  })

  it('連続実行中は営業開始・連続実行の両方のボタンが無効化される', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    let resolveFirst: (v: SimulationDetail) => void = () => {}
    const pending = new Promise<SimulationDetail>((resolve) => {
      resolveFirst = resolve
    })
    vi.spyOn(simulationsApi, 'createSimulation').mockReturnValue(pending)

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    const countInput = screen.getByLabelText('連続実行（同条件で学習を進める）')
    await user.clear(countInput)
    await user.type(countInput, '1')
    await user.click(screen.getByRole('button', { name: '連続実行' }))

    expect(screen.getByRole('button', { name: '営業開始' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '連続実行中…' })).toBeDisabled()

    resolveFirst(makeDetail(1, 0.1))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '連続実行' })).not.toBeDisabled()
    })
  })

  it('営業開始前は在庫推移グラフを表示しない', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])

    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    expect(screen.queryByText('在庫推移')).not.toBeInTheDocument()
  })

  it('API呼び出しが失敗したらエラーメッセージを表示し、ボタンを再度押せるようにする', async () => {
    vi.spyOn(productsApi, 'fetchProducts').mockResolvedValue([PRODUCT])
    vi.spyOn(simulationsApi, 'createSimulation').mockRejectedValue(new Error('サーバーエラー'))

    const user = userEvent.setup()
    render(<SimulationPage />)
    await screen.findByText('条件を設定して「営業開始」を押してください。')

    await user.click(screen.getByRole('button', { name: '営業開始' }))

    expect(await screen.findByText('サーバーエラー')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '営業開始' })).not.toBeDisabled()
  })
})
