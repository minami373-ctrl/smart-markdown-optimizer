export interface LearningCurveFinal {
  product_id: number
  product_name: string
  final_waste_rate: number
}

export interface LearningCurveRun {
  finals: LearningCurveFinal[]
}

export interface LearningCurveSeries {
  productId: number
  name: string
  /** 実績廃棄率(%)。その回にその商品のfinalsが無ければnull（線を途切れさせる） */
  data: (number | null)[]
}

export interface LearningCurveData {
  labels: number[] // 実行回（1始まり）
  series: LearningCurveSeries[]
}

/**
 * 連続実行（`SimulationPage`の「連続実行」）用の学習曲線データを組み立てる純関数
 * （docs/spec.md §4①「学習曲線グラフ」）。
 * 横軸=実行回（1〜N）、縦軸=実績廃棄率(%)、商品ごとに系列を分ける。
 * 商品名はいずれかの回のfinalsから解決する（`RateChart`/`StockChart`と同じ考え方）。
 */
export function buildLearningCurveData(runs: LearningCurveRun[]): LearningCurveData {
  const labels = runs.map((_, i) => i + 1)

  const productIds = [...new Set(runs.flatMap((r) => r.finals.map((f) => f.product_id)))]
  const nameById = new Map<number, string>()
  for (const run of runs) {
    for (const f of run.finals) {
      nameById.set(f.product_id, f.product_name)
    }
  }

  const series = productIds.map((productId) => ({
    productId,
    name: nameById.get(productId) ?? `商品${productId}`,
    data: runs.map((r) => {
      const f = r.finals.find((f) => f.product_id === productId)
      return f ? Math.round(f.final_waste_rate * 1000) / 10 : null
    }),
  }))

  return { labels, series }
}
