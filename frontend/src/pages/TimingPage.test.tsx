import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TimingPage from './TimingPage'
import * as discountTimingApi from '../api/discountTiming'
import type { ConditionTiming } from '../api/types'

describe('TimingPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('12マスのヒートマップを表示する', async () => {
    vi.spyOn(discountTimingApi, 'fetchDiscountTiming').mockResolvedValue([])

    render(<TimingPage />)

    await screen.findByText('まだ完了したシミュレーションがありません。シミュレーションを実行すると集計されます。')
    expect(screen.getAllByText('データなし')).toHaveLength(12)
  })

  it('データがある条件は平均時刻と発生割合を表示する', async () => {
    const conditions: ConditionTiming[] = [
      {
        weather: '雨',
        day_type: '平日',
        has_event: false,
        sample_count: 4,
        discounted_count: 3,
        avg_first_discount_step: 20, // stepToClockTime(20)=15:00（15分×48ステップ）
      },
    ]
    vi.spyOn(discountTimingApi, 'fetchDiscountTiming').mockResolvedValue(conditions)

    render(<TimingPage />)

    expect(await screen.findByText('発生 3/4回')).toBeInTheDocument()
    expect(screen.getByText('15:00ごろ')).toBeInTheDocument()
    // データがある1マス以外の11マスは引き続き「データなし」
    expect(screen.getAllByText('データなし')).toHaveLength(11)
  })

  it('値引きが一度も発生していない条件は「値引きなし」と表示する', async () => {
    const conditions: ConditionTiming[] = [
      {
        weather: '晴れ',
        day_type: '休日',
        has_event: true,
        sample_count: 2,
        discounted_count: 0,
        avg_first_discount_step: null,
      },
    ]
    vi.spyOn(discountTimingApi, 'fetchDiscountTiming').mockResolvedValue(conditions)

    render(<TimingPage />)

    expect(await screen.findByText('値引きなし')).toBeInTheDocument()
    expect(screen.getByText('発生 0/2回')).toBeInTheDocument()
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(discountTimingApi, 'fetchDiscountTiming').mockRejectedValue(new Error('取得失敗'))

    render(<TimingPage />)

    expect(await screen.findByText('取得失敗')).toBeInTheDocument()
  })
})
