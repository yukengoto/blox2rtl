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
    def make_submodule(self):
        return dialogs.SubmoduleDialog(module_data={
            "module_name": "blk",
            "instance_name": "u_blk",
            "inputs": [("a", 1, "net")],
            "outputs": [],
        })

    def test_tab_at_the_last_cell_appends_a_row(self):
        dlg = self.make_submodule()
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
        dlg = self.make_submodule()
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
        dlg = dialogs.SubmoduleDialog(module_data={
            "module_name": "blk", "instance_name": "u_blk",
            "inputs": [("a", 1, "n0"), ("b", 1, "n1")], "outputs": [],
        })
        dlg.show()
        table = dlg.input_table
        table.setCurrentCell(0, 0)
        before = table.rowCount()
        QtTest.QTest.keyClick(table, QtCore.Qt.Key_Return)
        flush()
        self.assertEqual(table.currentRow(), 0)
        self.assertEqual(table.rowCount(), before)

    def test_enter_on_the_last_row_does_not_append(self):
        dlg = self.make_submodule()
        dlg.show()
        table = dlg.input_table
        table.setCurrentCell(0, 0)
        before = table.rowCount()
        QtTest.QTest.keyClick(table, QtCore.Qt.Key_Return)
        flush()
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
        dlg = dialogs.ModuleDialog(module_data={
            "module_name": "top", "inputs": [], "outputs": [],
        })
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
        dlg.append_input_port()   # 未入力の行が末尾に増える
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

        dropped = dlg.drop_blank_rows()
        self.assertEqual(dropped, 0)
        errors, _ = dlg.check_input()
        self.assertEqual(errors[0].column, validate.COL_WIDTH)

    def test_a_row_with_only_a_wire_name_is_kept(self):
        dlg = dialogs.SubmoduleDialog(module_data={
            "module_name": "blk", "instance_name": "u_blk",
            "inputs": [("a", 1, "net")], "outputs": [],
        })
        dlg.append_input_port()
        row = dlg.input_table.rowCount() - 1
        dlg.input_table.setItem(row, validate.COL_WIRE,
                                QtWidgets.QTableWidgetItem("half_typed"))
        self.assertEqual(dlg.drop_blank_rows(), 0)

    def test_missing_wire_name_is_only_a_warning(self):
        dlg = dialogs.SubmoduleDialog(module_data={
            "module_name": "blk", "instance_name": "u_blk",
            "inputs": [("a", 1, "")], "outputs": [],
        })
        errors, warnings = dlg.check_input()
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
