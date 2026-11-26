import { discountLabel, monitorPrice } from '../lib/discountLabel'

export interface MonitorItem {
  productId: number
  name: string
  unitPrice: number | null
  //: モニターに出ている（承認済みの）値引き率
  appliedRate: number
  remainingStock: number | null
}

/**
 * 売り場モニター（お客さんに見える表示。docs/spec.md §4①・§5.11）。
 * シールの代わりに、今の値引きを商品ごとに一覧で出す。承認待ちの値引き（55%以上）は出さない
 * （モニターに出るのはナイトマネージャーが承認したものだけ）。売り切れた商品は「売り切れ」。
 */
export default function MonitorBoard({ items, clock }: { items: MonitorItem[]; clock: string }) {
  return (
    <section className="monitor-board" aria-label="売り場モニター">
      <div className="monitor-header">
        <span>お惣菜コーナー　売り場モニター</span>
        <span>{clock}</span>
      </div>
      <ul>
        {items.map((item) => {
          const soldOut = item.remainingStock === 0
          const discounted = item.appliedRate > 0 && !soldOut
          const label = discountLabel(item.appliedRate, item.unitPrice)
          return (
            <li
              key={item.productId}
              className={soldOut ? 'sold-out' : discounted ? 'discounted' : undefined}
            >
              <span className="monitor-name">{item.name}</span>
              {soldOut ? (
                <span className="monitor-price">売り切れ</span>
              ) : (
                <span className="monitor-price">
                  {item.unitPrice != null &&
                    (discounted ? (
                      <>
                        <s>¥{item.unitPrice}</s>
                        <strong>¥{monitorPrice(item.unitPrice, item.appliedRate)}</strong>
                      </>
                    ) : (
                      <strong>¥{item.unitPrice}</strong>
                    ))}
                </span>
              )}
              {discounted && (
                <span className="sticker">{label}</span>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
