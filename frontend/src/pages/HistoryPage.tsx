import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Line } from 'react-chartjs-2'
import { fetchSimulation, fetchSimulations } from '../api/simulations'
import { buildHistoryCsv } from '../lib/historyCsv'
import { DEFAULT_HISTORY_FILTERS, filterRuns } from '../lib/historyFilter'
import type { HistoryFilters } from '../lib/historyFilter'
import { chartAxisColors, useTheme } from '../lib/useTheme'
import type { SimulationDetail, SimulationSummary } from '../api/types'

const CSV_FILENAME = 'simulation_history.csv'
// ExcelでUTF-8 CSVを開いたときに日本語が文字化けしないようにするBOM（U+FEFF）。
// ソースコード中に不可視文字として直接埋め込むとエディタ・ビルドツールによって
// 気づかれずに消えることがあるため、String.fromCharCodeで明示的に組み立てる
const UTF8_BOM = String.fromCharCode(0xfeff)

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const COLORS = ['#d9480f', '#1971c2', '#2f9e44']

export default function HistoryPage() {
  const [runs, setRuns] = useState<SimulationSummary[]>([])
  const [openId, setOpenId] = useState<number | null>(null)
  const [detail, setDetail] = useState<SimulationDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<HistoryFilters>(DEFAULT_HISTORY_FILTERS)

  useEffect(() => {
    fetchSimulations()
      .then(setRuns)
      .catch((e) => setError(e.message))
  }, [])

  // 条件フィルタ（docs/spec.md §4③「条件フィルタ」）。新しいAPIは追加せず、
  // 取得済みの一覧をフロントエンドだけで絞り込む
  const filteredRuns = useMemo(() => filterRuns(runs, filters), [runs, filters])

  async function toggle(id: number) {
    if (openId === id) {
      setOpenId(null)
      setDetail(null)
      return
    }
    setOpenId(id)
    try {
      const d = await fetchSimulation(id)
      setDetail(d)
    } catch (e) {
      setError(e instanceof Error ? e.message : '取得に失敗しました')
    }
  }

  function handleDownloadCsv() {
    // フィルタ前の全件ではなく、今画面に見えている（絞り込み後の）行だけを書き出す
    const csv = buildHistoryCsv(filteredRuns)
    const blob = new Blob([UTF8_BOM + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = CSV_FILENAME
    a.click()
    URL.revokeObjectURL(url)
  }

  if (error) return <p className="error">{error}</p>

  if (runs.length === 0) {
    return (
      <div>
        <h1>履歴</h1>
        <p>まだシミュレーションを実行していません。</p>
      </div>
    )
  }

  return (
    <div>
      <h1>履歴</h1>
      <div className="card">
        <div className="form-row">
          <label>
            天気
            <select
              value={filters.weather}
              onChange={(e) =>
                setFilters({ ...filters, weather: e.target.value as HistoryFilters['weather'] })
              }
            >
              <option value="すべて">すべて</option>
              <option value="晴れ">晴れ</option>
              <option value="曇り">曇り</option>
              <option value="雨">雨</option>
            </select>
          </label>
          <label>
            曜日
            <select
              value={filters.dayType}
              onChange={(e) =>
                setFilters({ ...filters, dayType: e.target.value as HistoryFilters['dayType'] })
              }
            >
              <option value="すべて">すべて</option>
              <option value="平日">平日</option>
              <option value="休日">休日</option>
            </select>
          </label>
          <label>
            イベント
            <select
              value={filters.hasEvent}
              onChange={(e) =>
                setFilters({ ...filters, hasEvent: e.target.value as HistoryFilters['hasEvent'] })
              }
            >
              <option value="すべて">すべて</option>
              <option value="あり">あり</option>
              <option value="なし">なし</option>
            </select>
          </label>
          <button onClick={handleDownloadCsv} disabled={filteredRuns.length === 0}>
            CSVダウンロード
          </button>
        </div>
        {filteredRuns.length === 0 ? (
          <p>条件に一致する実行履歴がありません。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>日時</th>
                <th>条件</th>
                <th>目標廃棄率</th>
                <th>結果</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.map((r) => (
                <Fragment key={r.id}>
                  <tr className="history-row" onClick={() => toggle(r.id)}>
                    <td>{new Date(r.started_at).toLocaleString('ja-JP')}</td>
                    <td>
                      {r.weather} / {r.day_type} / {r.has_event ? 'イベントあり' : 'イベントなし'}
                    </td>
                    <td>{Math.round(r.target_waste_rate * 100)}%</td>
                    <td>
                      {r.finals.length === 0
                        ? '-'
                        : r.finals.every((f) => f.achieved)
                          ? '全商品達成'
                          : `${r.finals.filter((f) => !f.achieved).length}商品未達`}
                    </td>
                  </tr>
                  {openId === r.id && detail && detail.id === r.id && (
                    <tr>
                      <td colSpan={4}>
                        <RateChart detail={detail} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function RateChart({ detail }: { detail: SimulationDetail }) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)
  const productIds = [...new Set(detail.steps.map((s) => s.product_id))]
  const totalSteps = detail.steps.length > 0 ? Math.max(...detail.steps.map((s) => s.step)) + 1 : 0
  const labels = Array.from({ length: totalSteps }, (_, i) => i)

  const datasets = productIds.map((pid, i) => {
    const name = detail.finals.find((f) => f.product_id === pid)?.product_name ?? `商品${pid}`
    const byStep = new Map(detail.steps.filter((s) => s.product_id === pid).map((s) => [s.step, s.recommended_rate]))
    return {
      label: name,
      data: labels.map((step) => (byStep.get(step) ?? 0) * 100),
      borderColor: COLORS[i % COLORS.length],
      backgroundColor: COLORS[i % COLORS.length],
      tension: 0.1,
    }
  })

  return (
    <Line
      data={{ labels, datasets }}
      options={{
        plugins: { legend: { labels: { color: axisColors.tick } } },
        scales: {
          x: { ticks: { color: axisColors.tick }, grid: { color: axisColors.grid } },
          y: {
            title: { display: true, text: '値引き率(%)', color: axisColors.tick },
            ticks: { color: axisColors.tick },
            grid: { color: axisColors.grid },
          },
        },
      }}
    />
  )
}
