import { useEffect, useState } from 'react'
import { fetchDiscountTiming } from '../api/discountTiming'
import { stepToClockTime } from '../lib/clock'
import { buildTimingGrid, timingIntensity, type TimingCell } from '../lib/timingGrid'
import { useTheme } from '../lib/useTheme'
import type { ConditionTiming } from '../api/types'

// --warnのRGB値（index.cssのCSS変数と同じ値をJS側でも持つ。Chart.jsの軸色と同じ理由で
// テーマごとに手動で切り替える。lib/useTheme.tsのchartAxisColorsと同じ方針）
const WARN_RGB = { light: '178, 58, 47', dark: '255, 138, 117' }

function conditionLabel(cell: TimingCell): string {
  return `${cell.weather}・${cell.dayType}・イベント${cell.hasEvent ? 'あり' : 'なし'}`
}

function TimingHeatmapCell({
  cell,
  minStep,
  maxStep,
  warnRgb,
}: {
  cell: TimingCell
  minStep: number
  maxStep: number
  warnRgb: string
}) {
  const { data } = cell

  if (data === null) {
    return (
      <td className="timing-cell timing-cell-empty">
        <div className="timing-cell-label">{conditionLabel(cell)}</div>
        <div className="timing-cell-value">データなし</div>
      </td>
    )
  }

  if (data.avg_first_discount_step === null) {
    return (
      <td className="timing-cell">
        <div className="timing-cell-label">{conditionLabel(cell)}</div>
        <div className="timing-cell-value">値引きなし</div>
        <div className="timing-cell-sub">発生 0/{data.sample_count}回</div>
      </td>
    )
  }

  const intensity = timingIntensity(data.avg_first_discount_step, minStep, maxStep)
  // 強度0.1〜0.8の範囲に収め、データがあるマスが背景色ゼロ（見えない）にならないようにする
  const alpha = 0.1 + intensity * 0.7

  return (
    <td
      className="timing-cell"
      style={{ backgroundColor: `rgba(${warnRgb}, ${alpha})` }}
    >
      <div className="timing-cell-label">{conditionLabel(cell)}</div>
      <div className="timing-cell-value">{stepToClockTime(data.avg_first_discount_step)}ごろ</div>
      <div className="timing-cell-sub">
        発生 {data.discounted_count}/{data.sample_count}回
      </div>
    </td>
  )
}

export default function TimingPage() {
  const theme = useTheme()
  const [conditions, setConditions] = useState<ConditionTiming[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDiscountTiming()
      .then(setConditions)
      .catch((e) => setError(e instanceof Error ? e.message : '取得に失敗しました'))
  }, [])

  if (error) {
    return (
      <div>
        <h1>値引きタイミングの傾向分析</h1>
        <p className="error">{error}</p>
      </div>
    )
  }

  const grid = buildTimingGrid(conditions ?? [])
  const knownSteps = (conditions ?? [])
    .map((c) => c.avg_first_discount_step)
    .filter((s): s is number => s !== null)
  const minStep = knownSteps.length > 0 ? Math.min(...knownSteps) : 0
  const maxStep = knownSteps.length > 0 ? Math.max(...knownSteps) : 40
  const warnRgb = theme === 'dark' ? WARN_RGB.dark : WARN_RGB.light

  return (
    <div>
      <h1>値引きタイミングの傾向分析</h1>
      <p>
        過去のシミュレーション履歴から、天気・曜日・イベント有無の条件ごとに、値引きが平均
        何時ごろから必要になっているかを集計します。色が濃いほど値引きが早く必要になりがちな
        条件です。「雨の日は値引きが早まる」という傾向が、履歴が増えるほどはっきり見えてきます。
      </p>
      {conditions !== null && conditions.length === 0 && (
        <p>まだ完了したシミュレーションがありません。シミュレーションを実行すると集計されます。</p>
      )}
      <table className="timing-grid">
        <tbody>
          {grid.map((row, i) => (
            <tr key={i}>
              {row.map((cell) => (
                <TimingHeatmapCell
                  key={`${cell.weather}_${cell.dayType}_${cell.hasEvent}`}
                  cell={cell}
                  minStep={minStep}
                  maxStep={maxStep}
                  warnRgb={warnRgb}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
