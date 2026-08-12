"""ブロック図データから Verilog を生成する。

入力は blox2rtl.py の saveDiagram が書き出すのと同じ形式 (dict のリスト)、
出力は Verilog のソース文字列。

このモジュールは Qt に依存しない。GUI を起動せずにテストできるように
意図的に分離してある。単体でも使える:

    python verilog.py diagram.json out.v
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field


class GenerationError(Exception):
    """Verilog を生成できないときに送出する。"""


@dataclass
class Port:
    name: str
    width: int = 1
    wire: str = ""  # サブモジュールのポートが接続される wire 名


@dataclass
class Instance:
    module_name: str
    instance_name: str
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)


@dataclass
class Design:
    module_name: str = "top"
    inputs: list = field(default_factory=list)   # トップの入力ポート
    outputs: list = field(default_factory=list)  # トップの出力ポート
    instances: list = field(default_factory=list)


# --------------------------------------------------------------------------
# 読み込み
# --------------------------------------------------------------------------

def _to_width(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def _to_port(entry):
    """[name, width] または [name, width, wire] を Port にする。

    SubmoduleDialog は Wire 名が空のとき 2 要素のまま返すので、両方を許す。
    """
    if not entry:
        return None
    name = str(entry[0]).strip()
    if not name:
        return None
    width = _to_width(entry[1]) if len(entry) > 1 else 1
    wire = ""
    if len(entry) > 2 and isinstance(entry[2], str):
        wire = entry[2].strip()
    return Port(name, width, wire)


def parse_diagram(items_data):
    """saveDiagram が書き出した形式を Design に変換する。"""
    design = Design()
    inputs, outputs, instances = [], [], []

    for item in items_data:
        kind = item.get("type")

        if kind == "module_name":
            text = str(item.get("text", "")).strip()
            if text:
                design.module_name = text

        elif kind == "port":
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            port = Port(name, _to_width(item.get("width", 1)))
            y = _to_float(item.get("y"))
            (inputs if item.get("is_input") else outputs).append((y, port))

        elif kind == "submodule":
            module_data = item.get("module_data") or {}
            inst = Instance(
                module_name=str(module_data.get("module_name", "")).strip(),
                instance_name=str(module_data.get("instance_name", "")).strip(),
                inputs=[p for p in map(_to_port, module_data.get("inputs", [])) if p],
                outputs=[p for p in map(_to_port, module_data.get("outputs", [])) if p],
            )
            instances.append((_to_float(item.get("x")), _to_float(item.get("y")), inst))

    # JSON 内の並びは scene の内部順で不定なので、図の見た目の順に並べ直す。
    # ポートは上から下、インスタンスは信号の流れに沿って左から右へ。
    inputs.sort(key=lambda t: t[0])
    outputs.sort(key=lambda t: t[0])
    instances.sort(key=lambda t: (t[0], t[1]))

    design.inputs = [port for _, port in inputs]
    design.outputs = [port for _, port in outputs]
    design.instances = [inst for _, _, inst in instances]
    return design


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# 検査
# --------------------------------------------------------------------------

def _validate(design):
    if not design.inputs and not design.outputs and not design.instances:
        raise GenerationError("図が空です。")

    if not design.module_name:
        raise GenerationError("モジュール名が空です。")

    seen = {}
    for inst in design.instances:
        if not inst.module_name:
            raise GenerationError("モジュール名が空のサブモジュールがあります。")
        if not inst.instance_name:
            raise GenerationError(
                f"'{inst.module_name}' のインスタンス名が空です。"
            )
        if inst.instance_name in seen:
            raise GenerationError(
                f"インスタンス名 '{inst.instance_name}' が重複しています。"
            )
        seen[inst.instance_name] = inst


def _collect_wires(design, warnings):
    """宣言が必要な wire を (名前, ビット幅) の順序付きリストで返す。"""
    top_ports = {p.name for p in design.inputs} | {p.name for p in design.outputs}
    widths, drivers, loads, order = {}, {}, {}, []

    def use(wire, width, where, is_driver):
        if wire not in widths:
            widths[wire] = width
            order.append(wire)
        elif widths[wire] != width:
            warnings.append(
                f"wire '{wire}' のビット幅が一致しません "
                f"({widths[wire]} と {width})。広いほうを採用します"
            )
            widths[wire] = max(widths[wire], width)
        (drivers if is_driver else loads).setdefault(wire, []).append(where)

    # トップから見ると、入力ポートが駆動元・出力ポートが受け側になる
    for port in design.inputs:
        use(port.name, port.width, f"{design.module_name}.{port.name}", True)
    for port in design.outputs:
        use(port.name, port.width, f"{design.module_name}.{port.name}", False)

    for inst in design.instances:
        for port in inst.inputs:
            if not port.wire:
                warnings.append(f"{inst.instance_name}.{port.name} が未接続です")
                continue
            use(port.wire, port.width, f"{inst.instance_name}.{port.name}", False)
        for port in inst.outputs:
            if not port.wire:
                warnings.append(f"{inst.instance_name}.{port.name} が未接続です")
                continue
            use(port.wire, port.width, f"{inst.instance_name}.{port.name}", True)

    for wire in order:
        wire_drivers = drivers.get(wire, [])
        if not wire_drivers:
            warnings.append(f"wire '{wire}' に駆動元がありません")
        elif len(wire_drivers) > 1:
            warnings.append(
                f"wire '{wire}' が複数から駆動されています: "
                + ", ".join(wire_drivers)
            )
        if not loads.get(wire):
            warnings.append(f"wire '{wire}' がどこにも接続されていません")

    # トップのポート名と同じ wire は、ポート宣言が兼ねるので宣言しない
    return [(wire, widths[wire]) for wire in order if wire not in top_ports]


# --------------------------------------------------------------------------
# 出力
# --------------------------------------------------------------------------

INDENT = "    "


def _bit_range(width):
    return f"[{width - 1}:0]" if width > 1 else ""


def _port_declarations(design):
    entries = [("input", p) for p in design.inputs]
    entries += [("output", p) for p in design.outputs]
    if not entries:
        return []

    range_width = max(len(_bit_range(p.width)) for _, p in entries)
    lines = []
    for direction, port in entries:
        decl = f"{direction:<6} wire"
        if range_width:
            decl += " " + _bit_range(port.width).ljust(range_width)
        lines.append(f"{decl} {port.name}")
    return lines


def _wire_declarations(wires):
    if not wires:
        return []

    range_width = max(len(_bit_range(width)) for _, width in wires)
    lines = []
    for name, width in wires:
        decl = "wire"
        if range_width:
            decl += " " + _bit_range(width).ljust(range_width)
        lines.append(f"{decl} {name};")
    return lines


def _instance_lines(inst):
    connections = [(p.name, p.wire) for p in inst.inputs]
    connections += [(p.name, p.wire) for p in inst.outputs]

    lines = [f"{inst.module_name} {inst.instance_name} ("]
    if connections:
        name_width = max(len(name) for name, _ in connections)
        last = len(connections) - 1
        for i, (name, wire) in enumerate(connections):
            comma = "," if i < last else ""
            lines.append(f"{INDENT}.{name.ljust(name_width)} ({wire}){comma}")
    lines.append(");")
    return lines


def _emit(design, wires):
    lines = ["// Generated by blox2rtl.", ""]

    port_lines = _port_declarations(design)
    if port_lines:
        lines.append(f"module {design.module_name} (")
        last = len(port_lines) - 1
        for i, decl in enumerate(port_lines):
            comma = "," if i < last else ""
            lines.append(f"{INDENT}{decl}{comma}")
        lines.append(");")
    else:
        lines.append(f"module {design.module_name};")
    lines.append("")

    for decl in _wire_declarations(wires):
        lines.append(f"{INDENT}{decl}")
    if wires:
        lines.append("")

    for inst in design.instances:
        for line in _instance_lines(inst):
            lines.append(f"{INDENT}{line}")
        lines.append("")

    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def generate(items_data):
    """ブロック図データから (Verilog 文字列, 警告のリスト) を返す。

    構造上 Verilog にできない場合は GenerationError を送出する。
    警告は生成を止めない種類の指摘 (未接続、駆動元なし、ビット幅不一致など)。
    """
    design = parse_diagram(items_data)
    _validate(design)
    warnings = []
    wires = _collect_wires(design, warnings)
    return _emit(design, wires), warnings


# --------------------------------------------------------------------------
# コマンドライン
# --------------------------------------------------------------------------

def main(argv):
    if len(argv) < 2:
        print("usage: python verilog.py <diagram.json> [out.v]", file=sys.stderr)
        return 2

    with open(argv[1], encoding="utf-8") as handle:
        items_data = json.load(handle)

    try:
        text, warnings = generate(items_data)
    except GenerationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if len(argv) > 2:
        with open(argv[2], "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
