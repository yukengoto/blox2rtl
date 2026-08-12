"""ダイアログのキー操作と、閉じるときの検証のテスト。

Qt が要るので offscreen で動かす。PySide6 が無い環境ではスキップする。
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtWidgets, QtTest
    import ModuleDialog as dialogs
    import netlist
    import validate
except ImportError:  # PySide6 が無い環境
    QtWidgets = None

_app = None


def setUpModule():
    global _app
    if QtWidgets is not None:
        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def flush():
    QtWidgets.QApplication.processEvents()


def make_design():
    design = netlist.Design(name="top")
    design.modules["blk"] = netlist.Module(
        "blk", [netlist.Port("a", 4), netlist.Port("b", 1)],
        [netlist.Port("y", 1)])
    return design


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class ShortcutTest(unittest.TestCase):
    def make(self):
        return dialogs.ModuleDialog(module_data={
            "module_name": "top",
            "inputs": [("a", 1, False)],
            "outputs": [("y", 1)],
        })

    def test_ctrl_i_adds_an_input_row(self):
        dlg = self.make()
        dlg.show()
        dlg.activateWindow()
        flush()
        dlg.module_name_edit.setFocus()
        before = dlg.input_table.rowCount()
        QtTest.QTest.keyClick(dlg.module_name_edit, QtCore.Qt.Key_I,
                              QtCore.Qt.ControlModifier)
        flush()
        self.assertEqual(dlg.input_table.rowCount(), before + 1)

    def test_ctrl_o_adds_an_output_row(self):
        dlg = self.make()
        dlg.show()
        dlg.activateWindow()
        flush()
        dlg.module_name_edit.setFocus()
        before = dlg.output_table.rowCount()
        QtTest.QTest.keyClick(dlg.module_name_edit, QtCore.Qt.Key_O,
                              QtCore.Qt.ControlModifier)
        flush()
        self.assertEqual(dlg.output_table.rowCount(), before + 1)

    def test_ctrl_i_while_editing_adds_only_one_row(self):
        """編集中に押しても行が2つ増えないこと。"""
        dlg = self.make()
        dlg.show()
        dlg.activateWindow()
        flush()
        dlg.add_input_port()   # ここでセルの編集が始まる
        flush()
        before = dlg.input_table.rowCount()
        QtTest.QTest.keyClick(dlg.input_table, QtCore.Qt.Key_I,
                              QtCore.Qt.ControlModifier)
        flush()
        flush()
        self.assertEqual(dlg.input_table.rowCount(), before + 1)

    def test_new_row_defaults_bit_width_to_one(self):
        """空のままだと get_table_data() がその行を落としてしまう。"""
        dlg = self.make()
        dlg.add_input_port()
        row = dlg.input_table.currentRow()
        self.assertEqual(dlg.input_table.item(row, validate.COL_WIDTH).text(), "1")

    def test_new_row_goes_below_the_current_one(self):
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top",
            "inputs": [("a", 1, False), ("b", 1, False)],
            "outputs": [],
        })
        dlg.input_table.setCurrentCell(0, 0)
        dlg.add_input_port()
        self.assertEqual(dlg.input_table.currentRow(), 1)
        self.assertEqual(dlg.input_table.item(2, validate.COL_NAME).text(), "b")


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class RowAppendTest(unittest.TestCase):
    def make(self):
        return dialogs.ModuleDefDialog(module=netlist.Module(
            "blk", [netlist.Port("a", 1)], []))

    def test_tab_at_the_last_cell_appends_a_row(self):
        dlg = self.make()
        dlg.show()
        table = dlg.input_table
        table.setFocus()
        table.setCurrentCell(0, table.columnCount() - 1)
        before = table.rowCount()
        table.moveCursor(QtWidgets.QAbstractItemView.CursorAction.MoveNext,
                         QtCore.Qt.NoModifier)
        flush()
        self.assertEqual(table.rowCount(), before + 1)

    def test_tab_in_the_middle_does_not_append(self):
        dlg = self.make()
        dlg.show()
        table = dlg.input_table
        table.setCurrentCell(0, 0)
        before = table.rowCount()
        table.moveCursor(QtWidgets.QAbstractItemView.CursorAction.MoveNext,
                         QtCore.Qt.NoModifier)
        flush()
        self.assertEqual(table.rowCount(), before)

    def test_enter_stays_on_the_same_cell(self):
        """Enter は編集終了。行を送るのは Tab の役目。"""
        dlg = dialogs.ModuleDefDialog(module=netlist.Module(
            "blk", [netlist.Port("a", 1), netlist.Port("b", 1)], []))
        dlg.show()
        table = dlg.input_table
        table.setCurrentCell(0, 0)
        before = table.rowCount()
        QtTest.QTest.keyClick(table, QtCore.Qt.Key_Return)
        flush()
        self.assertEqual(table.currentRow(), 0)
        self.assertEqual(table.rowCount(), before)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class EnterDoesNotCloseTest(unittest.TestCase):
    def test_enter_in_the_name_field_keeps_the_dialog_open(self):
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [("a", 1, False)], "outputs": [],
        })
        dlg.show()
        dlg.module_name_edit.setFocus()
        QtTest.QTest.keyClick(dlg.module_name_edit, QtCore.Qt.Key_Return)
        flush()
        self.assertTrue(dlg.isVisible())

    def test_no_button_is_default(self):
        for dlg in (dialogs.ModuleDialog(module_data={
                        "module_name": "top", "inputs": [], "outputs": []}),
                    dialogs.InstanceDialog(design=make_design())):
            dlg.show()
            flush()
            for button in dlg.findChildren(QtWidgets.QPushButton):
                self.assertFalse(button.isDefault(), button.text())
                self.assertFalse(button.autoDefault(), button.text())


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class AcceptValidationTest(unittest.TestCase):
    def test_valid_input_closes(self):
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [("a", 1, False)], "outputs": [("y", 8)],
        })
        dlg.show()
        dlg.accept()
        flush()
        self.assertEqual(dlg.result(), QtWidgets.QDialog.Accepted)

    def test_bad_width_is_reported_and_blocks_closing(self):
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [("a", 1, False)], "outputs": [],
        })
        dlg.input_table.setItem(0, validate.COL_WIDTH,
                                QtWidgets.QTableWidgetItem("8bit"))
        errors, _ = dlg.check_input()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].column, validate.COL_WIDTH)

    def test_focus_issue_moves_to_the_offending_cell(self):
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top",
            "inputs": [("a", 1, False), ("", 1, False)],
            "outputs": [],
        })
        dlg.show()
        errors, _ = dlg.check_input()
        self.assertTrue(errors)
        dlg.focus_issue(errors[0])
        self.assertEqual(dlg.input_table.currentRow(), 1)
        self.assertEqual(dlg.input_table.currentColumn(), validate.COL_NAME)

    def test_blank_rows_are_dropped_on_close(self):
        """Tab や Ctrl+I で余った未入力行を、閉じるときに捨てる。"""
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [("a", 1, False)], "outputs": [],
        })
        dlg.show()
        dlg.append_input_port()
        dlg.append_input_port()
        self.assertEqual(dlg.input_table.rowCount(), 3)

        dlg.accept()
        flush()
        self.assertEqual(dlg.input_table.rowCount(), 1)
        self.assertEqual(dlg.result(), QtWidgets.QDialog.Accepted)

    def test_a_partly_filled_row_is_kept_and_reported(self):
        """名前だけ入れた行は捨てずにエラーにする(打ちかけを消さない)。"""
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [("a", 1, False)], "outputs": [],
        })
        dlg.append_input_port()
        row = dlg.input_table.rowCount() - 1
        dlg.input_table.item(row, validate.COL_WIDTH).setText("")
        dlg.input_table.item(row, validate.COL_NAME).setText("b")

        self.assertEqual(dlg.drop_blank_rows(), 0)
        errors, _ = dlg.check_input()
        self.assertEqual(errors[0].column, validate.COL_WIDTH)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class ModuleDefDialogTest(unittest.TestCase):
    def make(self):
        return dialogs.ModuleDefDialog(module=netlist.Module(
            "blk", [netlist.Port("a", 4)], [netlist.Port("y", 1)]))

    def test_get_module_returns_the_definition(self):
        module = self.make().get_module()
        self.assertEqual(module.name, "blk")
        self.assertEqual([(p.name, p.width) for p in module.inputs], [("a", 4)])
        self.assertEqual([(p.name, p.width) for p in module.outputs], [("y", 1)])

    def test_renames_are_tracked(self):
        dlg = self.make()
        dlg.input_table.item(0, validate.COL_NAME).setText("aa")
        self.assertEqual(dlg.get_renames(), {"a": "aa"})

    def test_no_rename_when_untouched(self):
        self.assertEqual(self.make().get_renames(), {})

    def test_duplicate_module_name_is_rejected(self):
        dlg = dialogs.ModuleDefDialog(taken_names={"blk", "other"})
        dlg.module_name_edit.setText("other")
        dlg.append_input_port()
        dlg.input_table.item(0, validate.COL_NAME).setText("a")
        errors, _ = dlg.check_input()
        self.assertTrue(any("既に使われています" in e.message for e in errors), errors)


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class ApplyModuleChangeTest(unittest.TestCase):
    def make_design_with_instances(self):
        design = make_design()
        design.instances = [
            netlist.Instance("blk", "u0", connections={"a": "n0", "y": "n1"}),
            netlist.Instance("blk", "u1", connections={"a": "n2", "b": "n3"}),
        ]
        return design

    def test_rename_moves_the_connections(self):
        design = self.make_design_with_instances()
        updated = netlist.Module("blk", [netlist.Port("aa", 4),
                                         netlist.Port("b", 1)],
                                 [netlist.Port("y", 1)])
        dialogs.apply_module_change(design, "blk", updated, {"a": "aa"})

        self.assertEqual(design.instances[0].connections, {"aa": "n0", "y": "n1"})
        self.assertEqual(design.instances[1].connections, {"aa": "n2", "b": "n3"})

    def test_removed_port_drops_its_connection(self):
        design = self.make_design_with_instances()
        updated = netlist.Module("blk", [netlist.Port("a", 4)],
                                 [netlist.Port("y", 1)])
        dialogs.apply_module_change(design, "blk", updated, {})

        self.assertNotIn("b", design.instances[1].connections)
        self.assertEqual(design.instances[0].connections, {"a": "n0", "y": "n1"})

    def test_module_rename_follows_the_instances(self):
        design = self.make_design_with_instances()
        updated = netlist.Module("adder", list(design.modules["blk"].inputs),
                                 list(design.modules["blk"].outputs))
        dialogs.apply_module_change(design, "blk", updated, {})

        self.assertNotIn("blk", design.modules)
        self.assertIn("adder", design.modules)
        for instance in design.instances:
            self.assertEqual(instance.module_name, "adder")


@unittest.skipIf(QtWidgets is None, "PySide6 が無い")
class InstanceDialogTest(unittest.TestCase):
    def test_lists_the_existing_modules(self):
        dlg = dialogs.InstanceDialog(design=make_design())
        items = [dlg.module_combo.itemText(i)
                 for i in range(dlg.module_combo.count())]
        self.assertIn("blk", items)
        self.assertIn(dialogs.InstanceDialog.NEW_MODULE, items)

    def test_port_columns_are_read_only(self):
        dlg = dialogs.InstanceDialog(design=make_design())
        for row in range(dlg.table.rowCount()):
            for column in (dlg.COL_DIRECTION, dlg.COL_PORT):
                flags = dlg.table.item(row, column).flags()
                self.assertFalse(flags & QtCore.Qt.ItemIsSelectable)
                self.assertFalse(flags & QtCore.Qt.ItemIsEditable)
            self.assertTrue(
                dlg.table.item(row, dlg.COL_WIRE).flags() & QtCore.Qt.ItemIsEditable)

    def test_tab_visits_only_the_wire_column(self):
        """読み取り専用でも Tab の移動先からは外れないので、明示的に飛ばす。"""
        dlg = dialogs.InstanceDialog(design=make_design())
        dlg.show()
        table = dlg.table
        table.setFocus()
        table.setCurrentCell(0, dlg.COL_WIRE)

        visited = [(table.currentRow(), table.currentColumn())]
        for _ in range(3):
            QtTest.QTest.keyClick(table, QtCore.Qt.Key_Tab)
            flush()
            visited.append((table.currentRow(), table.currentColumn()))

        self.assertEqual([column for _, column in visited],
                         [dlg.COL_WIRE] * 4)
        self.assertEqual([row for row, _ in visited], [0, 1, 2, 0])

    def test_rows_follow_the_module_definition(self):
        dlg = dialogs.InstanceDialog(design=make_design())
        self.assertEqual(dlg.port_names, ["a", "b", "y"])

    def test_existing_connections_are_shown(self):
        design = make_design()
        instance = netlist.Instance("blk", "u_blk", connections={"a": "net"})
        dlg = dialogs.InstanceDialog(design=design, instance=instance)
        row = dlg.port_names.index("a")
        self.assertEqual(dlg.table.item(row, dlg.COL_WIRE).text(), "net")

    def test_typed_wires_come_back(self):
        design = make_design()
        dlg = dialogs.InstanceDialog(design=design)
        dlg.instance_name_edit.setText("u_blk")
        dlg.table.item(dlg.port_names.index("y"), dlg.COL_WIRE).setText("out")

        data = dlg.get_data()
        self.assertEqual(data["module_name"], "blk")
        self.assertEqual(data["instance_name"], "u_blk")
        self.assertEqual(data["connections"], {"y": "out"})

    def test_instance_name_is_generated_when_empty(self):
        design = make_design()
        design.instances = [netlist.Instance("blk", "u_blk0")]
        dlg = dialogs.InstanceDialog(design=design)
        dlg.instance_name_edit.setText("")
        self.assertEqual(dlg.get_data()["instance_name"], "u_blk1")


if __name__ == "__main__":
    unittest.main()
