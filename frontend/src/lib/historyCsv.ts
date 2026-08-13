import type { SimulationSummary } from '../api/types'

const HEADER = [
  '実行ID',
  '日時',
  '天気',
  '曜日',
  'イベント',
  '目標廃棄率(%)',
  '商品名',
  '実績廃棄率(%)',
  '達成可否',
]

/** RFC4180ふうのフィールドエスケープ。カンマ・ダブルクォート・改行を含む場合だけ引用符で囲む。
 * さらに、CSVインジェクション（Formula Injection）対策として、値が `=` `+` `-` `@` で
 * 始まる場合は先頭にシングルクォートを1つ足し、Excel等が数式として評価しないようにする
 * （商品名は`POST /api/products`で自由入力のため、このCSVに紛れ込みうる。docs/spec.md §4③）。 */
function escapeField(value: string): string {
  const guarded = /^[=+\-@]/.test(value) ? `'${value}` : value
  if (/[",\r\n]/.test(guarded)) {
    return `"${guarded.replace(/"/g, '""')}"`
  }
  return guarded
}

function toRow(fields: string[]): string {
  return fields.map(escapeField).join(',')
}

/**
 * 履歴画面（`/history`）のCSVダウンロード用データを組み立てる純関数
 * （docs/spec.md §4③「CSVダウンロード」）。
 * 1回の実行 × 1商品を1行とする。商品が1件も無い回も、その回の行（空欄）を出力し欠落させない。
 * 改行はCRLF（Excel互換）。UTF-8 BOMはこの関数の外（呼び出し元のBlob生成時）で付与する。
 */
export function buildHistoryCsv(runs: SimulationSummary[]): string {
  const lines = [toRow(HEADER)]

  for (const r of runs) {
    const datetime = new Date(r.started_at).toLocaleString('ja-JP')
    const wasteRate = String(Math.round(r.target_waste_rate * 100))
    const base = [
      String(r.id),
      datetime,
      r.weather,
      r.day_type,
      r.has_event ? 'あり' : 'なし',
      wasteRate,
    ]

    if (r.finals.length === 0) {
      lines.push(toRow([...base, '', '', '']))
      continue
    }

    for (const f of r.finals) {
      lines.push(
        toRow([
          ...base,
          f.product_name,
          String(Math.round(f.final_waste_rate * 100)),
          f.achieved ? '達成' : '未達',
        ]),
      )
    }
  }

  return lines.join('\r\n')
}
