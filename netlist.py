"""ブロック図のデータモデル。Qt に依存しない。

モジュール定義 (ポートの並び) とインスタンス (接続先) を分けて持つ。
同じモジュールをいくつ置いても定義は1つで、直せば全インスタンスに効く。

保存形式は2種類を読める。

  形式1 (旧): dict のリスト。サブモジュールが自分のポート定義を丸ごと持つ。
              同じモジュールを2つ置くと定義が2重になり、片方だけ直すとずれる。
  形式2 (新): dict。modules にポート定義、instances に接続だけを持つ。

読むときは両方受け付け、書くときは常に形式2にする。
"""

from __future__ import annotations

from dataclasses import dataclass, field

FORMAT_VERSION = 2


@dataclass
class Port:
    """モジュールのポート1本。どこに繋がるかは持たない。"""

    name: str
    width: int = 1


@dataclass
class Module:
    """モジュールの定義。インスタンス間で共有する。"""

    name: str
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)

    def ports(self):
        """(向き, Port) を入力・出力の順に返す。"""
        return ([("input", port) for port in self.inputs]
                + [("output", port) for port in self.outputs])

    def port_names(self):
        return [port.name for _, port in self.ports()]

    def signature(self):
        """定義が同じかどうかを比べるための形。"""
        return ([(p.name, p.width) for p in self.inputs],
                [(p.name, p.width) for p in self.outputs])


@dataclass
class Instance:
    """モジュールの実体。位置と接続先だけを持つ。"""

    module_name: str
    name: str
    x: float = 0.0
    y: float = 0.0
    connections: dict = field(default_factory=dict)  # ポート名 -> wire 名

    def wire_for(self, port_name):
        return (self.connections.get(port_name) or "").strip()


@dataclass
class TopPort:
    """トップモジュールの入出力ポート。名前がそのまま wire 名になる。"""

    name: str
    width: int = 1
    is_input: bool = True
    x: float = 0.0
    y: float = 0.0


@dataclass
class Design:
    name: str = "top"
    name_pos: tuple = (0.0, 0.0)
    inputs: list = field(default_factory=list)     # TopPort
    outputs: list = field(default_factory=list)    # TopPort
    modules: dict = field(default_factory=dict)    # モジュール名 -> Module
    instances: list = field(default_factory=list)
    wires_to_hide: list = field(default_factory=list)

    def module_for(self, instance):
        return self.modules.get(instance.module_name)

    def next_instance_name(self, module_name):
        """モジュールごとの連番でインスタンス名を作る。"""
        used = {inst.name for inst in self.instances}
        stem = f"u_{module_name.lower()}"
        index = 0
        while f"{stem}{index}" in used:
            index += 1
        return f"{stem}{index}"


# --------------------------------------------------------------------------
# 読み込み
# --------------------------------------------------------------------------

def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_width(value):
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def load(data):
    """保存データを (Design, 警告のリスト) にする。形式1と形式2の両方を読む。"""
    if isinstance(data, list):
        return _load_v1(data)
    if isinstance(data, dict):
        return _load_v2(data)
    raise ValueError("読めない形式です。")


def _sort_design(design):
    """図の見た目の順に並べ直す。

    保存データの並びは scene の内部順で不定。ポートは上から下、
    インスタンスは信号の流れに沿って左から右。
    """
    design.inputs.sort(key=lambda port: port.y)
    design.outputs.sort(key=lambda port: port.y)
    design.instances.sort(key=lambda inst: (inst.x, inst.y))
    return design


def _load_v2(data):
    design = Design()
    warnings = []

    design.name = str(data.get("module_name", "top")).strip() or "top"
    position = data.get("module_name_pos") or (0.0, 0.0)
    design.name_pos = (_to_float(position[0]), _to_float(position[1]))
    design.wires_to_hide = list(data.get("wires_to_hide", []))

    for entry in data.get("ports", []):
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        port = TopPort(name, _to_width(entry.get("width", 1)),
                       bool(entry.get("is_input", True)),
                       _to_float(entry.get("x")), _to_float(entry.get("y")))
        (design.inputs if port.is_input else design.outputs).append(port)

    for module_name, entry in (data.get("modules") or {}).items():
        design.modules[module_name] = Module(
            module_name,
            [Port(str(p["name"]), _to_width(p.get("width", 1)))
             for p in entry.get("inputs", [])],
            [Port(str(p["name"]), _to_width(p.get("width", 1)))
             for p in entry.get("outputs", [])])

    for entry in data.get("instances", []):
        module_name = str(entry.get("module", "")).strip()
        instance = Instance(
            module_name,
            str(entry.get("name", "")).strip(),
            _to_float(entry.get("x")), _to_float(entry.get("y")),
            {str(k): str(v) for k, v in (entry.get("connections") or {}).items()})
        if module_name not in design.modules:
            warnings.append(
                f"インスタンス '{instance.name}' のモジュール "
                f"'{module_name}' の定義がありません。")
        design.instances.append(instance)

    return _sort_design(design), warnings


def _v1_port(entry):
    """[名前, 幅] または [名前, 幅, wire名] を (Port, wire名) にする。

    SubmoduleDialog は Wire 名が空欄のとき2要素のまま返す。
    """
    if not entry:
        return None, ""
    name = str(entry[0]).strip()
    if not name:
        return None, ""
    width = _to_width(entry[1]) if len(entry) > 1 else 1
    wire = entry[2].strip() if len(entry) > 2 and isinstance(entry[2], str) else ""
    return Port(name, width), wire


def _load_v1(items_data):
    """旧形式。サブモジュールが持つ定義からモジュール表を起こす。"""
    design = Design()
    warnings = []

    for item in items_data:
        kind = item.get("type")

        if kind == "module_name":
            text = str(item.get("text", "")).strip()
            if text:
                design.name = text
            design.name_pos = (_to_float(item.get("x")), _to_float(item.get("y")))

        elif kind == "port":
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            port = TopPort(name, _to_width(item.get("width", 1)),
                           bool(item.get("is_input")),
                           _to_float(item.get("x")), _to_float(item.get("y")))
            (design.inputs if port.is_input else design.outputs).append(port)

        elif kind == "submodule":
            module_data = item.get("module_data") or {}
            module_name = str(module_data.get("module_name", "")).strip()

            inputs, outputs, connections = [], [], {}
            for key, bucket in (("inputs", inputs), ("outputs", outputs)):
                for entry in module_data.get(key, []):
                    port, wire = _v1_port(entry)
                    if port is None:
                        continue
                    bucket.append(port)
                    if wire:
                        connections[port.name] = wire

            module = Module(module_name, inputs, outputs)
            known = design.modules.get(module_name)
            if known is None:
                design.modules[module_name] = module
            elif known.signature() != module.signature():
                warnings.append(
                    f"モジュール '{module_name}' の定義がインスタンス間で"
                    "食い違っています。最初の定義を使います。")

            design.instances.append(Instance(
                module_name,
                str(module_data.get("instance_name", "")).strip(),
                _to_float(item.get("x")), _to_float(item.get("y")),
                connections))

        elif kind == "global":
            design.wires_to_hide = list(item.get("wires_to_hide", []))

    seen = set()
    for instance in design.instances:
        if instance.name in seen:
            warnings.append(f"インスタンス名 '{instance.name}' が重複しています。")
        seen.add(instance.name)

    return _sort_design(design), warnings


# --------------------------------------------------------------------------
# 書き出し
# --------------------------------------------------------------------------

def dump(design):
    """形式2の dict にする。"""
    return {
        "format": FORMAT_VERSION,
        "module_name": design.name,
        "module_name_pos": [design.name_pos[0], design.name_pos[1]],
        "ports": [
            {"name": port.name, "width": port.width,
             "is_input": port.is_input, "x": port.x, "y": port.y}
            for port in design.inputs + design.outputs
        ],
        "modules": {
            name: {
                "inputs": [{"name": p.name, "width": p.width} for p in module.inputs],
                "outputs": [{"name": p.name, "width": p.width} for p in module.outputs],
            }
            for name, module in design.modules.items()
        },
        "instances": [
            {"module": inst.module_name, "name": inst.name,
             "x": inst.x, "y": inst.y,
             "connections": dict(inst.connections)}
            for inst in design.instances
        ],
        "wires_to_hide": list(design.wires_to_hide),
    }
