#!/usr/bin/env python3
"""PPTX 日本語折り返し検知(house-rules H1 用)。

html2pptx 系のデッキは、ブラウザ実測幅ぴったりのテキストボックスを作る。
PowerPoint 実機では日本語グリフがより広い代替フォント(游ゴシック等)に置換され、
さらに既定インセット(左右 0.1in)が効くため、作成時に1行だった段落が折り返し、
枠の高さを超えて下の要素の裏に隠れる。LibreOffice の PDF 化では代替フォントが
異なり再現しないので、実測ではなく East Asian width による机上見積りで検知する。

判定(CJK を含む全テキスト枠の全段落が対象。段落数・箱の高さで対象を絞らない):
  見積り幅 = Σ(全角 1.0em / ASCII は Arial 実メトリクス近似) x フォントサイズ
  作成時1行 = 見積り幅 <= 箱のフル幅
  実機判定 = 見積り幅 と 実効幅(箱幅 - 左右インセット) の比較

  - WRAP RISK(修正必須): 作成時1行の段落が実機見積りで2行以上になる。
    枠は1行分しか想定していないため、増えた行は枠外に出るか下の要素に隠れる
  - BORDERLINE(要確認): 作成時1行の段落で、実機見積りが実効幅の98%以上
    (わずかな幅差で1行増える)

  作成時から複数行の段落(本文ブロック・縦長ラベル)は対象外。
  それらの折り返しは LibreOffice レンダリングでも見えるため、H1 の目視で判定する。

BORDERLINE はレンダリング(LibreOffice)が正常でも解消扱いにしない(実機でのみ再現するため)。
テキスト短縮で98%を切るか、レビュー担当者が PowerPoint 実機で表示確認した場合のみ解消。

較正データ(2026-08-31 実測、游ゴシック21pt・全角13文字相当=見積り273pt):
実効幅270ptの箱では実機で折り返し、実効幅275.8ptの箱では収まった。
つまり游ゴシック全角はほぼ1.0emちょうどで、置換余裕係数は1.0(旧1.04は過大で誤検知)。
不確かさは BORDERLINE 帯(98〜100%)で吸収する。

使い方: python3 pptx_jp_wrap_check.py <file.pptx>
終了コード: 0 = 検出なし / 1 = 検出あり(BORDERLINE のみでも 1) / 2 = 実行エラー
"""
import math
import sys
import unicodedata
from pptx import Presentation
from pptx.util import Emu

SUBSTITUTION_MARGIN = 1.0
BORDERLINE_RATIO = 0.98
DEFAULT_FONT_PT = 18.0
DEFAULT_INSET_LR_PT = 7.2   # 0.1 inch

NARROW = set('ijl')          # 0.222
THIN = set("ft!.,:;'|()[] ")  # 0.278
WIDE = set('mMG@')            # 0.833
XWIDE = set('W%')             # 0.944


def is_cjk(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ('W', 'F', 'A')


def char_em(ch: str) -> float:
    if is_cjk(ch):
        return 1.0
    if ch in NARROW:
        return 0.222
    if ch in THIN:
        return 0.278
    if ch == 'r':
        return 0.333
    if ch in WIDE:
        return 0.833
    if ch in XWIDE:
        return 0.944
    if ch.isupper():
        return 0.7
    return 0.556


def para_font_pt(para, fallback: float) -> float:
    sizes = [r.font.size.pt for r in para.runs if r.font.size is not None]
    if sizes:
        return max(sizes)
    if para.font.size is not None:
        return para.font.size.pt
    return fallback


def margin_pt(value, default_pt: float) -> float:
    if value is None:
        return default_pt
    return Emu(value).pt


def check(path: str):
    prs = Presentation(path)
    wrap_risk = []
    borderline = []
    for idx, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            tf = shape.text_frame
            if tf.word_wrap is False:
                continue  # 折り返さない設定の箱は対象外(はみ出しはレンダリングで見える)
            shape_w = Emu(shape.width).pt
            usable_w = shape_w - margin_pt(tf.margin_left, DEFAULT_INSET_LR_PT) \
                - margin_pt(tf.margin_right, DEFAULT_INSET_LR_PT)
            if usable_w <= 0:
                continue
            for para in tf.paragraphs:
                text = para.text
                if not text.strip() or not any(is_cjk(c) for c in text):
                    continue
                font_pt = para_font_pt(para, DEFAULT_FONT_PT)
                base_w = sum(char_em(c) for c in text) * font_pt
                if base_w > shape_w:
                    continue  # 作成時から複数行の段落は対象外(レンダリングの目視で判定)
                real_ratio = base_w * SUBSTITUTION_MARGIN / usable_w
                if real_ratio > 1.0:
                    wrap_risk.append((idx, text, font_pt, usable_w, real_ratio))
                elif real_ratio >= BORDERLINE_RATIO:
                    borderline.append((idx, text, real_ratio))
    return wrap_risk, borderline


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    wrap_risk, borderline = check(sys.argv[1])
    if not wrap_risk and not borderline:
        print('OK: 折り返しリスクのあるテキストボックスは検出されませんでした')
        return 0
    if wrap_risk:
        print(f'WRAP RISK: {len(wrap_risk)}件(作成時1行の段落が実機で折り返す見積り。修正必須)')
        for idx, text, font_pt, usable_w, ratio in wrap_risk:
            label = text if len(text) <= 50 else text[:50] + '…'
            print(f'  slide {idx}: "{label}" ({font_pt:.1f}pt) 実効幅の {ratio * 100:.0f}% (実効幅 {usable_w:.1f}pt)')
    if borderline:
        print(f'BORDERLINE: {len(borderline)}件(要確認。実機で1行増える恐れ)')
        for idx, text, ratio in borderline:
            label = text if len(text) <= 50 else text[:50] + '…'
            print(f'  slide {idx}: "{label}" 実効幅の {ratio * 100:.0f}%')
    print('注: BORDERLINE はレンダリング正常でも解消扱いにしない。短縮するか実機で表示確認する')
    return 1


if __name__ == '__main__':
    sys.exit(main())
