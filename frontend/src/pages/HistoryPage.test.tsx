import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import HistoryPage from './HistoryPage'
import * as simulationsApi from '../api/simulations'
import type { SimulationSummary } from '../api/types'

// jsdomはcanvasを実装していない（SimulationPage.test.tsxと同じ理由。行を展開したときの
// RateChartの描画に使うLineをスタブに差し替える。CSVダウンロード機能のテストでは
// 展開操作自体は行わないため実質未使用だが、念のため他テストと同じ方針にそろえる）
vi.mock('react-chartjs-2', () => ({
  Line: () => null,
}))

const RUN: SimulationSummary = {
  id: 1,
  weather: '晴れ',
  day_type: '平日',
  has_event: false,
  target_waste_rate: 0.03,
  status: 'finished',
  started_at: '2026-08-10T12:00:00',
  finished_at: '2026-08-10T12:01:00',
  finals: [{ product_id: 1, product_name: '唐揚げ', final_waste_rate: 0.05, achieved: true }],
  stock_adjustments: [],
}

const RAINY_RUN: SimulationSummary = {
  id: 2,
  weather: '雨',
  day_type: '休日',
  has_event: true,
  target_waste_rate: 0.05,
  status: 'finished',
  started_at: '2026-08-09T18:00:00',
  finished_at: '2026-08-09T18:01:00',
  finals: [{ product_id: 2, product_name: 'おでん', final_waste_rate: 0.1, achieved: false }],
  stock_adjustments: [],
}

describe('HistoryPage', () => {
  let createObjectURLSpy: ReturnType<typeof vi.fn>
  let revokeObjectURLSpy: ReturnType<typeof vi.fn>
  let clickSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    createObjectURLSpy = vi.fn(() => 'blob:mock-url')
    revokeObjectURLSpy = vi.fn()
    // jsdomはURL.createObjectURLを実装していないためモックする
    URL.createObjectURL = createObjectURLSpy as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeObjectURLSpy as unknown as typeof URL.revokeObjectURL
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('実行履歴が無ければCSVダウンロードボタンごと表示しない', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([])

    render(<HistoryPage />)

    expect(await screen.findByText('まだシミュレーションを実行していません。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'CSVダウンロード' })).not.toBeInTheDocument()
  })

  it('CSVダウンロードを押すと、Blobを作ってダウンロード用リンクをクリックする', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    await user.click(screen.getByRole('button', { name: 'CSVダウンロード' }))

    await waitFor(() => {
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    })
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob
    expect(blob.type).toBe('text/csv;charset=utf-8;')
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url')
  })

  it('CSVの中身に実行履歴の内容（商品名・実績廃棄率）が含まれる', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    await user.click(screen.getByRole('button', { name: 'CSVダウンロード' }))

    await waitFor(() => {
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    })
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob

    // 文字化け対策のBOM（UTF-8で EF BB BF）が生バイト列の先頭に付いている。
    // Blob.text()はWHATWGのUTF-8デコード仕様上、先頭のBOMを取り除いてしまうため
    // （ブラウザ・Node双方の仕様どおりの挙動でありアプリの不具合ではない）、
    // ここでは生バイトを直接見る
    const bytes = new Uint8Array(await blob.arrayBuffer())
    expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf])

    const text = await blob.text()
    expect(text).toContain('唐揚げ')
    expect(text).toContain('達成')
  })

  it('天気フィルタで絞り込むと、該当する回だけ一覧に表示される', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN, RAINY_RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    // 絞り込み前は両方の回が見えている（日時セルで存在確認）
    expect(screen.getByText('2026/8/10 12:00:00')).toBeInTheDocument()
    expect(screen.getByText('2026/8/9 18:00:00')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('天気'), '雨')

    expect(screen.queryByText('2026/8/10 12:00:00')).not.toBeInTheDocument()
    expect(screen.getByText('2026/8/9 18:00:00')).toBeInTheDocument()
  })

  it('複数条件はAND：天気と曜日を両方指定すると両方満たす回だけ残る', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN, RAINY_RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    await user.selectOptions(screen.getByLabelText('天気'), '雨')
    await user.selectOptions(screen.getByLabelText('曜日'), '平日') // RAINY_RUNは休日なので一致しない

    expect(screen.queryByText('2026/8/9 18:00:00')).not.toBeInTheDocument()
    expect(screen.queryByText('2026/8/10 12:00:00')).not.toBeInTheDocument()
  })

  it('フィルタで0件になると案内文を表示し、CSVダウンロードボタンを無効化する', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    await user.selectOptions(screen.getByLabelText('天気'), '雨') // RUNは晴れなので一致しない

    expect(await screen.findByText('条件に一致する実行履歴がありません。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'CSVダウンロード' })).toBeDisabled()
  })

  it('フィルタ適用中にCSVダウンロードすると、絞り込み後の内容だけが含まれる', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockResolvedValue([RUN, RAINY_RUN])

    const user = userEvent.setup()
    render(<HistoryPage />)
    await screen.findByRole('button', { name: 'CSVダウンロード' })

    await user.selectOptions(screen.getByLabelText('天気'), '雨')
    await user.click(screen.getByRole('button', { name: 'CSVダウンロード' }))

    await waitFor(() => {
      expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    })
    const blob = createObjectURLSpy.mock.calls[0][0] as Blob
    const text = await blob.text()
    expect(text).toContain('おでん')
    expect(text).not.toContain('唐揚げ')
  })

  it('取得に失敗したらエラーメッセージを表示する', async () => {
    vi.spyOn(simulationsApi, 'fetchSimulations').mockRejectedValue(new Error('取得失敗'))

    render(<HistoryPage />)

    expect(await screen.findByText('取得失敗')).toBeInTheDocument()
  })
})
