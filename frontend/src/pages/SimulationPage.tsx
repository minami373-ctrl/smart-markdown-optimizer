import { useEffect, useMemo, useRef, useState } from 'react'
import DistributionChart from '../components/DistributionChart'
import { fetchProducts } from '../api/products'
import { createSimulation } from '../api/simulations'
import { conditionKey } from '../lib/conditionKey'
import type { DayType, Product, SimulationDetail, StepOut, Weather } from '../api/types'

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
    </div>
  )
}
