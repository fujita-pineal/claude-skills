#!/usr/bin/env node
/**
 * check-headings.mjs の変異テスト。
 *
 * 「素の状態で違反0」だけでは、検査が実は何も見ていない状態(セレクタの綴り違い、
 * 走査対象の取りこぼし)を通してしまう。実際に直した不具合を1つずつ壊して戻し、
 * 検査が必ず落ちることを確かめる。
 *
 * 使い方: node scripts/test-check-headings.mjs
 */
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(join(HERE, '..'));
const FIXTURES = join(HERE, 'fixtures/check-headings');
const CHECKER = join(HERE, 'check-headings.mjs');

const COLUMN_MD = 'content/column/sample.md';
const TOPIC_MD = 'content/topics/sample.md';
const COLUMN_HTML = 'site/column/sample/index.html';
const POLICY_HTML = 'site/privacypolicy/index.html';
const PRODUCT_HTML = 'site/products/sample/index.html';

/** ファイルを1つ書き換える変異を作る。 */
const edit = (file, from, to) => (root) => {
  const path = join(root, file);
  const body = readFileSync(path, 'utf8');
  if (!body.includes(from)) throw new Error(`変異の前提が崩れている: ${file} に ${from} がない`);
  writeFileSync(path, body.replace(from, to));
};

/** ファイルを1つ足す変異を作る。 */
const add = (file, body) => (root) => writeFileSync(join(root, file), body);

const MUTATIONS = [
  {
    name: 'topics の先頭見出しを h3 にする',
    expect: '先頭の見出しが h3: topics/sample.md',
    mutate: edit(TOPIC_MD, '## 課題', '### 課題'),
  },
  {
    name: 'コラム本文に h1 を書く',
    expect: '本文に h1 がある: column/sample.md',
    mutate: edit(COLUMN_MD, '## 章A', '# 章A'),
  },
  {
    name: '原稿で h2 から h4 へ飛ばす',
    expect: '見出しレベルが h2 から h4 へ飛ぶ: column/sample.md',
    mutate: edit(COLUMN_MD, '### 節A1', '#### 節A1'),
  },
  {
    name: '強調を含む見出しでも文言を報告できるか',
    expect: '「章A」',
    mutate: edit(TOPIC_MD, '## 課題', '### **章A**'),
  },
  {
    name: '成果物から h1 を消す',
    expect: 'h1 が 0 個: column/sample/index.html',
    mutate: edit(COLUMN_HTML, '<h1 class="title">見本のコラム</h1>', ''),
  },
  {
    name: '成果物に h1 を2つ置く',
    expect: 'h1 が 2 個: privacypolicy/index.html',
    mutate: edit(POLICY_HTML, '<div class="doc">', '<div class="doc"><h1>おまけ</h1>'),
  },
  {
    name: '成果物で h2 から h4 へ飛ばす',
    expect: '見出しレベルが h2 から h4 へ飛ぶ: privacypolicy/index.html',
    mutate: edit(POLICY_HTML, '<h3>1. 事業者の名称</h3>', '<h4>1. 事業者の名称</h4>'),
  },
  {
    name: 'リストの直下に li 以外を置く',
    expect: '<ol> の直下に <div>: privacypolicy/index.html',
    mutate: edit(POLICY_HTML, '<li><a href="#art-1">', '<div>区切り</div><li><a href="#art-1">'),
  },
  {
    name: '目次のリンク先を存在しない id にする',
    expect: '目次のリンク先がない: privacypolicy/index.html -> #art-9',
    mutate: edit(POLICY_HTML, 'href="#art-1"', 'href="#art-9"'),
  },
  {
    name: '目次の h3 を子リストから出してフラットに並べる',
    expect: '目次が本文の見出しと一致しない: column/sample/index.html',
    mutate: edit(
      COLUMN_HTML,
      '<ol class="toc-sub">\n<li><span class="toc-dash" aria-hidden="true">–</span><a href="#a1">節A1</a></li>\n</ol>\n</li>',
      '</li>\n<li><a href="#a1">節A1</a></li>',
    ),
  },
  {
    name: '本文の h3 を増やしても目次を直さない',
    expect: '目次が本文の見出しと一致しない: column/sample/index.html',
    mutate: edit(COLUMN_HTML, '<h2 id="b">章B</h2>', '<h2 id="b">章B</h2><h3 id="b1">節B1</h3>'),
  },
  {
    // 件数だけを見る検査だと、章を1つ落として別の章のリンクを複製しても素通りする
    name: '目次から章Bを落として章Aのリンクを複製する',
    expect: '目次が同じリンク先を2回指す: column/sample/index.html -> #a',
    mutate: edit(COLUMN_HTML, '<li><a href="#b">章B</a></li>', '<li><a href="#a">章A</a></li>'),
  },
  {
    // 件数は動かないまま、節A1 が章B の子にぶら下がる形
    name: '目次の子リストを章Aから章Bへ移す',
    expect: '目次が本文の見出しと一致しない: column/sample/index.html',
    mutate: (root) => {
      const sub =
        '<ol class="toc-sub">\n<li><span class="toc-dash" aria-hidden="true">–</span><a href="#a1">節A1</a></li>\n</ol>\n';
      edit(COLUMN_HTML, sub, '')(root);
      edit(COLUMN_HTML, '<li><a href="#b">章B</a></li>', `<li><a href="#b">章B</a>\n${sub}</li>`)(root);
    },
  },
  {
    name: '目次リストから data-marker を外す',
    expect: '目次の文言が自前で番号を持つのに data-marker="none" がない: privacypolicy/index.html',
    mutate: edit(POLICY_HTML, '<ol data-marker="none" style="list-style: none !important">', '<ol>'),
  },
  {
    // 属性は残したまま list-style だけ消す。旧 High 1 の再発経路そのもの
    name: 'style 属性から list-style を消す',
    expect: 'data-marker="none" の目次の style 属性が「list-style: none !important」でない: privacypolicy/index.html',
    mutate: edit(POLICY_HTML, ' style="list-style: none !important"', ''),
  },
  {
    // 契約は完全一致。宣言を後ろに足すと後勝ちで decimal になるので、混入自体を許さない
    name: 'style 属性の後ろに decimal を足す',
    expect: 'data-marker="none" の目次の style 属性が「list-style: none !important」でない: privacypolicy/index.html',
    mutate: edit(
      POLICY_HTML,
      'style="list-style: none !important"',
      'style="list-style: none !important; list-style: decimal !important"',
    ),
  },
  {
    // 以下5件は「検出してはいけない」変異。style 属性の !important で決めているので、
    // 制作者側の CSS をどういじっても画面の結果は変わらない
    // (sol #399 Medium 1 の3経路 + sol #401 Medium 1 の !important 2経路)
    name: 'CSS のセレクタが対象に当たらなくなっても表示は変わらない',
    expect: null,
    mutate: edit(POLICY_HTML, '.toc ol[data-marker=none]', '.ghost[data-marker=none]'),
  },
  {
    name: 'CSS で list-style:decimal!important を足しても表示は変わらない',
    expect: null,
    mutate: edit(POLICY_HTML, '</style>', '.toc ol{list-style:decimal!important}</style>'),
  },
  {
    name: 'CSS で all:revert!important を足しても表示は変わらない',
    expect: null,
    mutate: edit(POLICY_HTML, '</style>', '.toc ol{all:revert!important}</style>'),
  },
  {
    name: 'CSS を @media print に閉じ込めても表示は変わらない',
    expect: null,
    mutate: edit(
      POLICY_HTML,
      '.toc ol[data-marker=none]{padding-left:0;margin:0}',
      '@media print{.toc ol[data-marker=none]{padding-left:0;margin:0}}',
    ),
  },
  {
    name: '後段に list-style:decimal を足しても表示は変わらない',
    expect: null,
    mutate: edit(POLICY_HTML, '</style>', '.toc ol[data-marker=none]{list-style:decimal}</style>'),
  },
  {
    name: '目次の最上位リストを ul にする',
    expect: '目次の直下が <ul>: column/sample/index.html',
    mutate: (root) => {
      edit(COLUMN_HTML, '<ol>\n<li><a href="#a">章A</a>', '<ul>\n<li><a href="#a">章A</a>')(root);
      edit(COLUMN_HTML, '</ol>\n</nav>', '</ul>\n</nav>')(root);
    },
  },
  {
    name: '目次の子リストから toc-sub を外す',
    expect: '目次の子リストが <ol class="">: column/sample/index.html',
    mutate: edit(COLUMN_HTML, '<ol class="toc-sub">', '<ol>'),
  },
  {
    name: 'flow-grid を div に戻す',
    expect: '.flow-grid が <div>: products/sample/index.html',
    mutate: edit(PRODUCT_HTML, '<ol class="flow-grid">', '<div class="flow-grid">'),
  },
  {
    name: 'pain-list を ol に取り違える',
    expect: '.pain-list が <ol>: products/sample/index.html',
    mutate: edit(PRODUCT_HTML, '<ul class="pain-list">', '<ol class="pain-list">'),
  },
  {
    name: 'パンくずを p に戻す',
    expect: '.breadcrumb が <p>: products/sample/index.html',
    mutate: edit(PRODUCT_HTML, '<nav class="breadcrumb" aria-label="パンくず">', '<p class="breadcrumb">'),
  },
  {
    name: 'パンくずの現在地から aria-current を外す',
    expect: '.breadcrumb の aria-current="page" が 0 件: products/sample/index.html',
    mutate: edit(PRODUCT_HTML, '<li aria-current="page">PRODUCT</li>', '<li>PRODUCT</li>'),
  },
  {
    // 件数だけ見ていると、現在地が先頭の TOP に付いていても素通りする
    name: 'パンくずの現在地を末尾から先頭へ移す',
    expect: '.breadcrumb の aria-current="page" が 1 件目: products/sample/index.html',
    mutate: (root) => {
      edit(PRODUCT_HTML, '<li aria-current="page">PRODUCT</li>', '<li>PRODUCT</li>')(root);
      edit(PRODUCT_HTML, '<li><a href="/">TOP</a>', '<li aria-current="page"><a href="/">TOP</a>')(root);
    },
  },
  {
    name: 'パンくずの nav から aria-label を外す',
    expect: '.breadcrumb の aria-label が「なし」: products/sample/index.html',
    mutate: edit(PRODUCT_HTML, '<nav class="breadcrumb" aria-label="パンくず">', '<nav class="breadcrumb">'),
  },
  {
    // クラス起点の検査だけだと、nav ごと削除しても発火しない
    name: 'パンくずを nav ごと削除する',
    expect: 'パンくずがない: products/sample/index.html',
    mutate: edit(
      PRODUCT_HTML,
      '<nav class="breadcrumb" aria-label="パンくず">\n<ol>\n<li><a href="/">TOP</a><span class="crumb-sep" aria-hidden="true">/</span></li>\n<li aria-current="page">PRODUCT</li>\n</ol>\n</nav>\n',
      '',
    ),
  },
  {
    // 同名の navigation landmark が2つ並ぶと読み上げで区別できない
    name: 'パンくずの nav を複製する',
    expect: 'パンくずが 2 件: products/sample/index.html',
    mutate: edit(
      PRODUCT_HTML,
      '<h1>見本のプロダクト</h1>',
      '<nav class="breadcrumb" aria-label="パンくず"><ol><li><a href="/">TOP</a></li><li aria-current="page">PRODUCT</li></ol></nav>\n<h1>見本のプロダクト</h1>',
    ),
  },
  {
    // DOM にはあっても AX tree から消える
    name: 'パンくずの nav に aria-hidden を付ける',
    expect: 'パンくずが <nav> の hidden / aria-hidden の中: products/sample/index.html',
    mutate: edit(
      PRODUCT_HTML,
      '<nav class="breadcrumb" aria-label="パンくず">',
      '<nav class="breadcrumb" aria-label="パンくず" aria-hidden="true">',
    ),
  },
  {
    name: 'パンくずの祖先に hidden を付ける',
    expect: 'パンくずが <div> の hidden / aria-hidden の中: products/sample/index.html',
    mutate: (root) => {
      edit(PRODUCT_HTML, '<nav class="breadcrumb" aria-label="パンくず">', '<div hidden><nav class="breadcrumb" aria-label="パンくず">')(root);
      edit(PRODUCT_HTML, '</nav>', '</nav></div>')(root);
    },
  },
  {
    // クラスを改名しても aria-label 起点の検査から逃れられない
    name: 'パンくずのクラスを改名して現在地も外す',
    expect: 'nav[aria-label="パンくず"] の aria-current="page" が 0 件: products/sample/index.html',
    mutate: (root) => {
      edit(PRODUCT_HTML, '<nav class="breadcrumb" aria-label="パンくず">', '<nav class="bc" aria-label="パンくず">')(root);
      edit(PRODUCT_HTML, '<li aria-current="page">PRODUCT</li>', '<li>PRODUCT</li>')(root);
    },
  },
  {
    // クラスごと消して div に戻す。CONTRACT はクラスが残っている前提なので発火しない
    name: 'flow-grid をクラスごと消して div に戻す',
    expect: '.flow-grid がない: products/sample/index.html',
    mutate: (root) => {
      edit(PRODUCT_HTML, '<ol class="flow-grid">', '<div class="flow-wrap">')(root);
      edit(PRODUCT_HTML, '<li class="flow-card"><h3>試す</h3><p>本文。</p></li>\n</ol>', '<div class="flow-card"><h3>試す</h3><p>本文。</p></div>\n</div>')(root);
      edit(PRODUCT_HTML, '<li class="flow-card"><h3>要件を決める</h3><p>本文。</p></li>', '<div class="flow-card"><h3>要件を決める</h3><p>本文。</p></div>')(root);
    },
  },
  {
    // 免除は「検査しない」ことなので、免除が効いているかも変異で確かめる
    name: 'ベンダー所有確認ページは免除されている',
    expect: null,
    mutate: add(
      'site/atlassian-domain-verification-4fec8cb2-7416-445b-b8b4-d70e999107d0.html',
      '<html><body><h1>Instructions</h1><h2>What</h2><h4>OR</h4><h1>Token</h1></body></html>',
    ),
  },
  {
    // 免除はファイル名の完全一致。命名が似ているだけの別ページまで自動で免除しない
    name: '別名の所有確認ページは免除されない',
    expect: 'h1 が 2 個: atlassian-domain-verification-deadbeef.html',
    mutate: add(
      'site/atlassian-domain-verification-deadbeef.html',
      '<html><body><h1>Instructions</h1><h2>What</h2><h4>OR</h4><h1>Token</h1></body></html>',
    ),
  },
];

function run(root) {
  const proc = spawnSync('node', [CHECKER], {
    cwd: ROOT,
    encoding: 'utf8',
    env: {
      ...process.env,
      CHECK_HEADINGS_CONTENT: join(root, 'content'),
      CHECK_HEADINGS_DIST: join(root, 'site'),
    },
  });
  return { code: proc.status, out: `${proc.stdout}${proc.stderr}` };
}

function withFixtures(fn) {
  const root = mkdtempSync(join(tmpdir(), 'check-headings-'));
  try {
    cpSync(FIXTURES, root, { recursive: true });
    return fn(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

let failed = 0;

const base = withFixtures((root) => run(root));
if (base.code !== 0) {
  console.error('素のフィクスチャで違反が出た(検査器かフィクスチャが壊れている):');
  console.error(base.out);
  process.exit(1);
}

for (const m of MUTATIONS) {
  const result = withFixtures((root) => {
    m.mutate(root);
    return run(root);
  });
  if (m.expect === null) {
    if (result.code === 0) continue;
    failed++;
    console.error(`NG(検出してはいけないものを検出): ${m.name}\n${result.out}`);
    continue;
  }
  if (result.code !== 0 && result.out.includes(m.expect)) continue;
  failed++;
  console.error(`NG(取りこぼし): ${m.name}\n  期待: ${m.expect}\n  実際: ${result.out.trim()}`);
}

if (failed) {
  console.error(`${MUTATIONS.length}変異のうち ${failed} 件で取りこぼし`);
  process.exit(1);
}
console.log(`変異テスト: ${MUTATIONS.length}件すべて検出`);
