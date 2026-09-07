#!/usr/bin/env python3
"""check_raw_html_assets() のalt判定の回帰テスト。

solレビュー(PR #244)で見つかった穴の再発防止:
aria-hidden="true" さえあればalt属性ごと欠落したimgが通ってしまっていた。
装飾画像でもalt属性自体は必須(値は空が正)。
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_column", Path(__file__).parent / "check-column.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# 実在する画像を使う(実在チェックのエラーを混ぜないため)
SRC = "/images/column/ai-data-analysis-guide/logos/claude.svg"
assert (mod.ROOT / "content" / SRC.lstrip("/")).exists(), f"テスト前提の画像がない: {SRC}"

CASES = [
    # (説明, imgタグ, alt起因エラーを期待するか)
    ("装飾: alt空 + aria-hidden", f'<img src="{SRC}" alt="" aria-hidden="true">', False),
    ("装飾: alt属性なし + aria-hidden", f'<img src="{SRC}" aria-hidden="true">', True),
    ("装飾: 非空alt + aria-hidden", f'<img src="{SRC}" alt="Claudeのロゴ" aria-hidden="true">', True),
    ("通常: 非空alt", f'<img src="{SRC}" alt="Claudeのロゴ">', False),
    ("通常: alt空", f'<img src="{SRC}" alt="">', True),
    ("通常: alt属性なし", f'<img src="{SRC}">', True),
]

failed = 0
for desc, tag, expect_error in CASES:
    errors = mod.check_raw_html_assets(tag)
    got_error = bool(errors)
    ok = got_error == expect_error
    print(f"{'OK ' if ok else 'NG '} {desc}: errors={errors}")
    if not ok:
        failed += 1

if failed:
    print(f"\ntest-check-column-alt: {failed}/{len(CASES)} 件失敗")
    sys.exit(1)
print(f"\ntest-check-column-alt: 全{len(CASES)}件通過")
