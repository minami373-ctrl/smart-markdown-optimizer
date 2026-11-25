import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { useState } from 'react'
import { Line } from 'react-chartjs-2'
import { compareSchedules } from '../api/comparison'
import { stepToClockTime } from '../lib/clock'
import { computeRevenue } from '../lib/revenue'
import { chartAxisColors, useTheme } from '../lib/useTheme'
import type { ComparisonProduct, ComparisonResult, DayType, Weather } from '../api/types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const FIXED_COLOR = '#9aa5a1' // グレー：固定スケジュール（学業・完了済みと同じ「動きが遅い」トーン）
const DYNAMIC_COLOR = '#d9480f' // オレンジ：動的値引き（他画面のCOLORS[0]と揃える）

function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

/** 廃棄率の改善幅を表示するタグ。動的値引きの方が廃棄率が低ければ「改善」を強調する。 */
function WasteRateComparison({ product }: { product: ComparisonProduct }) {
  const improvement = product.fixed_final_waste_rate - product.dynamic_final_waste_rate
  return (
    <div className="form-row">
      <span>固定スケジュール：廃棄率 {formatPercent(product.fixed_final_waste_rate)}</span>
      <span>動的値引き：廃棄率 {formatPercent(product.dynamic_final_waste_rate)}</span>
      {improvement > 0.001 && (
        <span className="tag ok">廃棄率 {formatPercent(improvement)} 改善</span>
      )}
      {improvement < -0.001 && (
        <span className="tag warn">廃棄率 {formatPercent(-improvement)} 悪化</span>
      )}
    </div>
  )
}

function RevenueComparison({ product }: { product: ComparisonProduct }) {
  if (product.unit_price == null) return null
  const fixedRevenue = computeRevenue(product.fixed_steps, product.unit_price)
  const dynamicRevenue = computeRevenue(product.dynamic_steps, product.unit_price)
  const diff = dynamicRevenue - fixedRevenue
  return (
    <div className="form-row">
      <span>固定スケジュール：推定売上 ¥{Math.round(fixedRevenue).toLocaleString()}</span>
      <span>動的値引き：推定売上 ¥{Math.round(dynamicRevenue).toLocaleString()}</span>
      {diff > 0.5 && <span className="tag ok">¥{Math.round(diff).toLocaleString()} 増収</span>}
      {diff < -0.5 && <span className="tag warn">¥{Math.round(-diff).toLocaleString()} 減収</span>}
    </div>
  )
}

/** 値引き率の推移を両方式で重ねた折れ線グラフ。固定スケジュールは19時・20時半でしか
 * 変化しない階段状、動的値引きはもっと早く反応しうる、という違いを見せる（docs/spec.md §4⑥）。 */
function DiscountRateChart({ product }: { product: ComparisonProduct }) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)
  const labels = product.fixed_steps.map((s) => s.step)

  return (
    <div className="stock-chart">
      <Line
        data={{
          labels,
          datasets: [
            {
              label: '固定スケジュール',
              data: product.fixed_steps.map((s) => s.recommended_rate * 100),
              borderColor: FIXED_COLOR,
              backgroundColor: FIXED_COLOR,
              stepped: true,
              tension: 0,
            },
            {
              label: '動的値引き',
              data: product.dynamic_steps.map((s) => s.recommended_rate * 100),
              borderColor: DYNAMIC_COLOR,
              backgroundColor: DYNAMIC_COLOR,
              stepped: true,
              tension: 0,
            },
          ],
        }}
        options={{
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: {
            x: { ticks: { color: axisColors.tick }, grid: { color: axisColors.grid } },
            y: {
              title: { display: true, text: '値引き率(%)', color: axisColors.tick },
              beginAtZero: true,
              max: 80,
              ticks: { color: axisColors.tick },
              grid: { color: axisColors.grid },
            },
          },
        }}
      />
    </div>
  )
}

function ProductComparisonCard({ product }: { product: ComparisonProduct }) {
  return (
    <div className="card">
      <h2>{product.product_name}</h2>
      <p className="chart-caption">
        <span style={{ color: FIXED_COLOR }}>● 固定スケジュール</span>{' '}
        <span style={{ color: DYNAMIC_COLOR }}>● 動的値引き</span>
      </p>
      <DiscountRateChart product={product} />
      <WasteRateComparison product={product} />
      <RevenueComparison product={product} />
    </div>
  )
}

export default function ComparisonPage() {
  const [weather, setWeather] = useState<Weather>('晴れ')
  const [dayType, setDayType] = useState<DayType>('平日')
  const [hasEvent, setHasEvent] = useState(false)
  const [isLongVacation, setIsLongVacation] = useState(false)
  const [targetWasteRate, setTargetWasteRate] = useState(0.03)
  //: 「お客さんが待つ」効果（docs/spec.md §5.12。売り場での観察にもとづく仮定なので切り替えられる）
  const [customerAnticipation, setCustomerAnticipation] = useState(false)

  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ComparisonResult | null>(null)

  async function handleCompare() {
    if (running) return
    setError(null)
    setRunning(true)
    try {
      const res = await compareSchedules({
        weather,
        day_type: dayType,
        has_event: hasEvent,
        is_long_vacation: isLongVacation,
        target_waste_rate: targetWasteRate,
        customer_anticipation: customerAnticipation,
      })
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '比較に失敗しました')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div>
      <h1>固定時刻との比較</h1>
      <p>
        値引きのタイミングが「{stepToClockTime(result?.fixed_schedule_30_step ?? 30)}
        ＝3割引・{stepToClockTime(result?.fixed_schedule_50_step ?? 35)}
        ＝半額・21時過ぎ＝ズバリ引き」のように固定化された従来のやり方と、今の動的値引きを、同じ条件・
        同じ乱数（＝同じ客の来店パターン）で比較します。DBには保存されません。
      </p>

      <div className="card">
        <div className="form-row">
          <label>
            天気
            <select
              value={weather}
              onChange={(e) => setWeather(e.target.value as Weather)}
              disabled={running}
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
              disabled={running}
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
              disabled={running}
            />
          </label>
          <label>
            長期休み
            <input
              type="checkbox"
              checked={isLongVacation}
              onChange={(e) => setIsLongVacation(e.target.checked)}
              disabled={running}
            />
          </label>
          <label title="値引きの時刻が毎日同じだと、お客さんが覚えて待つ（18時台は買い控え、30%引きの間も半額を待つ）。売り場での観察にもとづく仮定">
            お客さんが値引きの時刻を覚えて待つ（仮定・固定スケジュール側のみ）
            <input
              type="checkbox"
              checked={customerAnticipation}
              onChange={(e) => setCustomerAnticipation(e.target.checked)}
              disabled={running}
            />
          </label>
          <label>
            目標廃棄率（動的値引きのみ使用。{Math.round(targetWasteRate * 100)}%）
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
          <button className="primary" onClick={handleCompare} disabled={running}>
            {running ? '比較中…' : '比較する'}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      {result?.products.map((p) => <ProductComparisonCard key={p.product_id} product={p} />)}
    </div>
  )
}
