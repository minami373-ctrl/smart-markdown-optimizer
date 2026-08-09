import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Line } from 'react-chartjs-2'
import DistributionChart from '../components/DistributionChart'
import { fetchProducts } from '../api/products'
import { createSimulation } from '../api/simulations'
import { conditionKey } from '../lib/conditionKey'
import { buildStockChartData } from '../lib/stockChartData'
import type { DayType, Product, SimulationDetail, StepOut, Weather } from '../api/types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const STEP_INTERVAL_MS = 500
const COLORS = ['#d9480f', '#1971c2', '#2f9e44']

export default function SimulationPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [weather, setWeather] = useState<Weather>('晴れ')
  const [dayType, setDayType] = useState<DayType>('平日')
  const [hasEvent, setHasEvent] = useState(false)
  const [targetWasteRate, setTargetWasteRate] = useState(0.03)

  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<SimulationDetail | null>(null)
  const [visibleStep, setVisibleStep] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchProducts()
      .then(setProducts)
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  const totalSteps = useMemo(() => {
    if (!detail || detail.steps.length === 0) return 0
    return Math.max(...detail.steps.map((s) => s.step)) + 1
  }, [detail])

  async function handleStart() {
    if (running) return // 二重開始防止（disabled属性の反映が間に合わない場合の保険）
    setError(null)
    setRunning(true)
    setDetail(null)
    setVisibleStep(0)
    try {
      const result = await createSimulation({
        weather,
        day_type: dayType,
        has_event: hasEvent,
        target_waste_rate: targetWasteRate,
      })
      setDetail(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : '実行に失敗しました')
      setRunning(false)
    }
  }

  useEffect(() => {
    if (!detail) return
    if (totalSteps === 0) {
      // 対象商品が全て在庫0等でstepsが空のとき、「営業中…」のまま固まらないようにする
      setRunning(false)
      return
    }
    let current = 0
    setVisibleStep(0)
    timerRef.current = setInterval(() => {
      current += 1
      setVisibleStep(current)
      if (current >= totalSteps) {
        if (timerRef.current) clearInterval(timerRef.current)
        setRunning(false)
      }
    }, STEP_INTERVAL_MS)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [detail, totalSteps])

  function latestStepFor(productId: number): StepOut | undefined {
    if (!detail) return undefined
    let latest: StepOut | undefined
    for (const s of detail.steps) {
      if (s.product_id !== productId) continue
      if (s.step >= visibleStep) break
      latest = s
    }
    return latest
  }

  /** まだ1ステップも進んでいない開店直後は、事前分布（山が低く広い状態）を返す。
   * docs/spec.md §4①「開店直後は山が低く横に広い…」を、最初のティックを待たずに見せるため */
  function priorDistributionFor(product: Product): { alpha: number; beta: number } | null {
    if (!detail) return null
    const key = conditionKey(detail.weather, detail.day_type, detail.has_event)
    const prior = product.prior_demand[key]
    return prior ? { alpha: prior.alpha, beta: prior.beta } : null
  }

  const finished = detail !== null && visibleStep >= totalSteps && totalSteps > 0

  return (
    <div>
      <h1>営業シミュレーション</h1>

      <div className="card">
        <div className="form-row">
          <label>
            天気
            <select value={weather} onChange={(e) => setWeather(e.target.value as Weather)} disabled={running}>
              <option value="晴れ">晴れ</option>
              <option value="曇り">曇り</option>
              <option value="雨">雨</option>
            </select>
          </label>
          <label>
            曜日
            <select value={dayType} onChange={(e) => setDayType(e.target.value as DayType)} disabled={running}>
              <option value="平日">平日</option>
              <option value="休日">休日</option>
            </select>
          </label>
          <label>
            イベント
            <input
              type="checkbox"
              checked={hasEvent}
              onChange={(e) => setHasEvent(e.target.checked)}
              disabled={running}
            />
          </label>
          <label>
            目標廃棄率（{Math.round(targetWasteRate * 100)}%）
            <input
              type="range"
              min={0}
              max={0.1}
              step={0.01}
              value={targetWasteRate}
              onChange={(e) => setTargetWasteRate(Number(e.target.value))}
              disabled={running}
            />
          </label>
          <button className="primary" onClick={handleStart} disabled={running}>
            {running ? '営業中…' : '営業開始'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      <div className="product-grid">
        {products.map((p, i) => {
          const step = latestStepFor(p.id)
          const finalResult = detail?.finals.find((f) => f.product_id === p.id)
          const distribution =
            step?.posterior_alpha != null && step?.posterior_beta != null
              ? { alpha: step.posterior_alpha, beta: step.posterior_beta }
              : priorDistributionFor(p) // 最初のティック前は事前分布（開店直後の山）を見せる
          return (
            <div className="product-card" key={p.id}>
              <h3>{p.name}</h3>
              {!detail && <p>条件を設定して「営業開始」を押してください。</p>}
              {detail && !finished && (
                <>
                  <div className="rate">{Math.round((step?.recommended_rate ?? 0) * 100)}%引き</div>
                  <p>
                    残り {step?.remaining_stock ?? p.initial_stock} / {p.initial_stock}
                  </p>
                  <p>期待残数: {step ? Math.round((step.posterior_mean ?? 0) * 10) / 10 : '-'}</p>
                  {distribution && (
                    <>
                      <DistributionChart
                        alpha={distribution.alpha}
                        beta={distribution.beta}
                        color={COLORS[i % COLORS.length]}
                      />
                      <p className="chart-caption">需要率の確信度（データが増えるほど山が尖る）</p>
                    </>
                  )}
                </>
              )}
              {finished && finalResult && (
                <>
                  <p>実績廃棄率: {Math.round(finalResult.final_waste_rate * 100)}%</p>
                  <span className={`tag ${finalResult.achieved ? 'ok' : 'warn'}`}>
                    {finalResult.achieved ? '目標達成' : '目標未達'}
                  </span>
                </>
              )}
            </div>
          )
        })}
      </div>

      {detail && <StockChart detail={detail} visibleStep={visibleStep} />}
    </div>
  )
}

/** 商品ごとの残り在庫数の推移を折れ線で描く（docs/spec.md §4①）。
 * `/history` の値引き率推移グラフ（RateChart）と同じ描画方式で、visibleStepまでを描画する。
 * 商品名は`RateChart`と同じく`detail.finals`（実行時点のスナップショット）から解決する。
 * 実行中に別画面で商品が削除されても、他のカードの表示（`finalResult`）と名前がずれない */
function StockChart({ detail, visibleStep }: { detail: SimulationDetail; visibleStep: number }) {
  const nameSource = detail.finals.map((f) => ({ id: f.product_id, name: f.product_name }))
  const { labels, series } = buildStockChartData(detail.steps, nameSource, visibleStep)

  const datasets = series.map((s, i) => ({
    label: s.name,
    data: s.data,
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length],
    tension: 0.1,
  }))

  return (
    <div className="card">
      <h2>在庫推移</h2>
      <p className="chart-caption">
        {/* responsive:trueのLegendプラグインはjsdomのcanvas未実装環境でリサイズ監視まわりの
            例外を誘発する（SimulationPage.test.tsxのvi.mockコメント参照）ため使わず、
            DistributionChartと同じくlegend/tooltipを無効化し、色の対応表を自前で出す */}
        {series.map((s, i) => (
          <span key={s.productId} style={{ color: COLORS[i % COLORS.length], marginRight: 12 }}>
            ● {s.name}
          </span>
        ))}
      </p>
      <div className="stock-chart">
        <Line
          data={{ labels, datasets }}
          options={{
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: { y: { title: { display: true, text: '残り在庫数' }, beginAtZero: true } },
          }}
        />
      </div>
    </div>
  )
}
