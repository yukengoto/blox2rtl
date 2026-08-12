"""ポート定義の検証。

ダイアログを閉じる前に呼ぶ。Qt に依存しないので GUI を起動せずにテストできる。

入力はダイアログのセルから読んだ生の文字列。ビット幅を int() に通す前に
検査するのが目的なので、ここでは変換しない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 表の列
COL_NAME = 0
COL_WIDTH = 1
COL_WIRE = 2

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# Verilog-2001 の予約語
VERILOG_KEYWORDS = frozenset("""
always and assign automatic begin buf bufif0 bufif1 case casex casez cell cmos
config deassign default defparam design disable edge else end endcase endconfig
endfunction endgenerate endmodule endprimitive endspecify endtable endtask event
for force forever fork function generate genvar highz0 highz1 if ifnone incdir
include initial inout input instance integer join large liblist library localparam
macromodule medium module nand negedge nmos nor noshowcancelled not notif0 notif1
or output parameter pmos posedge primitive pull0 pull1 pulldown pullup
pulsestyle_ondetect pulsestyle_onevent rcmos real realtime reg release repeat
rnmos rpmos rtran rtranif0 rtranif1 scalared showcancelled signed small specify
specparam strong0 strong1 supply0 supply1 table task time tran tranif0 tranif1
tri tri0 tri1 triand trior trireg unsigned use uwire vectored wait wand weak0
weak1 while wire wor xnor xor
""".split())


@dataclass
class Issue:
    """指摘1件。where / row / column は該当セルにカーソルを移すために使う。"""

    message: str
    where: str = ""   # "module_name" / "instance_name" / "inputs" / "outputs"
    row: int = -1
    column: int = -1


def identifier_problem(name):
    """Verilog の識別子として使えない理由を返す。問題なければ空文字列。"""
    if name in VERILOG_KEYWORDS:
        return f"'{name}' は Verilog の予約語です。"
    if not _IDENTIFIER.match(name):
        return (f"'{name}' は Verilog の識別子として使えません"
                "(英字か _ で始まり、英数字と _ $ のみ)。")
    return ""


def width_problem(text):
    """ビット幅として不正な理由を返す。問題なければ空文字列。"""
    if not text:
        return "が空です。"
    try:
        value = int(text)
    except ValueError:
        return f" '{text}' が数値ではありません。"
    if value < 1:
        return f" {value} は 1 以上である必要があります。"
    return ""


def check(module_name, inputs, outputs, instance_name=None):
    """(エラー, 警告) を Issue のリストで返す。

    inputs / outputs は (ポート名, ビット幅の文字列, Wire名 または None) のリスト。
    Wire 名の列を持たない表 (モジュール側の入力表) では None を渡す。
    instance_name は サブモジュールのときだけ渡す。空欄は自動生成なので許す。
    """
    errors, warnings = [], []

    name = (module_name or "").strip()
    if not name:
        errors.append(Issue("モジュール名が空です。", where="module_name"))
    else:
        problem = identifier_problem(name)
        if problem:
            errors.append(Issue(f"モジュール名: {problem}", where="module_name"))

    if instance_name is not None:
        instance = instance_name.strip()
        if instance:
            problem = identifier_problem(instance)
            if problem:
                errors.append(Issue(f"インスタンス名: {problem}", where="instance_name"))

    seen = set()
    for where, rows in (("inputs", inputs), ("outputs", outputs)):
        label = "入力ポート" if where == "inputs" else "出力ポート"
        for row, entry in enumerate(rows):
            port_name = (entry[0] or "").strip()
            width_text = (entry[1] or "").strip()
            wire = entry[2] if len(entry) > 2 else None

            if not port_name:
                errors.append(Issue(f"{row + 1}行目の{label}名が空です。",
                                    where, row, COL_NAME))
            else:
                problem = identifier_problem(port_name)
                if problem:
                    errors.append(Issue(f"{row + 1}行目の{label}名: {problem}",
                                        where, row, COL_NAME))
                elif port_name in seen:
                    errors.append(Issue(f"ポート名 '{port_name}' が重複しています。",
                                        where, row, COL_NAME))
                else:
                    seen.add(port_name)

            problem = width_problem(width_text)
            if problem:
                errors.append(Issue(f"{row + 1}行目の{label}のビット幅{problem}",
                                    where, row, COL_WIDTH))

            if wire is not None and not wire.strip():
                shown = port_name or f"{row + 1}行目"
                warnings.append(Issue(f"{label} '{shown}' に Wire 名がありません(未接続)。",
                                      where, row, COL_WIRE))

    return errors, warnings
