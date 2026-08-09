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
