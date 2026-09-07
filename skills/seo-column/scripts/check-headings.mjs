#!/usr/bin/env node
/**
 * 見出し階層・目次・リスト構造の契約を検査する。原稿(Markdown)と成果物(HTML)の両方を見る。
 *
 * 単発の目視で見つけた不具合を二度と入れないための回帰ゲート。実際に起きたのは次の3つ。
 *
 *   - content/topics の28記事が `###` から始まっていて、テンプレートの h1 の直後が
 *     h3 になっていた。見出しナビゲーションで章構造が1段まるごと欠ける
 *   - コラムの目次で h2 と h3 を同じ <ol> にフラットに並べ、番号を出さない h3 も
 *     序数を消費して親の番号が飛んでいた(3 の次が 7 になる)
 *   - privacypolicy の目次が「第N条」の文言とリスト序数で二重に番号を出していた
 *
 * さらに、カード並びやパンくずを div / p で組んでいたものを ol / ul / nav に直した。
 * これは見た目に出ないので、放っておくと次の編集で静かに戻る。下の CONTRACT で
 * 「このクラスはこのタグ」を成果物に対して固定している。
 *
 * 原稿側(Markdown)で見るもの:
 *   - 本文に h1 がある(タイトルはテンプレートが h1 で出すので重複する)
 *   - 先頭の見出しが h2 でない
 *   - 見出しレベルが2段以上飛ぶ
 *
 * 成果物側(HTML)で見るもの:
 *   - h1 が0個または2個以上
 *   - 見出しレベルが2段以上飛ぶ
 *   - ol / ul の直下に li 以外の要素がいる
 *   - 目次のリンク先 id がページ内に存在する / 重複しない / 本文と同じ順に並ぶ
 *   - コラムの目次が本文の見出し木(h2 と、その直下の h3 列)と id 単位で完全一致する
 *   - 目次の最上位は ol、子リストは ol.toc-sub(1項目につき0個か1個)
 *   - 文言が自前で番号を持つ目次リストは data-marker="none" を持ち、style 属性が
 *     「list-style: none !important」と完全一致している
 *   - CONTRACT のクラスが指定どおりのタグで出ている
 *   - REQUIRED の route に、そこに出るはずのクラスが実際に出ている
 *   - CRUMB_FREE 以外の全ページにパンくずがあり、nav[aria-label="パンくず"] > ol > li で
 *     末尾の項目だけが aria-current="page"
 *
 * マーカーを style 属性の !important で消しているのは、静的解析で「画面での見え方」まで
 * 保証するため。外部ルールにすると、セレクタが対象に当たらない・@media print に
 * 閉じ込められている・後段や !important のルールに負けている、のどれでも CSS の字面は
 * 正しいまま表示が壊れる。style 属性の !important には制作者側の CSS からは勝てない
 * (all: revert !important を含む)ので、属性値を完全一致で固定すれば結果が決まる
 *
 * ビルド後に走らせる(dist が要る)。検査対象は環境変数で差し替えられる(テスト用)。
 *   CHECK_HEADINGS_CONTENT … content ディレクトリ
 *   CHECK_HEADINGS_DIST    … dist ディレクトリ
 *
 * 使い方: node scripts/check-headings.mjs
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fromMarkdown } from 'mdast-util-from-markdown';
import { gfmFromMarkdown } from 'mdast-util-gfm';
import { gfm } from 'micromark-extension-gfm';
import { parse } from 'parse5';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(join(HERE, '..'));
const CONTENT = resolve(process.env.CHECK_HEADINGS_CONTENT || join(ROOT, 'content'));
const DIST = resolve(process.env.CHECK_HEADINGS_DIST || join(ROOT, 'dist'));
const FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;

// ベンダーが生成した所有確認用ページ。noindex で通常導線にも入っておらず、書き換えると
// Atlassian のドメイン所有確認が落ちる。中身は向こうの都合で決まるので検査から外す。
// 正規表現ではなくファイル名の完全一致にしてある。免除は1枚ずつ人が見て足すもので、
// 「同じ命名なら自動的に免除」にすると検査していないページが黙って増える
const DIST_ALLOWLIST = new Set([
  'atlassian-domain-verification-4fec8cb2-7416-445b-b8b4-d70e999107d0.html',
]);

// テンプレートが記事タイトルを h1 で出すコレクション。本文は h2 から始める
const MD_COLLECTIONS = ['column', 'topics'];

// クラスと、そのクラスが名乗ってよいタグ。意味構造を div / p に戻す回帰を止めるためのもの。
// ここに載せてよいのは「サイト全体で1つの用途にしか使っていないクラス名」だけ。
// たとえば flow-card は products では li、recruit では li の中の div なので載せていない
const CONTRACT = new Map([
  ['steps', 'ol'],
  ['p3-steps', 'ol'],
  ['flow-grid', 'ol'],
  ['setup-steps', 'ol'],
  ['flow-timeline', 'ol'],
  ['pain-list', 'ul'],
  ['impl-list', 'ul'],
  ['mk-grid', 'ul'],
  ['cards', 'ul'],
  ['ai-rail', 'ul'],
  ['cx-grid', 'ul'],
]);

// パンくず。nav > ol > li で組み、末尾の項目に aria-current="page" を1つだけ置く。
// 検査の起点は nav[aria-label="パンくず"](クラスを改名しても検査から逃れられない)。
// クラス側からも見て、クラスだけ残して nav をやめた回帰も拾う
const CRUMB_CLASSES = ['breadcrumb', 'crumb'];
const CRUMB_LABEL = 'パンくず';

// パンくずを置かないページ。トップ(現在地しかない)、フォーム系、一覧に出ない配布・求人詳細など。
// これ以外の全ページに nav[aria-label="パンくず"] を1件必須にする。
// パンくずを持たない新ページを作るときは、意図してここに足す
const CRUMB_FREE = [
  /^404\.html$/,
  /^index\.html$/,
  /^about\/index\.html$/,
  /^contact\/thanks\//,
  /^download\/d_[^/]+\/index\.html$/,
  /^member\/index\.html$/,
  /^press\/index\.html$/,
  /^privacypolicy\/index\.html$/,
  /^recruit\/[^/]+\/index\.html$/,
  /^recruit\/agents\/[^/]+\/index\.html$/,
];

// 文言が自前で番号を持つ形。「第1条」「1.」「(1)」。リスト序数と併せると二重番号になる
const SELF_NUMBERED = /^\s*(第\s*[0-9０-９]+\s*条|[0-9０-９]+\s*[.、．)）]|[（(]\s*[0-9０-９]+\s*[)）])/;

// マーカー抑止の style 属性。正規化(小文字化・空白と末尾セミコロン除去)して完全一致で見る。
// 「none を含む宣言がある」程度の検査だと、後ろに list-style: decimal を足された時に
// 後勝ちで負けるのを見逃す。完全一致なら余計な宣言そのものが入り込めない
const MARKER_STYLE = 'list-style:none!important';

// route と、その成果物に必ず出ていてほしいクラス。クラスごと消して div に戻す回帰を止める。
// 「クラスがあればタグを見る」検査(CONTRACT)は、クラスごと消されると発火しないため
const REQUIRED = [
  [/^index\.html$/, ['ai-rail', 'cx-grid']],
  [/^cases\/index\.html$/, ['impl-list', 'mk-grid']],
  [/^cases\/[^/]+\/index\.html$/, ['steps']],
  [/^download\/index\.html$/, ['cards']],
  [/^recruit\/index\.html$/, ['flow-timeline']],
  [/^products\/[^/]+\/index\.html$/, ['pain-list', 'flow-grid', 'setup-steps']],
  [/^(ai|marketing-creative)\/index\.html$/, ['p3-steps']],
];

const bad = [];

// ---- 原稿(Markdown) ----

function mdText(node) {
  if (typeof node.value === 'string') return node.value;
  return (node.children || []).map(mdText).join('');
}

function headingsOfMarkdown(body) {
  const tree = fromMarkdown(body, { extensions: [gfm()], mdastExtensions: [gfmFromMarkdown()] });
  const out = [];
  const visit = (node) => {
    if (node.type === 'heading') {
      // 見出しの中は強調やリンクで入れ子になる。文言は再帰で拾わないと空になる
      const text = mdText(node).trim();
      out.push({ depth: node.depth, text, line: node.position.start.line });
    }
    // コードブロックの中の `#` は heading ノードにならないのでパーサに任せる
    for (const child of node.children || []) visit(child);
  };
  visit(tree);
  return out;
}

function checkMarkdown() {
  for (const collection of MD_COLLECTIONS) {
    const dir = join(CONTENT, collection);
    if (!existsSync(dir)) continue;
    for (const name of readdirSync(dir).sort()) {
      if (!name.endsWith('.md')) continue;
      const where = `${collection}/${name}`;
      const body = readFileSync(join(dir, name), 'utf8').replace(FRONTMATTER, '');
      const headings = headingsOfMarkdown(body);
      if (headings.length === 0) continue;

      const h1 = headings.find((h) => h.depth === 1);
      if (h1) {
        bad.push(`本文に h1 がある: ${where}:${h1.line}「${h1.text}」(タイトルはテンプレートが h1 で出す)`);
      }
      if (headings[0].depth !== 2) {
        bad.push(
          `先頭の見出しが h${headings[0].depth}: ${where}:${headings[0].line}「${headings[0].text}」` +
            `(文言は変えず ## から始める)`,
        );
      }
      let prev = null;
      for (const h of headings) {
        if (prev !== null && h.depth > prev + 1) {
          bad.push(`見出しレベルが h${prev} から h${h.depth} へ飛ぶ: ${where}:${h.line}「${h.text}」`);
        }
        prev = h.depth;
      }
    }
  }
}

// ---- 成果物(HTML) ----

const HEADING = /^h[1-6]$/;

function attr(node, name) {
  return (node.attrs || []).find((a) => a.name === name)?.value;
}

function classesOf(node) {
  return (attr(node, 'class') || '').split(/\s+/).filter(Boolean);
}

function textOf(node) {
  if (node.nodeName === '#text') return node.value;
  return (node.childNodes || []).map(textOf).join('');
}

/** 深さ優先で原文順に全要素を返す。 */
function walk(node, out = []) {
  for (const child of node.childNodes || []) {
    if (child.tagName) out.push(child);
    walk(child, out);
  }
  return out;
}

function elementChildren(node) {
  return (node.childNodes || []).filter((c) => c.tagName);
}

function childLists(node) {
  return elementChildren(node).filter((c) => c.tagName === 'ol' || c.tagName === 'ul');
}

function childItems(node) {
  return elementChildren(node).filter((c) => c.tagName === 'li');
}

function htmlFiles(dir, base = dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) htmlFiles(full, base, out);
    else if (name.endsWith('.html')) out.push(relative(base, full));
  }
  return out;
}

/** li が指すリンク先の id。入れ子の目次まで潜らないよう直下の <a> だけ見る。 */
function idOfItem(li) {
  const a = elementChildren(li).find((c) => c.tagName === 'a');
  const href = a ? attr(a, 'href') || '' : '';
  if (!href.startsWith('#')) return null;
  return decodeURIComponent(href.slice(1));
}

/** 目次を「最上位 id と、その子 id 列」の木にする。 */
function tocTree(toc) {
  const list = childLists(toc)[0];
  if (!list) return null;
  return childItems(list).map((li) => ({
    id: idOfItem(li),
    subs: childLists(li).flatMap((sub) => childItems(sub).map(idOfItem)),
  }));
}

/** 本文の見出しを「h2 と、その直下に続く h3 列」の木にする。 */
function bodyTree(body) {
  const tree = [];
  let current = null;
  for (const el of walk(body).filter((e) => HEADING.test(e.tagName))) {
    const depth = Number(el.tagName[1]);
    const id = attr(el, 'id') ?? null;
    if (depth === 2) {
      current = { id, subs: [] };
      tree.push(current);
    } else if (depth === 3 && current) {
      current.subs.push(id);
    }
  }
  return tree;
}

const shape = (tree) => tree.map((n) => `${n.id ?? '(idなし)'}[${n.subs.map((s) => s ?? '(idなし)').join(' ')}]`).join(' ');

/** style 属性が MARKER_STYLE と(正規化して)完全一致しているか。 */
function inlineHidesMarker(el) {
  const style = (attr(el, 'style') || '').toLowerCase().replace(/\s+/g, '').replace(/;+$/, '');
  return style === MARKER_STYLE;
}

function checkContracts(file, elements) {
  for (const el of elements) {
    const classes = classesOf(el);

    for (const [cls, tag] of CONTRACT) {
      if (!classes.includes(cls)) continue;
      if (el.tagName !== tag) {
        bad.push(`.${cls} が <${el.tagName}>: ${file}(<${tag}> で組む。項目のまとまりはリストで出す)`);
      } else if (childItems(el).length === 0) {
        bad.push(`.${cls} に li がない: ${file}`);
      }
    }

    // クラス側からの検査。nav 以外に付いていたら、この時点で回帰
    const cls = CRUMB_CLASSES.find((c) => classes.includes(c));
    if (cls && el.tagName !== 'nav') {
      bad.push(`.${cls} が <${el.tagName}>: ${file}(パンくずは <nav> > <ol> > <li>)`);
    }
  }

  // パンくずの構造検査。起点は aria-label(クラスを改名・削除しても逃れられない)
  const crumbNavs = elements.filter(
    (el) => el.tagName === 'nav' && (attr(el, 'aria-label') === CRUMB_LABEL || CRUMB_CLASSES.some((c) => classesOf(el).includes(c))),
  );
  // 非免除ページはちょうど1件。0件は欠落、2件以上は同名の navigation landmark が重複する
  const free = CRUMB_FREE.some((re) => re.test(file));
  if (!free && crumbNavs.length !== 1) {
    bad.push(
      crumbNavs.length === 0
        ? `パンくずがない: ${file}(nav[aria-label="${CRUMB_LABEL}"] を置く。持たないページは CRUMB_FREE に足す)`
        : `パンくずが ${crumbNavs.length} 件: ${file}(1ページに1つ。読み上げで同名の navigation が並ぶ)`,
    );
  } else if (free && crumbNavs.length > 0) {
    bad.push(`CRUMB_FREE のページにパンくずがある: ${file}(置くなら CRUMB_FREE から外す)`);
  }
  for (const nav of crumbNavs) {
    // hidden / aria-hidden だと DOM にはあっても AX tree から消える。属性の直接指定だけ見る
    // (CSS による可視性までは静的検査の範囲外)
    for (let node = nav; node && node.tagName; node = node.parentNode) {
      if (attr(node, 'hidden') !== undefined || attr(node, 'aria-hidden') === 'true') {
        bad.push(`パンくずが <${node.tagName}> の hidden / aria-hidden の中: ${file}(支援技術から見えない)`);
        break;
      }
    }
    const name = CRUMB_CLASSES.find((c) => classesOf(nav).includes(c));
    const label = name ? `.${name}` : `nav[aria-label="${CRUMB_LABEL}"]`;
    // ページには他にも navigation landmark がある。名前がないと読み上げで区別できない
    if (attr(nav, 'aria-label') !== CRUMB_LABEL) {
      bad.push(`${label} の aria-label が「${attr(nav, 'aria-label') ?? 'なし'}」: ${file}(「${CRUMB_LABEL}」で固定する)`);
    }
    const list = childLists(nav)[0];
    if (!list || list.tagName !== 'ol') {
      bad.push(`${label} の直下に <ol> がない: ${file}(パンくずは順序のあるリスト)`);
      continue;
    }
    const items = childItems(list);
    if (items.length < 2) {
      bad.push(`${label} の項目が ${items.length} 件: ${file}(親と現在地で2件以上)`);
      continue;
    }
    // 現在地は末尾。件数だけ見ていると、先頭の TOP に付いていても気づけない
    const withCurrent = items
      .map((li, i) => ({ i, n: [li, ...walk(li)].filter((e) => attr(e, 'aria-current') === 'page').length }))
      .filter((x) => x.n > 0);
    const total = withCurrent.reduce((sum, x) => sum + x.n, 0);
    if (total !== 1) {
      bad.push(`${label} の aria-current="page" が ${total} 件: ${file}(現在地に1件だけ置く)`);
    } else if (withCurrent[0].i !== items.length - 1) {
      bad.push(
        `${label} の aria-current="page" が ${withCurrent[0].i + 1} 件目: ${file}` +
          `(現在地は末尾の ${items.length} 件目)`,
      );
    }
  }

  for (const [route, classes] of REQUIRED) {
    if (!route.test(file)) continue;
    for (const cls of classes) {
      if (elements.some((el) => classesOf(el).includes(cls))) continue;
      bad.push(`.${cls} がない: ${file}(このページに出ているはずのリスト。クラスごと消して div に戻していないか)`);
    }
  }
}

function checkToc(file, elements, toc) {
  const ids = new Set(elements.map((el) => attr(el, 'id')).filter(Boolean));
  const order = new Map(elements.map((el, i) => [attr(el, 'id'), i]).filter(([id]) => id));

  const links = walk(toc)
    .filter((el) => el.tagName === 'a')
    .map((a) => attr(a, 'href') || '')
    .filter((href) => href.startsWith('#'))
    .map((href) => decodeURIComponent(href.slice(1)));

  const seen = new Set();
  let prevOrder = -1;
  for (const id of links) {
    if (!ids.has(id)) {
      bad.push(`目次のリンク先がない: ${file} -> #${id}`);
      continue;
    }
    // 見出しを1つ消して別の見出しのリンクを複製すると、件数だけの検査は素通りする
    if (seen.has(id)) bad.push(`目次が同じリンク先を2回指す: ${file} -> #${id}`);
    seen.add(id);
    const at = order.get(id);
    if (at < prevOrder) {
      bad.push(`目次の並びが本文と逆: ${file} -> #${id}(本文より前の項目のあとに来ている)`);
    }
    prevOrder = Math.max(prevOrder, at);
  }

  // 目次の章は順序のあるリスト。ここで固定するのは意味構造(ol であること)まで。
  // 序数が画面に描かれるかは CSS 次第で、そこは静的検査の範囲外
  const top = childLists(toc)[0];
  if (!top) {
    bad.push(`目次に ol / ul がない: ${file}`);
    return;
  }
  if (top.tagName !== 'ol') {
    bad.push(`目次の直下が <${top.tagName}>: ${file}(章は順序のあるリスト。<ol> で組む)`);
  }
  for (const li of childItems(top)) {
    const subs = childLists(li);
    if (subs.length > 1) {
      bad.push(`目次の1項目に子リストが ${subs.length} 個: ${file}(0個か1個)`);
    }
    for (const sub of subs) {
      if (sub.tagName !== 'ol' || !classesOf(sub).includes('toc-sub')) {
        bad.push(`目次の子リストが <${sub.tagName} class="${classesOf(sub).join(' ')}">: ${file}(ol.toc-sub で固定)`);
      }
    }
  }

  // 文言が番号を持つ目次は、リスト序数を消していないと二重番号になる。
  // 消し方は style 属性の !important に限る。外部ルールだとセレクタの取り違え・
  // @media print への閉じ込め・後勝ちや !important の上書きで、CSS を読めても
  // 画面の結果までは保証できない。style 属性の !important には制作者側の CSS からは
  // 勝てない(all: revert !important を含む。カスケードで inline の important が上)ので、
  // 属性値そのものを完全一致で固定すれば静的検査だけで画面の結果が決まる
  for (const list of walk(toc).filter((el) => el.tagName === 'ol' || el.tagName === 'ul')) {
    const numbered = childItems(list).some((li) => SELF_NUMBERED.test(textOf(li).trim()));
    if (!numbered) continue;
    if (attr(list, 'data-marker') !== 'none') {
      bad.push(
        `目次の文言が自前で番号を持つのに data-marker="none" がない: ${file}` +
          `(リスト序数と二重になる)`,
      );
      continue;
    }
    if (!inlineHidesMarker(list)) {
      bad.push(
        `data-marker="none" の目次の style 属性が「list-style: none !important」でない: ${file}` +
          `(この完全一致が契約。宣言を足すと後勝ちで負けうる)`,
      );
    }
  }

  // コラムの目次は本文の見出し木そのもの。件数だけ合っていても中身が違えば不整合
  const body = elements.find((el) => classesOf(el).includes('body'));
  if (!body) return;
  const want = bodyTree(body);
  const got = tocTree(toc);
  if (!got) {
    bad.push(`目次に ol / ul がない: ${file}`);
    return;
  }
  if (shape(want) !== shape(got)) {
    bad.push(`目次が本文の見出しと一致しない: ${file}(目次 ${shape(got) || '空'} / 本文 ${shape(want) || '空'})`);
  }
}

function checkDist() {
  if (!existsSync(DIST)) {
    bad.push(`dist がない: ${DIST}(先に npm run build を実行する)`);
    return;
  }
  for (const file of htmlFiles(DIST)) {
    if (DIST_ALLOWLIST.has(file)) continue;
    const doc = parse(readFileSync(join(DIST, file), 'utf8'));
    const elements = walk(doc);

    // 見出しの数とレベル
    const headings = elements.filter((el) => HEADING.test(el.tagName));
    const h1 = headings.filter((el) => el.tagName === 'h1');
    if (h1.length !== 1) {
      bad.push(`h1 が ${h1.length} 個: ${file}(1ページに1つ)`);
    }
    let prev = null;
    for (const el of headings) {
      const depth = Number(el.tagName[1]);
      if (prev !== null && depth > prev + 1) {
        bad.push(`見出しレベルが h${prev} から h${depth} へ飛ぶ: ${file}「${textOf(el).trim()}」`);
      }
      prev = depth;
    }

    // リストの直下は li だけ
    for (const el of elements) {
      if (el.tagName !== 'ol' && el.tagName !== 'ul') continue;
      for (const child of elementChildren(el)) {
        // <script>/<template> は描画されないので li の兄弟にいても構造は壊れない
        if (child.tagName === 'li' || child.tagName === 'script' || child.tagName === 'template') continue;
        bad.push(`<${el.tagName}> の直下に <${child.tagName}>: ${file}(直下は li だけ)`);
      }
    }

    checkContracts(file, elements);

    const toc = elements.find((el) => el.tagName === 'nav' && classesOf(el).includes('toc'));
    if (toc) checkToc(file, elements, toc);
  }
}

checkMarkdown();
checkDist();

if (bad.length) {
  console.error(`見出し・目次の検査で ${bad.length} 件:`);
  for (const line of bad) console.error(`  - ${line}`);
  process.exit(1);
}
console.log('見出し・目次の検査: 違反なし');
