import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OverstockPage from './OverstockPage'
import * as overstockApi from '../api/overstock'

describe('OverstockPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('該当商品を順位付きで一覧表示する', async () => {
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([
      {
        product_id: 2,
        product_name: '大きい過剰在庫',
        occurrence_count: 3,
        avg_final_remaining: 20,
        avg_suggested_decrease: 20.5,
      },
      {
        product_id: 1,
        product_name: '小さい過剰在庫',
        occurrence_count: 1,
        avg_final_remaining: 2,
        avg_suggested_decrease: 2,
      },
    ])

    render(<OverstockPage />)

    expect(await screen.findByText('大きい過剰在庫')).toBeInTheDocument()
    expect(screen.getByText('-21個')).toBeInTheDocument()
    expect(screen.getByText('20個')).toBeInTheDocument()
    expect(screen.getByText('3回')).toBeInTheDocument()
  })

  it('該当商品が無ければ案内メッセージを表示する', async () => {
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([])

    render(<OverstockPage />)

    expect(
      await screen.findByText('値引き上限まで下げても売れ残った商品はまだありません。'),
    ).toBeInTheDocument()
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(overstockApi, 'fetchOverstocks').mockRejectedValue(new Error('取得失敗'))

    render(<OverstockPage />)

    expect(await screen.findByText('取得失敗')).toBeInTheDocument()
  })
})
