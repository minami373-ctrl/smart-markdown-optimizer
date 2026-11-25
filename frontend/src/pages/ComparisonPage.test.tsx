import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ComparisonPage from './ComparisonPage'
import * as comparisonApi from '../api/comparison'
import type { ComparisonProduct, ComparisonResult } from '../api/types'

// jsdomはcanvasを実装していないため、値引き率推移グラフのLineは軽量スタブに差し替える
// （SimulationPage.test.tsxと同じ理由）
vi.mock('react-chartjs-2', () => ({
  Line: () => null,
}))

function makeSteps(rate: number): ComparisonProduct['fixed_steps'] {
  return Array.from({ length: 40 }, (_, step) => ({
    step,
    quantity: 1,
    remaining_stock: 40 - step,
    recommended_rate: rate,
  }))
}

const PRODUCT: ComparisonProduct = {
  product_id: 1,
  product_name: '唐揚げ',
  unit_price: null,
  dynamic_steps: makeSteps(0.3),
  dynamic_final_waste_rate: 0.1,
  fixed_steps: makeSteps(0.0),
  fixed_final_waste_rate: 0.4,
}

const RESULT: ComparisonResult = {
  products: [PRODUCT],
  fixed_schedule_30_step: 33,
  fixed_schedule_50_step: 38,
}

describe('ComparisonPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('比較するボタンを押すとcompareSchedulesを呼び、結果を表示する', async () => {
    const spy = vi.spyOn(comparisonApi, 'compareSchedules').mockResolvedValue(RESULT)

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    expect(await screen.findByText('唐揚げ')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith({
      weather: '晴れ',
      day_type: '平日',
      has_event: false,
      target_waste_rate: 0.03,
    })
  })

  it('廃棄率が改善していれば改善タグを表示する', async () => {
    vi.spyOn(comparisonApi, 'compareSchedules').mockResolvedValue(RESULT)

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    // fixed=40% dynamic=10% なので30%改善
    expect(await screen.findByText('廃棄率 30% 改善')).toBeInTheDocument()
  })

  it('単価が設定されている商品は推定売上の比較も表示する', async () => {
    const withPrice: ComparisonResult = {
      ...RESULT,
      products: [{ ...PRODUCT, unit_price: 350 }],
    }
    vi.spyOn(comparisonApi, 'compareSchedules').mockResolvedValue(withPrice)

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    expect(await screen.findAllByText(/推定売上/)).toHaveLength(2)
  })

  it('単価が未設定の商品には推定売上を表示しない', async () => {
    vi.spyOn(comparisonApi, 'compareSchedules').mockResolvedValue(RESULT)

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    await screen.findByText('唐揚げ')
    expect(screen.queryByText(/推定売上/)).not.toBeInTheDocument()
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(comparisonApi, 'compareSchedules').mockRejectedValue(new Error('比較に失敗しました'))

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    expect(await screen.findByText('比較に失敗しました')).toBeInTheDocument()
  })

  it('比較中はボタンが二重押し防止で無効化される', async () => {
    let resolvePromise: (value: ComparisonResult) => void = () => {}
    vi.spyOn(comparisonApi, 'compareSchedules').mockReturnValue(
      new Promise((resolve) => {
        resolvePromise = resolve
      }),
    )

    const user = userEvent.setup()
    render(<ComparisonPage />)
    await user.click(screen.getByRole('button', { name: '比較する' }))

    expect(screen.getByRole('button', { name: '比較中…' })).toBeDisabled()
    resolvePromise(RESULT)
  })
})
