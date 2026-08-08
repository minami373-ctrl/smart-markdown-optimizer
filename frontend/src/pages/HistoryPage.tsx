import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Fragment, useEffect, useState } from 'react'
import { Line } from 'react-chartjs-2'
import { fetchSimulation, fetchSimulations } from '../api/simulations'
import type { SimulationDetail, SimulationSummary } from '../api/types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const COLORS = ['#d9480f', '#1971c2', '#2f9e44']

export default function HistoryPage() {
  const [runs, setRuns] = useState<SimulationSummary[]>([])
  const [openId, setOpenId] = useState<number | null>(null)
  const [detail, setDetail] = useState<SimulationDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchSimulations()
      .then(setRuns)
      .catch((e) => setError(e.message))
  }, [])

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
            {runs.map((r) => (
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
      </div>
    </div>
  )
}

function RateChart({ detail }: { detail: SimulationDetail }) {
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
        scales: { y: { title: { display: true, text: '値引き率(%)' } } },
      }}
    />
  )
}
