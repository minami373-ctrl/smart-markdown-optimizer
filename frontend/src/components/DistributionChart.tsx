import {
  CategoryScale,
  Chart as ChartJS,
  Filler,
  LinearScale,
  LineElement,
  PointElement,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { gammaCurve } from '../lib/gamma'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler)

interface Props {
  alpha: number
  beta: number
  /** 6桁hex（例 "#d9480f"）を渡すこと。塗りつぶし色は末尾に透過度を文字列結合して作る */
  color: string
}

/**
 * 需要率の事後分布（ガンマ分布）の確率密度曲線を小さく描く。
 * データが増えるほど（alpha・betaが大きいほど）山が高く鋭くなる（docs/spec.md §4①）。
 */
export default function DistributionChart({ alpha, beta, color }: Props) {
  const { xs, ys } = gammaCurve(alpha, beta, 40)

  return (
    <div className="distribution-chart">
      <Line
        data={{
          labels: xs.map((x) => x.toFixed(1)),
          datasets: [
            {
              data: ys,
              borderColor: color,
              backgroundColor: `${color}33`,
              fill: true,
              pointRadius: 0,
              tension: 0.3,
            },
          ],
        }}
        options={{
          animation: false,
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: {
            x: { display: false },
            y: { display: false, beginAtZero: true },
          },
        }}
      />
    </div>
  )
}
