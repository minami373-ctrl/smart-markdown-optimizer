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
import { CATEGORY_COLORS, buildCategoryStockChartData } from '../lib/stockChartData'
import { dayPhase } from '../lib/dayPhase'
import { storeAlert } from '../lib/storeAlert'
import { ACTUAL_SITUATIONS } from '../api/types'
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
  //: 長期休み（大学の休み・帰省の期間）の日か（docs/spec.md §5.13）
  const [isLongVacation, setIsLongVacation] = useState(false)
  //: 実際の状況（店は知らない。docs/spec.md §5.16）。入れ忘れの影響と知らせを試すため
  const [actualSituation, setActualSituation] = useState<string>('いつもどおり')
  //: 作る量の決め方（docs/spec.md §5.17）
  const [stockMode, setStockMode] = useState<string>('いつもの量')
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
        is_long_vacation: isLongVacation,
        actual_situation: actualSituation,
        stock_mode: stockMode,
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
          is_long_vacation: isLongVacation,
          actual_situation: actualSituation,
          stock_mode: stockMode,
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
    const key = conditionKey(
      detail.weather,
      detail.day_type,
      detail.has_event,
      detail.is_long_vacation ?? false,
    )
    const prior = product.prior_demand[key]
    return prior ? { alpha: prior.alpha, beta: prior.beta } : null
  }

  /** その日に作った量。営業が終わると在庫の自動調整（§5.7）で商品の初期在庫が書き換わるため、
   * 商品一覧の現在値ではなく、この回の最初のステップ（残り＋売れた数）から求める */
  function dayStockFor(product: Product): number {
    const first = detail?.steps.find((s) => s.product_id === product.id)
    if (first?.remaining_stock != null) return first.remaining_stock + first.quantity
    return product.initial_stock
  }

  const finished = detail !== null && visibleStep >= totalSteps && totalSteps > 0
  // 店全体の「いつもと違う」の知らせ（§5.16）。各商品の今のステップの知らせから求める
  const currentStoreAlert = detail ? storeAlert(products.map((p) => latestStepFor(p.id)?.alert)) : null

  return (
    <div>
      <div className="page-head">
        <h1>今日の売り場</h1>
        {detail && totalSteps > 0 && (
          <div className="clock">
            <span className="phase">{dayPhase(visibleStep, totalSteps)}</span>
            <p className="clock-display">現在 {stepToClockTime(visibleStep, totalSteps)}</p>
          </div>
        )}
      </div>

      <section className="panel conditions">
        <div className="field-group">
          <span className="group-label">その日の条件</span>
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
          <label className="check">
            <input
              type="checkbox"
              checked={hasEvent}
              onChange={(e) => setHasEvent(e.target.checked)}
              disabled={running || batchRunning}
            />
            イベント
          </label>
          <label
            className="check"
            title="大学の休み・帰省の期間はふだんと客数が違う。カレンダーを見て人が入れる"
          >
            <input
              type="checkbox"
              checked={isLongVacation}
              onChange={(e) => setIsLongVacation(e.target.checked)}
              disabled={running || batchRunning}
            />
            長期休み
          </label>
        </div>
        <div className="field-group">
          <span className="group-label">お店の決めごと</span>
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
          <label title="予測から決める＝その日の条件（天気・曜日・イベント・長期休み）の予測から、定価で1日に売れる見込みの量を作る">
            作る量
            <select
              value={stockMode}
              onChange={(e) => setStockMode(e.target.value)}
              disabled={running || batchRunning}
            >
              <option value="いつもの量">いつもの量</option>
              <option value="予測から決める">予測から決める</option>
            </select>
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
        </div>
        <div className="field-group actions">
          <button className="primary" onClick={handleStart} disabled={running || batchRunning}>
            {running ? '営業中…' : '営業開始'}
          </button>
        </div>
        <div className="field-group batch">
          <span className="group-label">シミュレーション用：実際の状況（店は知らない）</span>
          <label title="お客さんの本当の需要だけがこの状況で決まる。店の予測は上で入れた条件のまま">
            実際の状況
            <select
              value={actualSituation}
              onChange={(e) => setActualSituation(e.target.value)}
              disabled={running || batchRunning}
            >
              {ACTUAL_SITUATIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field-group batch">
          <span className="group-label">学習の様子を見る（同じ条件で何日分か続けて営業）</span>
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
      </section>

      {!detail && (
        <>
          <p className="empty">条件を設定して「営業開始」を押してください。</p>
          {products.length > 0 && (
            <MonitorBoard
              clock="開店前"
              items={products.map((p) => ({
                productId: p.id,
                name: p.name,
                unitPrice: p.unit_price,
                appliedRate: 0,
                remainingStock: p.initial_stock,
              }))}
            />
          )}
        </>
      )}

      {detail && totalSteps > 0 && currentStoreAlert && (
        <p className="store-alert" role="status">
          {currentStoreAlert}
        </p>
      )}

      {detail && totalSteps > 0 && !finished && (
        <div className="floor">
          <MonitorBoard
            clock={stepToClockTime(visibleStep, totalSteps)}
            items={products.map((p) => {
              const step = latestStepFor(p.id)
              return {
                productId: p.id,
                name: p.name,
                unitPrice: p.unit_price,
                appliedRate: step?.applied_rate ?? step?.recommended_rate ?? 0,
                // 店頭の在庫（16時の補充で増える。昼に売り切れたら補充まで「売り切れ」）
                remainingStock: step?.shelf_stock ?? step?.remaining_stock ?? p.initial_stock,
              }
            })}
          />

          <section className="panel manager">
            <h2>ナイトマネージャーの画面</h2>
            <table className="list">
              <thead>
                <tr>
                  <th>商品</th>
                  <th className="num">店頭 / 1日の量</th>
                  <th>売り場の表示</th>
                  <th>確認すること</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => {
                  const step = latestStepFor(p.id)
                  const applied = step?.applied_rate ?? step?.recommended_rate ?? 0
                  const pending = step != null && applied < step.recommended_rate
                  return (
                    <tr key={p.id} className={pending ? 'row-pending' : undefined}>
                      <td>{p.name}</td>
                      <td className="num">
                        {step?.shelf_stock ?? step?.remaining_stock ?? dayStockFor(p)}
                        <span className="sub"> / {dayStockFor(p)}</span>
                      </td>
                      <td>{applied > 0 ? discountLabel(applied, p.unit_price) : '定価'}</td>
                      <td>
                        {pending && step && (
                          <span className="pending-approval">
                            承認待ち：{discountLabel(step.recommended_rate, p.unit_price)}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </section>
        </div>
      )}

      {finished && detail && (
        <section className="panel">
          <h2>閉店後の結果</h2>
          <table className="list">
            <thead>
              <tr>
                <th>商品</th>
                <th className="num">廃棄率</th>
                <th>目標</th>
                <th className="num">推定売上</th>
                <th>明日の在庫</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => {
                const finalResult = detail.finals.find((f) => f.product_id === p.id)
                if (!finalResult) return null
                const stockAdjustment = detail.stock_adjustments.find(
                  (a) => a.product_id === p.id,
                )
                return (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td className="num">{Math.round(finalResult.final_waste_rate * 100)}%</td>
                    <td className={finalResult.achieved ? 'ok' : 'warn'}>
                      {finalResult.achieved ? '目標達成' : '目標未達'}
                    </td>
                    <td className="num">
                      {p.unit_price != null &&
                        `¥${Math.round(
                          computeRevenue(
                            detail.steps.filter((s) => s.product_id === p.id),
                            p.unit_price,
                          ),
                        ).toLocaleString()}`}
                    </td>
                    <td className="sub">
                      {stockAdjustment &&
                        `在庫を自動調整：${stockAdjustment.delta > 0 ? '+' : ''}${stockAdjustment.delta}個（次回の初期在庫 ${stockAdjustment.new_initial_stock}個）`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}

      {detail && <StockChart detail={detail} products={products} visibleStep={visibleStep} />}
      {learningCurve.length > 0 && <LearningCurveChart runs={learningCurve} />}

      {detail && (
        <details className="panel model">
          <summary>予測のしくみを見る（ベイズ更新）</summary>
          <p className="sub">
            商品ごとの「1回あたりに売れる数」の予測です。売れるたびに更新され、データが増えるほど山が高く鋭くなります（確信度が上がる）。
          </p>
          <div className="model-grid">
            {products.map((p, i) => {
              const step = latestStepFor(p.id)
              const distribution =
                step?.posterior_alpha != null && step?.posterior_beta != null
                  ? { alpha: step.posterior_alpha, beta: step.posterior_beta }
                  : priorDistributionFor(p)
              return (
                <div key={p.id} className="model-item">
                  <span>{p.name}</span>
                  {distribution && (
                    <DistributionChart
                      alpha={distribution.alpha}
                      beta={distribution.beta}
                      color={COLORS[i % COLORS.length]}
                    />
                  )}
                </div>
              )
            })}
          </div>
        </details>
      )}
    </div>
  )
}

/** 在庫の推移を、商品の種類ごとの合計で折れ線に描く（docs/spec.md §4①。2026-11-26に12本→3本へ）。
 * 「弁当・丼は半額でほぼ売れるが、揚げ物の単品は残る」という売り場の観察が線の形で見えるようにする。
 * 凡例は自前で描き、legend/tooltipは無効化する（jsdomでのLine描画クラッシュを避けるため。
 * SimulationPage.test.tsxのvi.mockコメント参照） */
function StockChart({
  detail,
  products,
  visibleStep,
}: {
  detail: SimulationDetail
  products: Product[]
  visibleStep: number
}) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)
  const { labels, series } = buildCategoryStockChartData(detail.steps, products, visibleStep)

  const datasets = series.map((s) => ({
    label: s.category,
    data: s.data,
    borderColor: CATEGORY_COLORS[s.category] ?? '#666',
    backgroundColor: CATEGORY_COLORS[s.category] ?? '#666',
    tension: 0.1,
    pointRadius: 0,
    borderWidth: 2,
  }))

  return (
    <section className="panel">
      <h2>在庫推移</h2>
      <p className="chart-caption">
        種類ごとの店頭の在庫の合計。16時の補充で増え、18時以降の値引きで減っていきます。
        {series.map((s) => (
          <span key={s.category} style={{ color: CATEGORY_COLORS[s.category], marginLeft: 12 }}>
            ━ {s.category}
          </span>
        ))}
      </p>
      <div className="stock-chart">
        <Line
          data={{ labels: labels.map((step) => stepToClockTime(step)), datasets }}
          options={{
            animation: false,
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            scales: {
              x: {
                ticks: { color: axisColors.tick, maxTicksLimit: 13 },
                grid: { color: axisColors.grid },
              },
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
    </section>
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
    <section className="panel">
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
    </section>
  )
}
