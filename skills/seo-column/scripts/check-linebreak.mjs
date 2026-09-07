// ビルド済みHTMLの<wbr>配置を検査し、見出しの「変な改行」の既知パターンを検出する。
//
// ja-linebreak.mjs はビルド時に改行機会(<wbr>)を確定させるため、レンダリング不要で
// dist/ の走査だけで改行位置の不変条件を検証できる。過去に本番で見つかった2クラス:
//   1. 助詞の行頭落ち   「リスク / の現在地」 (2026-08-15 レビュー担当者報告, PR #208)
//   2. 数字複合語の分離 「対策の4 / 本柱」    (2026-08-15 レビュー担当者報告, PR #210)
// を不変条件として恒久化する。新しいクラスが見つかったらここに追加する。
//
// 使い方: npm run build 後に `node scripts/check-linebreak.mjs [distDir]`
// 違反があれば一覧を出して exit 1。

import { readFileSync } from 'node:fs';
import { globSync } from 'node:fs';

const DIST = process.argv[2] || 'dist';

// PARTICLE_TAIL(ja-linebreak.mjs)と同じ集合。import せず複製もしない、が理想だが
// 検査は「実装と独立した期待値」であるべきなので、あえてここに明示する。
// 実装側の集合を変えたら、この期待値も意図を確認して更新する。
const PARTICLES = 'のをにへとがはもでやからどばるな';

const RULES = [
  {
    name: '助詞の行頭落ち(<wbr>直後が助詞)',
    re: new RegExp(`<wbr>[${PARTICLES}]`, 'g'),
  },
  {
    name: '数字複合語の分離(数字→非数字)',
    re: /[0-9０-９]<wbr>(?![0-9０-９])/g,
  },
  {
    name: '数字複合語の分離(漢字・カタカナ→数字)',
    re: /[々〇㐀-䶿一-鿿ァ-ヺ]<wbr>[0-9０-９]/g,
  },
];

const files = globSync(`${DIST}/**/index.html`);
if (files.length === 0) {
  console.error(`ERROR: ${DIST}/ にindex.htmlがない。先に npm run build を実行する`);
  process.exit(1);
}

let bad = 0;
for (const f of files) {
  const html = readFileSync(f, 'utf-8');
  for (const rule of RULES) {
    for (const m of html.matchAll(rule.re)) {
      bad++;
      const ctx = html
        .slice(Math.max(0, m.index - 40), m.index + 40)
        .replace(/<(?!\/?wbr)[^>]+>/g, '')
        .replace(/\s+/g, ' ');
      console.log(`NG [${rule.name}] ${f}\n    …${ctx}…`);
    }
  }
}

console.log(`check-linebreak: ${files.length}ページ走査, 違反 ${bad}件`);
process.exit(bad ? 1 : 0);
