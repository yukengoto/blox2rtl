"""GUI 側 (blox2rtl.py) の回帰テスト。

Qt が要るので offscreen で動かす。PySide6 が無い環境ではスキップするので、
テスト全体は標準ライブラリだけでも回せる。

    python -m unittest discover -s tests
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtWidgets
    import blox2rtl
except ImportError:  # PySide6 が無い環境
    QtWidgets = None
    blox2rtl = None

_app = None


def setUpModule():
    global _app
    if QtWidgets is not None:
        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class PortFieldsTest(unittest.TestCase):
    """Wire 名が空欄のとき、SubmoduleDialog は2要素のまま返す。"""

    def test_three_fields(self):
        self.assertEqual(blox2rtl.port_fields(("a", 8, "net")), ("a", 8, "net"))

    def test_two_fields(self):
        self.assertEqual(blox2rtl.port_fields(("a", 8)), ("a", 8, ""))

    def test_one_field(self):
        self.assertEqual(blox2rtl.port_fields(("a",)), ("a", 1, ""))


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class BlockItemTest(unittest.TestCase):
    def make_block(self):
        return blox2rtl.BlockItem(0, 0, 150, 50, module_data={
            "module_name": "blk",
            "instance_name": "u_blk",
            "inputs": [("a", 4, "net"), ("b", 1)],     # b は Wire 名が空欄
            "outputs": [("y", 1)],                     # y も空欄
        })

    def test_sink_wires_accepts_two_field_entry(self):
        """2要素のポート定義で ValueError にならないこと。"""
        wires = self.make_block().sink_wires()
        self.assertEqual([name for name, _, _ in wires], ["net", ""])

    def test_source_wires_accepts_two_field_entry(self):
        wires = self.make_block().source_wires()
        self.assertEqual([name for name, _, _ in wires], [""])


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class UpdateWiresTest(unittest.TestCase):
    def test_blank_wire_names_are_not_connected(self):
        """Wire 名が空欄のポート同士を同名として結線しないこと。"""
        window = blox2rtl.MainWindow()

        left = blox2rtl.BlockItem(0, 0, 150, 50, main_window=window, module_data={
            "module_name": "a", "instance_name": "u_a",
            "inputs": [], "outputs": [("y", 1)]})       # Wire 名なし
        left.setPos(0, 0)
        window.scene.addItem(left)

        right = blox2rtl.BlockItem(0, 0, 150, 50, main_window=window, module_data={
            "module_name": "b", "instance_name": "u_b",
            "inputs": [("d", 1)], "outputs": []})       # Wire 名なし
        right.setPos(400, 0)
        window.scene.addItem(right)

        window.updateWires()

        wires = [i for i in window.scene.items() if isinstance(i, blox2rtl.WireItem)]
        self.assertEqual(wires, [])

    def test_named_wires_are_connected(self):
        """名前が付いていれば従来どおり結線されること。"""
        window = blox2rtl.MainWindow()

        left = blox2rtl.BlockItem(0, 0, 150, 50, main_window=window, module_data={
            "module_name": "a", "instance_name": "u_a",
            "inputs": [], "outputs": [("y", 1, "net")]})
        left.setPos(0, 0)
        window.scene.addItem(left)

        right = blox2rtl.BlockItem(0, 0, 150, 50, main_window=window, module_data={
            "module_name": "b", "instance_name": "u_b",
            "inputs": [("d", 1, "net")], "outputs": []})
        right.setPos(400, 0)
        window.scene.addItem(right)

        window.updateWires()

        wires = [i for i in window.scene.items() if isinstance(i, blox2rtl.WireItem)]
        self.assertEqual(len(wires), 1)
        self.assertEqual(wires[0].name, "net")


if __name__ == "__main__":
    unittest.main()
