export interface InsightMessage {
  text: string
  to: string
}

/**
 * 分析結果バナー（docs/spec.md §4「全画面共通：分析結果バナー」）用のメッセージを組み立てる純関数。
 * 件数が0のものはメッセージを作らない。両方0件なら空配列（＝バナー自体を表示しない）。
 */
export function buildInsightMessages(
  opportunityCount: number,
  overstockCount: number,
): InsightMessage[] {
  const messages: InsightMessage[] = []
  if (opportunityCount > 0) {
    messages.push({
      text: `値引きなしで早く売り切れた商品が${opportunityCount}つあります（作る量を増やす候補）。`,
      to: '/opportunities',
    })
  }
  if (overstockCount > 0) {
    messages.push({
      text: `値引きしても売れ残った商品が${overstockCount}つあります（作る量を減らす候補）。`,
      to: '/overstock',
    })
  }
  return messages
}
