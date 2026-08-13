import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsightsBanner from './InsightsBanner'
import * as opportunitiesApi from '../api/opportunities'
import * as overstockApi from '../api/overstock'

function renderBanner() {
  return render(
    <MemoryRouter>
      <InsightsBanner />
    </MemoryRouter>,
  )
}

describe('InsightsBanner', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('両方0件なら何も表示しない', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([])
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([])

    const { container } = renderBanner()

    // fetchが解決するのを待ってから「何も無い」ことを確認する
    await waitFor(() => {
      expect(opportunitiesApi.fetchOpportunities).toHaveBeenCalled()
    })
    expect(container).toBeEmptyDOMElement()
  })

  it('機会損失が1件以上あれば案内文とリンクを表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([
      { product_id: 1, product_name: '唐揚げ', occurrence_count: 1, avg_sellout_step: 10, avg_suggested_increase: 5 },
      { product_id: 2, product_name: 'おでん', occurrence_count: 1, avg_sellout_step: 5, avg_suggested_increase: 10 },
    ])
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([])

    renderBanner()

    expect(await screen.findByText('在庫不足の可能性がある商品が2件あります。')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: '詳しく見る →' })
    expect(link).toHaveAttribute('href', '/opportunities')
  })

  it('過剰在庫が1件以上あれば案内文とリンクを表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([])
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([
      { product_id: 1, product_name: '唐揚げ', occurrence_count: 1, avg_final_remaining: 5, avg_suggested_decrease: 5 },
    ])

    renderBanner()

    expect(await screen.findByText('過剰在庫の可能性がある商品が1件あります。')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: '詳しく見る →' })
    expect(link).toHaveAttribute('href', '/overstock')
  })

  it('両方1件以上あれば2行とも表示する', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockResolvedValue([
      { product_id: 1, product_name: '唐揚げ', occurrence_count: 1, avg_sellout_step: 10, avg_suggested_increase: 5 },
    ])
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([
      { product_id: 2, product_name: 'おでん', occurrence_count: 1, avg_final_remaining: 5, avg_suggested_decrease: 5 },
    ])

    renderBanner()

    expect(await screen.findByText('在庫不足の可能性がある商品が1件あります。')).toBeInTheDocument()
    expect(await screen.findByText('過剰在庫の可能性がある商品が1件あります。')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '詳しく見る →' })).toHaveLength(2)
  })

  it('機会損失の取得に失敗しても、過剰在庫の行は表示され続ける', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockRejectedValue(new Error('取得失敗'))
    vi.spyOn(overstockApi, 'fetchOverstocks').mockResolvedValue([
      { product_id: 1, product_name: '唐揚げ', occurrence_count: 1, avg_final_remaining: 5, avg_suggested_decrease: 5 },
    ])

    renderBanner()

    expect(await screen.findByText('過剰在庫の可能性がある商品が1件あります。')).toBeInTheDocument()
    expect(screen.queryByText(/在庫不足/)).not.toBeInTheDocument()
  })

  it('両方の取得に失敗しても何も表示せず、例外も投げない', async () => {
    vi.spyOn(opportunitiesApi, 'fetchOpportunities').mockRejectedValue(new Error('取得失敗1'))
    vi.spyOn(overstockApi, 'fetchOverstocks').mockRejectedValue(new Error('取得失敗2'))

    const { container } = renderBanner()

    await waitFor(() => {
      expect(opportunitiesApi.fetchOpportunities).toHaveBeenCalled()
    })
    expect(container).toBeEmptyDOMElement()
  })
})
