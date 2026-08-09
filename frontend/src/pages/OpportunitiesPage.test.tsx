import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OpportunitiesPage from './OpportunitiesPage'
import * as opportunitiesApi from '../api/opportunities'

describe('OpportunitiesPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('該当商品を順位付きで一覧表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([
      {
        product_id: 2,
        product_name: '大きい機会損失',
        occurrence_count: 3,
        avg_sellout_step: 10,
        avg_suggested_increase: 45.5,
      },
      {
        product_id: 1,
        product_name: '小さい機会損失',
        occurrence_count: 1,
        avg_sellout_step: 30,
        avg_suggested_increase: 5,
      },
    ])

    render(<OpportunitiesPage />)

    expect(await screen.findByText('大きい機会損失')).toBeInTheDocument()
    expect(screen.getByText('+46個')).toBeInTheDocument()
    expect(screen.getByText('30/40')).toBeInTheDocument()
    expect(screen.getByText('3回')).toBeInTheDocument()
  })

  it('該当商品が無ければ案内メッセージを表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([])

    render(<OpportunitiesPage />)

    expect(
      await screen.findByText('値引きなしで早期完売した商品はまだありません。'),
    ).toBeInTheDocument()
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockRejectedValue(new Error('取得失敗'))

    render(<OpportunitiesPage />)

    expect(await screen.findByText('取得失敗')).toBeInTheDocument()
  })
})
