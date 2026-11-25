import { useEffect, useState } from 'react'
import { fetchOverstocks } from '../api/overstock'
import type { Overstock } from '../api/types'

export default function OverstockPage() {
  const [overstocks, setOverstocks] = useState<Overstock[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchOverstocks()
      .then(setOverstocks)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return <p className="error">{error}</p>

  return (
    <div>
      <h1>売れ残った商品</h1>
      <p>
        ズバリ引きの下限（75%引き）まで下げても売り切れなかった商品です。作る量を減らせば、廃棄を抑えられる可能性があります（過去の営業すべてから集計）。
      </p>

      {overstocks === null && <p>読み込み中…</p>}

      {overstocks !== null && overstocks.length === 0 && (
        <p className="card">値引き上限まで下げても売れ残った商品はまだありません。</p>
      )}

      {overstocks !== null && overstocks.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>順位</th>
                <th>商品名</th>
                <th>該当回数</th>
                <th>平均売れ残り数</th>
                <th>推奨削減在庫数</th>
              </tr>
            </thead>
            <tbody>
              {overstocks.map((o, i) => (
                <tr key={o.product_id}>
                  <td>{i + 1}</td>
                  <td>{o.product_name}</td>
                  <td>{o.occurrence_count}回</td>
                  <td>{Math.round(o.avg_final_remaining)}個</td>
                  <td>
                    <strong>-{Math.round(o.avg_suggested_decrease)}個</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
