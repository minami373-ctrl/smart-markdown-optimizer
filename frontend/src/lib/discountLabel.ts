/**
 * 値引き率を売り場の言葉で表す（docs/spec.md §5.3。2026-11-26追加）。
 * - 0%：値引きなし
 * - 30%：30%引き
 * - 50%：半額
 * - 半額より大きい値引き（21時以降のズバリ引き）：単価があれば「ズバリ ¥190」のように
 *   10円単位の値段で表示する。値段は切り下げ（売り切りやすい側）だが、下限
 *   （元の値段の75%引き）を下回らないよう、下限の値段は10円単位に切り上げる
 */
export const ZUBARI_FLOOR_RATE = 0.75

export function zubariPrice(unitPrice: number, rate: number): number {
  const floorPrice = Math.ceil((unitPrice * (1 - ZUBARI_FLOOR_RATE)) / 10) * 10
  const price = Math.floor((unitPrice * (1 - rate)) / 10) * 10
  return Math.max(floorPrice, price)
}

export function discountLabel(rate: number, unitPrice: number | null): string {
  if (rate <= 0) return '値引きなし'
  if (rate <= 0.5) return rate === 0.5 ? '半額' : `${Math.round(rate * 100)}%引き`
  if (unitPrice == null) return `ズバリ引き（${Math.round(rate * 100)}%引き）`
  return `ズバリ ¥${zubariPrice(unitPrice, rate)}`
}
