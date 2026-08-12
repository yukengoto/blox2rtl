"""netlist.py のテスト。Qt を使わない。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import netlist  # noqa: E402
import verilog  # noqa: E402


def module_name(text, x=0, y=0):
    return {"type": "module_name", "text": text, "x": x, "y": y}


def port(name, width=1, is_input=True, y=0):
    return {"type": "port", "name": name, "width": width,
            "is_input": is_input, "x": 0, "y": y}


def submodule(module, instance, inputs=(), outputs=(), x=0, y=0):
    return {
        "type": "submodule", "x": x, "y": y,
        "module_data": {
            "module_name": module, "instance_name": instance,
            "inputs": [list(entry) for entry in inputs],
            "outputs": [list(entry) for entry in outputs],
        },
    }


TWO_INSTANCES = [
    module_name("top"),
    port("din", 8, is_input=True),
    port("dout", 8, is_input=False),
    submodule("adder", "u_add0",
              inputs=[("a", 8, "din"), ("b", 8, "mid")],
              outputs=[("y", 8, "sum")], x=100),
    submodule("adder", "u_add1",
              inputs=[("a", 8, "sum"), ("b", 8, "mid")],
              outputs=[("y", 8, "dout")], x=300),
    submodule("gen", "u_gen", outputs=[("q", 8, "mid")], x=0),
]


class MigrationTest(unittest.TestCase):
    """旧形式は、同じモジュールを置くたびに定義を持っていた。"""

    def test_same_module_becomes_one_definition(self):
        design, warnings = netlist.load(TWO_INSTANCES)
        self.assertEqual(warnings, [])
        self.assertEqual(sorted(design.modules), ["adder", "gen"])
        self.assertEqual(len(design.instances), 3)

    def test_definition_holds_the_ports(self):
        design, _ = netlist.load(TWO_INSTANCES)
        adder = design.modules["adder"]
        self.assertEqual([(p.name, p.width) for p in adder.inputs],
                         [("a", 8), ("b", 8)])
        self.assertEqual([(p.name, p.width) for p in adder.outputs],
                         [("y", 8)])

    def test_connections_stay_per_instance(self):
        design, _ = netlist.load(TWO_INSTANCES)
        by_name = {inst.name: inst for inst in design.instances}
        self.assertEqual(by_name["u_add0"].connections,
                         {"a": "din", "b": "mid", "y": "sum"})
        self.assertEqual(by_name["u_add1"].connections,
                         {"a": "sum", "b": "mid", "y": "dout"})

    def test_conflicting_definitions_are_reported(self):
        """旧形式では片方だけ直すと静かにずれた。移行時に気づけるようにする。"""
        diagram = [
            module_name("top"),
            submodule("adder", "u_a", inputs=[("a", 8, "n0")], x=0),
            submodule("adder", "u_b", inputs=[("a", 4, "n1")], x=10),
        ]
        design, warnings = netlist.load(diagram)
        self.assertTrue(any("食い違" in w for w in warnings), warnings)
        # 最初の定義を採用する
        self.assertEqual(design.modules["adder"].inputs[0].width, 8)

    def test_duplicate_instance_names_are_reported(self):
        diagram = [
            module_name("top"),
            submodule("a", "u_dup", x=0),
            submodule("b", "u_dup", x=10),
        ]
        _, warnings = netlist.load(diagram)
        self.assertTrue(any("重複" in w for w in warnings), warnings)

    def test_port_entry_without_wire_name(self):
        diagram = [module_name("top"), submodule("blk", "u_blk",
                                                 inputs=[("a", 1)])]
        design, _ = netlist.load(diagram)
        self.assertEqual(design.instances[0].connections, {})
        self.assertEqual(design.instances[0].wire_for("a"), "")


class RoundTripTest(unittest.TestCase):
    def test_dump_then_load_keeps_the_design(self):
        original, _ = netlist.load(TWO_INSTANCES)
        again, warnings = netlist.load(netlist.dump(original))

        self.assertEqual(warnings, [])
        self.assertEqual(again.name, original.name)
        self.assertEqual([p.name for p in again.inputs],
                         [p.name for p in original.inputs])
        self.assertEqual(sorted(again.modules), sorted(original.modules))
        self.assertEqual([i.name for i in again.instances],
                         [i.name for i in original.instances])
        self.assertEqual([i.connections for i in again.instances],
                         [i.connections for i in original.instances])

    def test_the_new_format_produces_the_same_verilog(self):
        """移行しても出力が変わらないこと。"""
        from_old, _ = verilog.generate(TWO_INSTANCES)
        design, _ = netlist.load(TWO_INSTANCES)
        from_new, _ = verilog.generate(netlist.dump(design))
        self.assertEqual(from_old, from_new)

    def test_dump_is_json_safe(self):
        import json
        design, _ = netlist.load(TWO_INSTANCES)
        text = json.dumps(netlist.dump(design))
        self.assertEqual(json.loads(text)["format"], netlist.FORMAT_VERSION)


class LoadV2Test(unittest.TestCase):
    def test_missing_module_definition_is_reported(self):
        data = {
            "format": 2, "module_name": "top", "ports": [], "modules": {},
            "instances": [{"module": "ghost", "name": "u_x",
                           "x": 0, "y": 0, "connections": {}}],
        }
        _, warnings = netlist.load(data)
        self.assertTrue(any("定義がありません" in w for w in warnings), warnings)

    def test_unreadable_input(self):
        with self.assertRaises(ValueError):
            netlist.load("not a diagram")


class InstanceNameTest(unittest.TestCase):
    def test_numbers_per_module(self):
        design, _ = netlist.load(TWO_INSTANCES)
        self.assertEqual(design.next_instance_name("adder"), "u_adder0")

    def test_skips_names_already_used(self):
        design, _ = netlist.load(TWO_INSTANCES)
        design.instances.append(netlist.Instance("adder", "u_adder0"))
        design.instances.append(netlist.Instance("adder", "u_adder1"))
        self.assertEqual(design.next_instance_name("adder"), "u_adder2")


if __name__ == "__main__":
    unittest.main()
