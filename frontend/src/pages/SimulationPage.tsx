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
import { stepToClockTime } from '../lib/clock'
import { conditionKey } from '../lib/conditionKey'
import { buildLearningCurveData } from '../lib/learningCurveData'
import { computeRevenue } from '../lib/revenue'
import { buildStockChartData } from '../lib/stockChartData'
import { chartAxisColors, useTheme } from '../lib/useTheme'
import type { DayType, Product, SimulationDetail, StepOut, Weather } from '../api/types'
import { discountLabel } from '../lib/discountLabel'
import MonitorBoard from '../components/MonitorBoard'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const STEP_INTERVAL_MS = 500
const COLORS = ['#d9480f', '#1971c2', '#2f9e44']
// 目標廃棄率のプリセットボタン（docs/spec.md §4①）。スライダーの値を直接書き換えるだけの補助UI
const TARGET_WASTE_RATE_PRESETS = [0, 0.03, 0.05, 0.1]

//: ズバリ引きの承認の遅れの選択肢（docs/spec.md §5.11。1ステップ18分）
const APPROVAL_DELAY_OPTIONS = [
  { steps: 0, label: 'すぐ承認' },
  { steps: 1, label: '18分後' },
  { steps: 2, label: '36分後（忙しい）' },
  { steps: 3, label: '54分後（1人で回している）' },
]

export default function SimulationPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [weather, setWeather] = useState<Weather>('晴れ')
  const [dayType, setDayType] = useState<DayType>('平日')
  const [hasEvent, setHasEvent] = useState(false)
  const [targetWasteRate, setTargetWasteRate] = useState(0.03)
  //: ズバリ引きをナイトマネージャーが何ステップ後に承認するか（docs/spec.md §5.11）
  const [approvalDelaySteps, setApprovalDelaySteps] = useState(0)

  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<SimulationDetail | null>(null)
  const [visibleStep, setVisibleStep] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 連続実行（docs/spec.md §4①「連続実行」・「学習曲線グラフ」）
  const [batchCount, setBatchCount] = useState(5)
  const [batchRunning, setBatchRunning] = useState(false)
  const [learningCurve, setLearningCurve] = useState<SimulationDetail[]>([])

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
    if (running || batchRunning) return // 二重開始防止（disabled属性の反映が間に合わない場合の保険）
    setError(null)
    setRunning(true)
    setDetail(null)
    setVisibleStep(0)
    // 直前の連続実行の学習曲線グラフが、条件を変えた単発実行後も残り続けないようにする
    // （「今表示されている条件・結果」と学習曲線グラフの中身が食い違って見えるのを防ぐ）
    setLearningCurve([])
    try {
      const result = await createSimulation({
        weather,
        day_type: dayType,
        has_event: hasEvent,
        target_waste_rate: targetWasteRate,
        approval_delay_steps: approvalDelaySteps,
      })
      setDetail(result)
      // 学習の継続（docs/spec.md §2・§5.2 step4）：今回の実行で事前分布が書き換わっているため、
      // 次に同条件で実行したときの開店直後フォールバック表示（priorDistributionFor）が
      // 古い値のままにならないよう取り直す。失敗しても結果表示自体は継続する
      fetchProducts()
        .then(setProducts)
        .catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : '実行に失敗しました')
      setRunning(false)
    }
  }

  async function handleBatchRun() {
    if (running || batchRunning) return
    setError(null)
    setBatchRunning(true)
    setLearningCurve([])
    try {
      const results: SimulationDetail[] = []
      // 学習の継続は前の回がDBにコミットされて初めて次の事前分布に反映されるため、
      // 直列で（前の回の完了を待ってから次を呼ぶ）実行する（docs/spec.md §4①）
      for (let i = 0; i < batchCount; i++) {
        const result = await createSimulation({
          weather,
          day_type: dayType,
          has_event: hasEvent,
          target_waste_rate: targetWasteRate,
          approval_delay_steps: approvalDelaySteps,
        })
        results.push(result)
      }
      setLearningCurve(results)
      // 最後の1回は通常の営業開始と同じアニメーションで再生する（既存のuseEffectに乗せる）
      setRunning(true)
      setDetail(results[results.length - 1])
      setVisibleStep(0)
      fetchProducts()
        .then(setProducts)
        .catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : '連続実行に失敗しました')
    } finally {
      setBatchRunning(false)
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
            <select
              value={weather}
              onChange={(e) => setWeather(e.target.value as Weather)}
              disabled={running || batchRunning}
            >
              <option value="晴れ">晴れ</option>
              <option value="曇り">曇り</option>
              <option value="雨">雨</option>
            </select>
          </label>
          <label>
            曜日
            <select
              value={dayType}
              onChange={(e) => setDayType(e.target.value as DayType)}
              disabled={running || batchRunning}
            >
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
              disabled={running || batchRunning}
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
              disabled={running || batchRunning}
            />
          </label>
          <label>
            ズバリ引きの承認（ナイトマネージャー）
            <select
              value={approvalDelaySteps}
              onChange={(e) => setApprovalDelaySteps(Number(e.target.value))}
              disabled={running || batchRunning}
            >
              {APPROVAL_DELAY_OPTIONS.map((o) => (
                <option key={o.steps} value={o.steps}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <span className="preset-buttons">
            {TARGET_WASTE_RATE_PRESETS.map((rate) => (
              <button
                key={rate}
                type="button"
                className="preset-btn"
                onClick={() => setTargetWasteRate(rate)}
                disabled={running || batchRunning}
              >
                {Math.round(rate * 100)}%
              </button>
            ))}
          </span>
          <button className="primary" onClick={handleStart} disabled={running || batchRunning}>
            {running ? '営業中…' : '営業開始'}
          </button>
        </div>
        <div className="form-row">
          <label>
            連続実行（同条件で学習を進める）
            <input
              type="number"
              min={1}
              max={10}
              value={batchCount}
              onChange={(e) => setBatchCount(Number(e.target.value))}
              disabled={running || batchRunning}
            />
          </label>
          <button
            onClick={handleBatchRun}
            disabled={
              running ||
              batchRunning ||
              !Number.isInteger(batchCount) ||
              batchCount < 1 ||
              batchCount > 10
            }
          >
            {batchRunning ? '連続実行中…' : '連続実行'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {detail && totalSteps > 0 && (
        <p className="clock-display">現在 {stepToClockTime(visibleStep, totalSteps)}</p>
      )}

      {detail && totalSteps > 0 && (
        <MonitorBoard
          clock={stepToClockTime(visibleStep, totalSteps)}
          items={products.map((p) => {
            const step = latestStepFor(p.id)
            return {
              productId: p.id,
              name: p.name,
              unitPrice: p.unit_price,
              appliedRate: step?.applied_rate ?? step?.recommended_rate ?? 0,
              remainingStock: step?.remaining_stock ?? p.initial_stock,
            }
          })}
        />
      )}

      <div className="product-grid">
        {products.map((p, i) => {
          const step = latestStepFor(p.id)
          const finalResult = detail?.finals.find((f) => f.product_id === p.id)
          const stockAdjustment = detail?.stock_adjustments.find((a) => a.product_id === p.id)
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
                  <div className="rate">
                    {discountLabel(step?.applied_rate ?? step?.recommended_rate ?? 0, p.unit_price)}
                  </div>
                  {step && (step.applied_rate ?? step.recommended_rate) < step.recommended_rate && (
                    <p className="pending-approval">
                      承認待ち：{discountLabel(step.recommended_rate, p.unit_price)}
                      （ナイトマネージャーが承認するとモニターに出ます）
                    </p>
                  )}
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
                  {p.unit_price != null && detail && (
                    <p>
                      推定売上: ¥
                      {Math.round(
                        computeRevenue(
                          detail.steps.filter((s) => s.product_id === p.id),
                          p.unit_price,
                        ),
                      ).toLocaleString()}
                    </p>
                  )}
                  {stockAdjustment && (
                    <p className="chart-caption">
                      在庫を自動調整：{stockAdjustment.delta > 0 ? '+' : ''}
                      {stockAdjustment.delta}個（次回の初期在庫 {stockAdjustment.new_initial_stock}個）
                    </p>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>

      {detail && <StockChart detail={detail} visibleStep={visibleStep} />}
      {learningCurve.length > 0 && <LearningCurveChart runs={learningCurve} />}
    </div>
  )
}

/** 商品ごとの残り在庫数の推移を折れ線で描く（docs/spec.md §4①）。
 * `/history` の値引き率推移グラフ（RateChart）と同じ描画方式で、visibleStepまでを描画する。
 * 商品名は`RateChart`と同じく`detail.finals`（実行時点のスナップショット）から解決する。
 * 実行中に別画面で商品が削除されても、他のカードの表示（`finalResult`）と名前がずれない */
function StockChart({ detail, visibleStep }: { detail: SimulationDetail; visibleStep: number }) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)
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
            scales: {
              x: { ticks: { color: axisColors.tick }, grid: { color: axisColors.grid } },
              y: {
                title: { display: true, text: '残り在庫数', color: axisColors.tick },
                beginAtZero: true,
                ticks: { color: axisColors.tick },
                grid: { color: axisColors.grid },
              },
            },
          }}
        />
      </div>
    </div>
  )
}

/** 連続実行の結果を学習曲線として折れ線で描く（docs/spec.md §4①「学習曲線グラフ」）。
 * 横軸=実行回、縦軸=実績廃棄率(%)。StockChartと同じく凡例は自前で描き、legend/tooltipは無効化する
 * （jsdomでのLine描画クラッシュを避けるため。SimulationPage.test.tsxのvi.mockコメント参照）。 */
function LearningCurveChart({ runs }: { runs: SimulationDetail[] }) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)
  const { labels, series } = buildLearningCurveData(runs)

  const datasets = series.map((s, i) => ({
    label: s.name,
    data: s.data,
    borderColor: COLORS[i % COLORS.length],
    backgroundColor: COLORS[i % COLORS.length],
    tension: 0.1,
  }))

  return (
    <div className="card">
      <h2>学習曲線（連続実行 {runs.length}回）</h2>
      <p className="chart-caption">
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
            scales: {
              x: { ticks: { color: axisColors.tick }, grid: { color: axisColors.grid } },
              y: {
                title: { display: true, text: '実績廃棄率(%)', color: axisColors.tick },
                beginAtZero: true,
                ticks: { color: axisColors.tick },
                grid: { color: axisColors.grid },
              },
            },
          }}
        />
      </div>
    </div>
  )
}
