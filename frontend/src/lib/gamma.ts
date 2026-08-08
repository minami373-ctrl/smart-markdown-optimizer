/**
 * ガンマ分布の確率密度関数（PDF）。標準ライブラリにガンマ関数が無いので、
 * Lanczos近似で ln Γ(x) を計算し、対数空間でPDFを求める（オーバーフロー対策）。
 */

const LANCZOS_G = 7
const LANCZOS_COEF = [
  0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
  -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6,
  1.5056327351493116e-7,
]

/**
 * ln Γ(x) を返す。x<=0 の整数（Γ関数の極）や、反射公式が発散する点では NaN を返す
 * （このアプリでは alpha は常に正なので、gammaPdf 経由の呼び出しではその範囲に来ない）。
 */
export function logGamma(x: number): number {
  if (x < 0.5) {
    // 反射公式（x<0.5だとLanczos近似の精度が落ちるため）
    return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x)
  }
  const xm1 = x - 1
  let a = LANCZOS_COEF[0]
  const t = xm1 + LANCZOS_G + 0.5
  for (let i = 1; i < LANCZOS_G + 2; i++) {
    a += LANCZOS_COEF[i] / (xm1 + i)
  }
  return 0.5 * Math.log(2 * Math.PI) + (xm1 + 0.5) * Math.log(t) - t + Math.log(a)
}

export function gammaPdf(x: number, alpha: number, beta: number): number {
  if (x <= 0 || alpha <= 0 || beta <= 0) return 0
  const logPdf = alpha * Math.log(beta) - logGamma(alpha) + (alpha - 1) * Math.log(x) - beta * x
  return Math.exp(logPdf)
}

/** グラフ描画用に、0〜xMaxの範囲でPDFを`points`個サンプリングする。 */
export function gammaCurve(alpha: number, beta: number, points = 60) {
  const mean = beta > 0 ? alpha / beta : 1
  const xMax = Math.max(mean * 3, 1)
  const xs = Array.from({ length: points }, (_, i) => (i / (points - 1)) * xMax)
  const ys = xs.map((x) => gammaPdf(x, alpha, beta))
  return { xs, ys }
}
