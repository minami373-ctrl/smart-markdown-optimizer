import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import type { StockAdjustmentLogEntry } from '../api/types'
import { buildStockAdjustmentHistoryData } from '../lib/stockAdjustmentHistoryData'
import { chartAxisColors, useTheme } from '../lib/useTheme'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const REASON_COLORS = {
  opportunity: '#2f9e44', // 機会損失で増加
  overstock: '#d9480f', // 過剰在庫で減少
} as const

interface Props {
  entries: StockAdjustmentLogEntry[]
}

/**
 * 商品ごとの在庫調整履歴（docs/spec.md §5.8）を小さな折れ線グラフで表示する
 * （`ProductsPage`の商品カード内）。横軸=発生順、縦軸=その時点のinitial_stock。
 * 増加（機会損失起因）と減少（過剰在庫起因）を点の色で区別し、値が収束していく様子を見せる
 * （§5.7 step4のダンピングの効果を可視化する狙い）。
 * 一度も自動調整が発生していない商品（entries=[]）には何も描画しない。
 */
export default function StockAdjustmentHistory({ entries }: Props) {
  const theme = useTheme()
  const axisColors = chartAxisColors(theme)

  if (entries.length === 0) return null

  const { labels, values, reasons } = buildStockAdjustmentHistoryData(entries)
  const pointColors = reasons.map((r) => REASON_COLORS[r])

  return (
    <div className="stock-adjustment-history">
      <p className="chart-caption">
        在庫調整履歴（<span style={{ color: REASON_COLORS.opportunity }}>● 完売で増加</span>{' '}
        <span style={{ color: REASON_COLORS.overstock }}>● 売れ残りで減少</span>）
      </p>
      <div className="stock-adjustment-history-chart">
        <Line
          data={{
            labels,
            datasets: [
              {
                data: values,
                borderColor: axisColors.tick,
                backgroundColor: axisColors.tick,
                pointBackgroundColor: pointColors,
                pointBorderColor: pointColors,
                pointRadius: 4,
                tension: 0.2,
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
