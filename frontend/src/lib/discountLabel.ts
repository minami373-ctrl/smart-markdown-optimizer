/**
 * 値引き率を売り場の言葉で表す（docs/spec.md §5.19。2026-11-26改訂）。
 * 値引きは20%〜75%の5%刻みで、すべて「〇%引き」で表示する（ズバリ引きという呼び方はやめた）。
 * 単価の引数は以前の呼び出し側との互換のために残している（表示には使わない）。
 */
export function discountLabel(rate: number, _unitPrice?: number | null): string {
  if (rate <= 0) return '値引きなし'
  return `${Math.round(rate * 100)}%引き`
}

/**
 * 値引き後の売値（docs/spec.md §4①「売り場モニター」。components/MonitorBoard.tsx で使う）。
 * 1円単位で四捨五入する。
 */
export function monitorPrice(unitPrice: number, rate: number): number {
  // 1 − 0.55 ＝ 0.44999… のような浮動小数点の誤差で、193.5円が193円に切り下がらないよう、
  // 割合を整数の%に直してから計算する（430円の55%引き＝193.5円→194円）
  const keepPercent = Math.round((1 - rate) * 100)
  return Math.round((unitPrice * keepPercent) / 100)
}
