/**
 * 店全体の「いつもと違う」の知らせ（docs/spec.md §5.16）。商品1つずつの知らせはばらつきが大きい
 * （いつもどおりの日でも2割の商品に出る）ため、**半分以上の商品が同じ向きに外れたときだけ**店全体の
 * 知らせにする。いつもどおりの日に出るのは3%ほど、長期休みを入れ忘れた日は73%ほどで出る。
 */
export function storeAlert(alerts: (string | null | undefined)[]): string | null {
  const n = alerts.length
  if (n === 0) return null
  const low = alerts.filter((a) => a === 'low').length
  const high = alerts.filter((a) => a === 'high').length
  if (low * 2 >= n) {
    return `今日はいつもより売れていません（${n}商品中${low}商品）。長期休みなど、入れ忘れた条件がないか確認してください。`
  }
  if (high * 2 >= n) {
    return `今日はいつもより売れています（${n}商品中${high}商品）。近くでイベントなど、入れ忘れた条件がないか確認してください。`
  }
  return null
}
