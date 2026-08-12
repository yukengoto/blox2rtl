"""GUI 側 (blox2rtl.py) の回帰テスト。

Qt が要るので offscreen で動かす。PySide6 が無い環境ではスキップするので、
テスト全体は標準ライブラリだけでも回せる。

    python -m unittest discover -s tests
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtWidgets
    import blox2rtl
    import netlist
except ImportError:  # PySide6 が無い環境
    QtWidgets = None
    blox2rtl = None

_app = None


def setUpModule():
    global _app
    if QtWidgets is not None:
        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def make_window(modules=None):
    window = blox2rtl.MainWindow()
    for module in (modules or []):
        window.design.modules[module.name] = module
    return window


def add_block(window, instance, x=0, y=0):
    block = blox2rtl.BlockItem(0, 0, 150, 50, instance=instance, main_window=window)
    block.setPos(x, y)
    window.scene.addItem(block)
    return block


def blk():
    """定義を書き換えるテストがあるので、毎回作り直す。"""
    return netlist.Module("blk",
                          [netlist.Port("a", 4), netlist.Port("b", 1)],
                          [netlist.Port("y", 1)])


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class BlockItemTest(unittest.TestCase):
    """ブロックは定義を持たず、design.modules から引く。"""

    def test_ports_come_from_the_shared_definition(self):
        window = make_window([blk()])
        block = add_block(window, netlist.Instance("blk", "u_blk"))
        self.assertEqual([p.name for _, p in block.ports()], ["a", "b", "y"])

    def test_editing_the_definition_reaches_every_instance(self):
        window = make_window([blk()])
        first = add_block(window, netlist.Instance("blk", "u0"))
        second = add_block(window, netlist.Instance("blk", "u1"), x=400)

        window.design.modules["blk"].inputs.append(netlist.Port("cin", 1))

        for block in (first, second):
            self.assertIn("cin", [p.name for _, p in block.ports()])

    def test_unconnected_port_has_an_empty_wire(self):
        window = make_window([blk()])
        block = add_block(window, netlist.Instance("blk", "u_blk",
                                                   connections={"a": "net"}))
        self.assertEqual([name for name, _, _ in block.sink_wires()], ["net", ""])
        self.assertEqual([name for name, _, _ in block.source_wires()], [""])

    def test_a_missing_definition_does_not_crash(self):
        """定義が見つからないインスタンスでも描画・結線が通ること。"""
        window = make_window()
        block = add_block(window, netlist.Instance("ghost", "u_ghost"))
        self.assertIsNone(block.module())
        self.assertEqual(block.ports(), [])
        self.assertEqual(block.sink_wires(), [])
        window.updateWires()   # 落ちないこと


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class UpdateWiresTest(unittest.TestCase):
    def make_pair(self, left_wire, right_wire):
        window = make_window([
            netlist.Module("a", [], [netlist.Port("y", 1)]),
            netlist.Module("b", [netlist.Port("d", 1)], []),
        ])
        add_block(window, netlist.Instance("a", "u_a", connections=left_wire))
        add_block(window, netlist.Instance("b", "u_b", connections=right_wire),
                  x=400)
        window.updateWires()
        return window

    def wires(self, window):
        return [i for i in window.scene.items()
                if isinstance(i, blox2rtl.WireItem)]

    def test_blank_wire_names_are_not_connected(self):
        window = self.make_pair({}, {})
        self.assertEqual(self.wires(window), [])

    def test_named_wires_are_connected(self):
        window = self.make_pair({"y": "net"}, {"d": "net"})
        wires = self.wires(window)
        self.assertEqual(len(wires), 1)
        self.assertEqual(wires[0].name, "net")


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class PortOrderTest(unittest.TestCase):
    """scene.items() は z 順で返すので、そのまま使うと並びが逆さまになる。"""

    def make(self):
        window = blox2rtl.MainWindow()
        for i, name in enumerate(["clk", "rst", "din", "en"]):
            port = blox2rtl.PortItem(0, 0, name, 1, is_input=True,
                                     main_window=window)
            port.setPos(0, i * 50)
            window.scene.addItem(port)
        return window

    def test_scene_order_is_not_the_visual_order(self):
        window = self.make()
        raw = [item.name for item in window.scene.items()
               if isinstance(item, blox2rtl.PortItem)]
        self.assertNotEqual(raw, ["clk", "rst", "din", "en"])

    def test_ports_are_returned_top_to_bottom(self):
        window = self.make()
        self.assertEqual([item.name for item in window.ports(is_input=True)],
                         ["clk", "rst", "din", "en"])

    def test_order_survives_a_round_trip(self):
        window = self.make()
        design = window.buildDesign()
        self.assertEqual([p.name for p in design.inputs],
                         ["clk", "rst", "din", "en"])

        reopened = blox2rtl.MainWindow()
        reopened.loadDesign(netlist.load(netlist.dump(design))[0])
        self.assertEqual([item.name for item in reopened.ports(is_input=True)],
                         ["clk", "rst", "din", "en"])


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class PlacementTest(unittest.TestCase):
    def test_new_block_lands_near_the_existing_ones(self):
        window = make_window([blk()])
        add_block(window, netlist.Instance("blk", "u0"), x=200, y=200)
        window.updateWires()

        content = window.contentRect()
        x, y = window.freePosition(150, 100)

        self.assertGreaterEqual(x, content.left() - blox2rtl.NEW_ITEM_STEP)
        self.assertLessEqual(x, content.right() + 150)
        self.assertGreaterEqual(y, content.top() - blox2rtl.NEW_ITEM_STEP)

    def test_new_block_does_not_land_on_an_existing_one(self):
        window = make_window([blk()])
        add_block(window, netlist.Instance("blk", "u0"), x=0, y=0)
        window.updateWires()

        x, y = window.freePosition(150, 100)
        area = QtCore.QRectF(x, y, 150, 100)
        overlapping = [item for item in window.scene.items(
            area, QtCore.Qt.IntersectsItemShape)
            if isinstance(item, blox2rtl.BlockItem)]
        self.assertEqual(overlapping, [])

    def test_free_position_is_on_the_grid(self):
        window = make_window([blk()])
        add_block(window, netlist.Instance("blk", "u0"), x=37, y=63)
        x, y = window.freePosition(150, 100)
        self.assertEqual(x % blox2rtl.GRID_SIZE, 0)
        self.assertEqual(y % blox2rtl.GRID_SIZE, 0)

    def test_port_columns_follow_the_blocks(self):
        """固定値だと、図が小さいときに本体から遠く離れた場所に置かれる。"""
        window = make_window([blk()])
        add_block(window, netlist.Instance("blk", "u0"), x=300, y=100)

        left, right = window.portColumns()
        body = window.blocks()[0].mapRectToScene(window.blocks()[0].rect())
        self.assertLess(left, body.left())
        self.assertGreater(right, body.right())
        self.assertLess(body.left() - left, 400)
        self.assertLess(right - body.right(), 400)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class SelectionTest(unittest.TestCase):
    def make(self):
        window = make_window([blk()])
        first = add_block(window, netlist.Instance("blk", "u0"), x=0, y=0)
        second = add_block(window, netlist.Instance("blk", "u1"), x=400, y=0)
        window.updateWires()
        return window, first, second

    def test_rubber_band_uses_the_shape_not_the_bounding_rect(self):
        """BlockItem.boundingRect() は左右へ 100 広げてあるので、

        BoundingRect 判定にすると離れたブロックまで掴んでしまう。
        """
        window, _, _ = self.make()
        self.assertEqual(window.view.dragMode(),
                         QtWidgets.QGraphicsView.RubberBandDrag)
        self.assertEqual(window.view.rubberBandSelectionMode(),
                         blox2rtl.QtCore.Qt.IntersectsItemShape)

    def test_wires_are_not_selectable(self):
        window = make_window([
            netlist.Module("a", [], [netlist.Port("y", 1)]),
            netlist.Module("b", [netlist.Port("d", 1)], []),
        ])
        add_block(window, netlist.Instance("a", "u_a", connections={"y": "net"}))
        add_block(window, netlist.Instance("b", "u_b", connections={"d": "net"}),
                  x=400)
        window.updateWires()

        wires = [i for i in window.scene.items()
                 if isinstance(i, blox2rtl.WireItem)]
        self.assertTrue(wires)
        for wire in wires:
            self.assertFalse(wire.flags()
                             & QtWidgets.QGraphicsItem.ItemIsSelectable)

    def test_every_selected_item_snaps_to_the_grid(self):
        """ドラッグを受け取るのは1個だけ。残りも揃えること。"""
        window, first, second = self.make()
        first.setSelected(True)
        second.setSelected(True)

        first.setPos(37, 63)
        second.setPos(412, 9)
        blox2rtl.snap_selection(first)

        for block in (first, second):
            self.assertEqual(block.x() % blox2rtl.GRID_SIZE, 0)
            self.assertEqual(block.y() % blox2rtl.GRID_SIZE, 0)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class DuplicateTest(unittest.TestCase):
    def test_duplicate_shares_the_module_and_gets_a_new_name(self):
        window = make_window([blk()])
        block = add_block(window, netlist.Instance("blk", "u_blk",
                                                   connections={"a": "net"}))
        block.setSelected(True)
        window.duplicateSelectedBlocks()

        blocks = window.blocks()
        self.assertEqual(len(blocks), 2)
        names = sorted(b.instance.name for b in blocks)
        self.assertEqual(names[0], "u_blk")
        self.assertNotEqual(names[1], "u_blk")
        # 定義は共有、接続は引き継がない
        copy = [b for b in blocks if b.instance.name != "u_blk"][0]
        self.assertEqual(copy.instance.module_name, "blk")
        self.assertEqual(copy.instance.connections, {})


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class SceneRectTest(unittest.TestCase):
    def make(self):
        window = make_window([netlist.Module("a", [], [netlist.Port("y", 1)])])
        block = add_block(window, netlist.Instance("a", "u_a",
                                                   connections={"y": "net"}))
        window.updateWires()
        return window, block

    def test_canvas_shrinks_when_items_move_back(self):
        """指定しないと sceneRect は広がる一方で縮まない。"""
        window, block = self.make()

        block.setPos(2000, 1500)
        window.updateWires()
        widened = window.scene.sceneRect()

        block.setPos(0, 0)
        window.updateWires()
        shrunk = window.scene.sceneRect()

        self.assertLess(shrunk.width(), widened.width())
        self.assertLess(shrunk.height(), widened.height())

    def test_canvas_covers_the_items(self):
        window, _ = self.make()
        self.assertTrue(
            window.scene.sceneRect().contains(window.scene.itemsBoundingRect()))

    def test_canvas_is_aligned_to_the_grid(self):
        window, block = self.make()
        block.setPos(37, 63)
        window.updateWires()
        rect = window.scene.sceneRect()
        for value in (rect.left(), rect.top(), rect.right(), rect.bottom()):
            self.assertEqual(value % blox2rtl.GRID_SIZE, 0, value)

    def test_grid_is_not_a_scene_item(self):
        """アイテムにすると itemsBoundingRect が自分自身で広がり続ける。"""
        window, _ = self.make()
        kinds = {type(item).__name__ for item in window.scene.items()}
        self.assertNotIn("QGraphicsLineItem", kinds)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class SaveFileTest(unittest.TestCase):
    def make(self):
        window = make_window([blk()])
        window.module_name_item.setPlainText("counter")
        add_block(window, netlist.Instance("blk", "u_blk",
                                           connections={"a": "net"}), x=100)
        return window

    def test_starts_with_no_file(self):
        window = blox2rtl.MainWindow()
        self.assertIsNone(window.current_file_path)
        self.assertIn("未保存", window.windowTitle())

    def test_saves_in_the_new_format(self):
        window = self.make()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "diagram.json")
            window.writeDiagram(path)

            self.assertEqual(window.current_file_path, path)
            self.assertIn("diagram.json", window.windowTitle())

            with open(path, encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertEqual(saved["format"], netlist.FORMAT_VERSION)
            self.assertEqual(saved["module_name"], "counter")
            self.assertIn("blk", saved["modules"])
            self.assertEqual(saved["instances"][0]["connections"], {"a": "net"})

    def test_round_trip_through_a_file(self):
        window = self.make()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "diagram.json")
            window.writeDiagram(path)

            with open(path, encoding="utf-8") as handle:
                design, warnings = netlist.load(json.load(handle))

        self.assertEqual(warnings, [])
        reopened = blox2rtl.MainWindow()
        reopened.loadDesign(design)
        blocks = reopened.blocks()
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].instance.name, "u_blk")
        self.assertEqual([p.name for _, p in blocks[0].ports()], ["a", "b", "y"])

    def test_overwrite_uses_the_remembered_path(self):
        window = self.make()
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "diagram.json")
            window.writeDiagram(path)

            window.module_name_item.setPlainText("changed")
            window.saveDiagram()   # ダイアログを出さずに上書きされること

            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["module_name"], "changed")

    def test_can_open_the_old_format(self):
        old = [
            {"type": "module_name", "text": "legacy", "x": 0, "y": 0},
            {"type": "submodule", "x": 10, "y": 20, "module_data": {
                "module_name": "adder", "instance_name": "u_add",
                "inputs": [["a", 8, "din"]], "outputs": [["y", 8, "dout"]]}},
        ]
        design, _ = netlist.load(old)
        window = blox2rtl.MainWindow()
        window.loadDesign(design)

        self.assertEqual(window.module_name_item.toPlainText(), "legacy")
        self.assertIn("adder", window.design.modules)
        block = window.blocks()[0]
        self.assertEqual(block.instance.wire_for("a"), "din")


if __name__ == "__main__":
    unittest.main()
