from PySide6 import QtCore, QtGui, QtWidgets

import netlist
import validate

# キー割り当ての説明。ダイアログ下部に出す
PORT_HINT = ("Ctrl+I 入力追加    Ctrl+O 出力追加    Tab 次のセル(行末で次の行)    "
             "Enter 編集終了    Ctrl+Enter OK    Esc 取消")
WIRE_HINT = ("Tab 次の Wire 名    Enter 編集終了    Ctrl+Enter OK    Esc 取消")


class PortTable(QtWidgets.QTableWidget):
    """行末で Tab を押すと次の行を足す表。

    Tab はセル編集中にエディタが先に食うので keyPressEvent では捕まらない。
    エディタを閉じたあと view が呼ぶ moveCursor() を見る。

    Enter には手を入れない。Qt の既定どおり、編集を確定してエディタを閉じ、
    カレントセルはその場に留まる。行を送るのは Tab の役割。
    """

    appendRowRequested = QtCore.Signal()

    def moveCursor(self, action, modifiers):
        if action == QtWidgets.QAbstractItemView.CursorAction.MoveNext:
            index = self.currentIndex()
            if self._is_last_cell(index.row(), index.column()):
                self.appendRowRequested.emit()
                return self.model().index(self.rowCount() - 1, 0)
        return super().moveCursor(action, modifiers)

    def setCellWidget(self, row, column, widget):
        # セルに置いたウィジェット (チェックボックス) はフォーカスチェーンに
        # 入るため、そこで押された Tab は表に届かない。横取りする
        super().setCellWidget(row, column, widget)
        if widget is not None:
            widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.KeyPress \
                and event.key() == QtCore.Qt.Key_Tab \
                and not event.modifiers() & QtCore.Qt.ShiftModifier:
            index = self.indexAt(watched.pos())
            if self._is_last_cell(index.row(), index.column()):
                self.appendRowRequested.emit()
                return True
        return super().eventFilter(watched, event)

    def _is_last_cell(self, row, column):
        return row == self.rowCount() - 1 and column == self.columnCount() - 1

    def beginEditCurrent(self):
        """カレントセルの編集を始める。

        行の追加直後に遅延して呼ばれる。その間に行が消える (未入力行の削除など)
        ことがあるので、捕まえたアイテムではなくその時点のカレントを見る。
        """
        if not self.isVisible():
            return
        item = self.currentItem()
        if item is not None:
            self.editItem(item)


def add_hint(dialog, text):
    label = QtWidgets.QLabel(text)
    label.setStyleSheet("color: gray;")
    font = label.font()
    font.setPointSize(max(font.pointSize() - 1, 7))
    label.setFont(font)
    dialog.layout().addWidget(label)


def clear_default_buttons(dialog):
    """既定ボタンを無くす。

    既定ボタンがあると、どこで Enter を押してもダイアログが閉じる。
    閉じる経路は OK ボタンと Ctrl+Enter だけにする。
    """
    for button in dialog.findChildren(QtWidgets.QPushButton):
        button.setAutoDefault(False)
        button.setDefault(False)


def add_shortcut(dialog, key, slot):
    shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), dialog)
    # 既定の WindowShortcut はウィンドウがアクティブであることを要求する。
    # このダイアログの中だけで効けばよいので範囲を狭める
    shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
    shortcut.activated.connect(slot)
    return shortcut


def read_only_item(text):
    """表示だけのセル。選択も編集もできない。"""
    item = QtWidgets.QTableWidgetItem(text)
    item.setFlags(QtCore.Qt.ItemIsEnabled)
    return item


class WireTable(QtWidgets.QTableWidget):
    """Wire 名の列だけを Tab で渡り歩く表。

    選択も編集もできないセルでも Tab の移動先からは外れないので
    (ItemIsEnabled だけでも訪問される)、明示的に飛ばす。
    """

    def __init__(self, rows, columns, wire_column):
        super().__init__(rows, columns)
        self.wire_column = wire_column

    def moveCursor(self, action, modifiers):
        cursor = QtWidgets.QAbstractItemView.CursorAction
        if action in (cursor.MoveNext, cursor.MovePrevious) and self.rowCount():
            step = 1 if action == cursor.MoveNext else -1
            row = self.currentRow() + step
            if not 0 <= row < self.rowCount():
                row = 0 if step > 0 else self.rowCount() - 1   # 端で折り返す
            return self.model().index(row, self.wire_column)
        return super().moveCursor(action, modifiers)


class BaseModuleDialog(QtWidgets.QDialog):
    """ポートの並びを編集するダイアログの土台。

    トップモジュール用とサブモジュール定義用で共有する。
    どちらも「どのポートがあるか」を決めるもので、接続先は扱わない。
    """

    def __init__(self, parent=None, module_data=None):
        super().__init__(parent)
        self.setWindowTitle("モジュール情報入力")
        self.setLayout(QtWidgets.QVBoxLayout())

        # モジュール名
        self.module_name_edit = QtWidgets.QLineEdit()
        self.layout().addWidget(QtWidgets.QLabel("モジュール名:"))
        self.layout().addWidget(self.module_name_edit)

        # 入力ポートのテーブル
        self.setup_input_table()
        self.input_table.appendRowRequested.connect(self.append_input_port)
        self.layout().addWidget(QtWidgets.QLabel("入力ポート:"))
        self.layout().addWidget(self.input_table)
        self.layout().addLayout(self.make_row_buttons(
            self.input_table, "入力ポート追加 (Ctrl+I)", "入力ポート削除",
            self.add_input_port, self.remove_input_port))

        # 出力ポートのテーブル
        self.setup_output_table()
        self.output_table.appendRowRequested.connect(self.append_output_port)
        self.layout().addWidget(QtWidgets.QLabel("出力ポート:"))
        self.layout().addWidget(self.output_table)
        self.layout().addLayout(self.make_row_buttons(
            self.output_table, "出力ポート追加 (Ctrl+O)", "出力ポート削除",
            self.add_output_port, self.remove_output_port))

        add_hint(self, PORT_HINT)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout().addWidget(button_box)

        add_shortcut(self, "Ctrl+I", self.add_input_port)
        add_shortcut(self, "Ctrl+O", self.add_output_port)
        add_shortcut(self, "Ctrl+Return", self.accept)
        add_shortcut(self, "Ctrl+Enter", self.accept)
        clear_default_buttons(self)
        self.module_name_edit.returnPressed.connect(self.input_table.setFocus)

        if module_data:
            self.load_module_data(module_data)

    def make_row_buttons(self, table, add_text, remove_text, on_add, on_remove):
        layout = QtWidgets.QHBoxLayout()

        add_button = QtWidgets.QPushButton(add_text)
        add_button.clicked.connect(on_add)
        remove_button = QtWidgets.QPushButton(remove_text)
        remove_button.clicked.connect(on_remove)

        up_button = QtWidgets.QPushButton("↑")
        up_button.setToolTip("選択したポートを上に移動")
        up_button.setFixedWidth(30)
        up_button.clicked.connect(lambda: self.move_port(table, -1))

        down_button = QtWidgets.QPushButton("↓")
        down_button.setToolTip("選択したポートを下に移動")
        down_button.setFixedWidth(30)
        down_button.clicked.connect(lambda: self.move_port(table, 1))

        for button in (add_button, remove_button, up_button, down_button):
            layout.addWidget(button)
        return layout

    def showEvent(self, event):
        super().showEvent(event)
        # QDialogButtonBox は表示のたびに OK を既定ボタンへ戻すので、その後で外す
        clear_default_buttons(self)

    # -- 行の移動 -----------------------------------------------------------

    def move_port(self, table, direction):
        current_row = table.currentRow()
        if current_row < 0:
            return
        target_row = current_row + direction
        if target_row < 0 or target_row >= table.rowCount():
            return

        row_data = self.save_row_data(table, current_row)
        target_row_data = self.save_row_data(table, target_row)
        self.set_row_data(table, current_row, target_row_data)
        self.set_row_data(table, target_row, row_data)
        table.selectRow(target_row)

    def save_row_data(self, table, row):
        data = {}
        for col in range(table.columnCount()):
            item = table.item(row, col)
            data[f'item_{col}'] = item.text() if item else None
            if item is not None:
                data[f'origin_{col}'] = item.data(QtCore.Qt.UserRole)
            widget = table.cellWidget(row, col)
            if isinstance(widget, QtWidgets.QCheckBox):
                data[f'checkbox_{col}'] = widget.isChecked()
        return data

    def set_row_data(self, table, row, data):
        for col in range(table.columnCount()):
            key = f'item_{col}'
            if data.get(key) is not None:
                item = QtWidgets.QTableWidgetItem(data[key])
                origin = data.get(f'origin_{col}')
                if origin is not None:
                    item.setData(QtCore.Qt.UserRole, origin)
                table.setItem(row, col, item)
            key = f'checkbox_{col}'
            if key in data:
                checkbox = QtWidgets.QCheckBox()
                checkbox.setChecked(data[key])
                table.setCellWidget(row, col, checkbox)

    # -- サブクラスで実装 ---------------------------------------------------

    def setup_input_table(self):
        raise NotImplementedError

    def setup_output_table(self):
        raise NotImplementedError

    def setup_new_row(self, table, row):
        pass

    def set_table_data(self, table, data):
        raise NotImplementedError

    def get_table_data(self, table):
        raise NotImplementedError

    def get_data(self):
        raise NotImplementedError

    def load_module_data(self, module_data):
        self.module_name_edit.setText(module_data.get("module_name", ""))
        self.set_table_data(self.input_table, module_data.get("inputs", []))
        self.set_table_data(self.output_table, module_data.get("outputs", []))

    # -- 行の追加・削除 -----------------------------------------------------

    def insert_row(self, table, row):
        """row 番目に行を挿入し、そこから打ち始められる状態にする。"""
        table.insertRow(row)
        self.setup_new_row(table, row)

        # ビット幅を空のままにすると get_table_data() がその行を拾わず、
        # ポートが黙って消える。既定値を入れておく
        table.setItem(row, validate.COL_WIDTH, QtWidgets.QTableWidgetItem("1"))
        table.setItem(row, validate.COL_NAME, QtWidgets.QTableWidgetItem(""))
        table.setCurrentCell(row, validate.COL_NAME)
        table.setFocus()
        # moveCursor の途中から呼ばれることがあるので、
        # 編集開始はいったんイベントループに返してから
        QtCore.QTimer.singleShot(0, table.beginEditCurrent)
        return row

    def add_input_port(self):
        """選択行の下に足す。選択が無ければ末尾。"""
        row = self.input_table.currentRow()
        at = row + 1 if row >= 0 else self.input_table.rowCount()
        self.insert_row(self.input_table, at)

    def append_input_port(self):
        """末尾に足す (Tab で行末まで来たとき)。"""
        self.insert_row(self.input_table, self.input_table.rowCount())

    def remove_input_port(self):
        if self.input_table.selectedIndexes():
            self.input_table.removeRow(self.input_table.currentRow())

    def add_output_port(self):
        row = self.output_table.currentRow()
        at = row + 1 if row >= 0 else self.output_table.rowCount()
        self.insert_row(self.output_table, at)

    def append_output_port(self):
        self.insert_row(self.output_table, self.output_table.rowCount())

    def remove_output_port(self):
        if self.output_table.selectedIndexes():
            self.output_table.removeRow(self.output_table.currentRow())

    # -- 閉じるときの検証 ---------------------------------------------------

    def raw_rows(self, table):
        """セルの中身を文字列のまま読む。int() に通す前に検査するため。"""
        rows = []
        for row in range(table.rowCount()):
            values = []
            for column in (validate.COL_NAME, validate.COL_WIDTH):
                item = table.item(row, column)
                values.append(item.text().strip() if item else "")
            rows.append((values[0], values[1], None))
        return rows

    def check_input(self):
        return validate.check(self.module_name_edit.text(),
                              self.raw_rows(self.input_table),
                              self.raw_rows(self.output_table))

    def focus_issue(self, issue):
        """指摘のあった場所にカーソルを移す。"""
        if issue.where == "module_name":
            self.module_name_edit.setFocus()
            self.module_name_edit.selectAll()
        elif issue.where in ("inputs", "outputs") and issue.row >= 0:
            table = self.input_table if issue.where == "inputs" else self.output_table
            table.setFocus()
            table.setCurrentCell(issue.row, max(issue.column, 0))

    def is_blank_row(self, table, row):
        """一度も入力されていない行か。

        Tab や Ctrl+I で足した行が末尾に余りがちなので、閉じるときに捨てる。
        追加直後の行はビット幅に既定値 1 が入っているため、それも空とみなす。
        """
        name = table.item(row, validate.COL_NAME)
        if name and name.text().strip():
            return False
        width = table.item(row, validate.COL_WIDTH)
        if width and width.text().strip() not in ("", "1"):
            return False
        return True

    def drop_blank_rows(self):
        """未入力の行を削除する。何行消したかを返す。"""
        dropped = 0
        for table in (self.input_table, self.output_table):
            for row in reversed(range(table.rowCount())):
                if self.is_blank_row(table, row):
                    table.removeRow(row)
                    dropped += 1
        return dropped

    def accept(self):
        self.drop_blank_rows()
        errors, warnings = self.check_input()

        if errors:
            self.focus_issue(errors[0])
            QtWidgets.QMessageBox.warning(
                self, "入力の確認",
                "次の点を直してください。\n\n"
                + "\n".join(f"・{issue.message}" for issue in errors))
            return

        if warnings:
            reply = QtWidgets.QMessageBox.question(
                self, "確認",
                "次の点があります。このまま閉じますか?\n\n"
                + "\n".join(f"・{issue.message}" for issue in warnings),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                self.focus_issue(warnings[0])
                return

        super().accept()


class ModuleDialog(BaseModuleDialog):
    """トップモジュールの入出力ポートを編集する。"""

    def __init__(self, parent=None, module_data=None):
        super().__init__(parent, module_data)
        self.setWindowTitle("モジュール情報")

    def setup_input_table(self):
        self.input_table = PortTable(0, 3)
        self.input_table.setHorizontalHeaderLabels(
            ["入力ポート名", "ビット幅", "Wire非表示"])

    def setup_output_table(self):
        self.output_table = PortTable(0, 2)
        self.output_table.setHorizontalHeaderLabels(["出力ポート名", "ビット幅"])

    def setup_new_row(self, table, row):
        if table is self.input_table:
            table.setCellWidget(row, 2, QtWidgets.QCheckBox())

    def set_table_data(self, table, data):
        table.setRowCount(len(data))
        for row, entry in enumerate(data):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(entry[0]))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(entry[1])))
            if table is self.input_table:
                checkbox = QtWidgets.QCheckBox()
                if len(entry) > 2:
                    checkbox.setChecked(bool(entry[2]))
                table.setCellWidget(row, 2, checkbox)

    def get_table_data(self, table):
        data = []
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            width_item = table.item(row, 1)
            if not (name_item and width_item):
                continue
            name = name_item.text()
            width = int(width_item.text())
            if table is self.input_table:
                checkbox = table.cellWidget(row, 2)
                data.append((name, width, checkbox.isChecked() if checkbox else False))
            else:
                data.append((name, width))
        return data

    def get_data(self):
        return {
            "module_name": self.module_name_edit.text(),
            "inputs": self.get_table_data(self.input_table),
            "outputs": self.get_table_data(self.output_table),
        }

    def get_hidden_portwires(self):
        hidden = []
        for row in range(self.input_table.rowCount()):
            name_item = self.input_table.item(row, 0)
            checkbox = self.input_table.cellWidget(row, 2)
            if name_item and checkbox and checkbox.isChecked():
                hidden.append(name_item.text())
        return hidden


class ModuleDefDialog(BaseModuleDialog):
    """サブモジュールの定義を編集する。

    ここで決めるのは「どのポートがあるか」だけで、接続先は扱わない。
    同じモジュールを置いた全インスタンスに効く。

    ポート名を変えたときに各インスタンスの接続を付け替えられるよう、
    読み込んだ時点の名前を各行に覚えさせておく。
    """

    def __init__(self, parent=None, module=None, taken_names=()):
        self.taken_names = set(taken_names)
        if module is not None:
            self.taken_names.discard(module.name)
        data = None
        if module is not None:
            data = {
                "module_name": module.name,
                "inputs": [(p.name, p.width) for p in module.inputs],
                "outputs": [(p.name, p.width) for p in module.outputs],
            }
        super().__init__(parent, data)
        self.setWindowTitle("モジュール定義")

    def setup_input_table(self):
        self.input_table = PortTable(0, 2)
        self.input_table.setHorizontalHeaderLabels(["入力ポート名", "ビット幅"])

    def setup_output_table(self):
        self.output_table = PortTable(0, 2)
        self.output_table.setHorizontalHeaderLabels(["出力ポート名", "ビット幅"])

    def set_table_data(self, table, data):
        table.setRowCount(len(data))
        for row, entry in enumerate(data):
            name_item = QtWidgets.QTableWidgetItem(entry[0])
            name_item.setData(QtCore.Qt.UserRole, entry[0])   # 変更前の名前
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(entry[1])))

    def get_table_data(self, table):
        data = []
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            width_item = table.item(row, 1)
            if name_item and width_item:
                data.append((name_item.text(), int(width_item.text())))
        return data

    def get_data(self):
        return {
            "module_name": self.module_name_edit.text().strip(),
            "inputs": self.get_table_data(self.input_table),
            "outputs": self.get_table_data(self.output_table),
        }

    def get_module(self):
        data = self.get_data()
        return netlist.Module(
            data["module_name"],
            [netlist.Port(name, width) for name, width in data["inputs"]],
            [netlist.Port(name, width) for name, width in data["outputs"]])

    def get_renames(self):
        """{変更前のポート名: 変更後の名前} を返す。"""
        renames = {}
        for table in (self.input_table, self.output_table):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is None:
                    continue
                origin = item.data(QtCore.Qt.UserRole)
                if origin and origin != item.text().strip():
                    renames[origin] = item.text().strip()
        return renames

    def check_input(self):
        errors, warnings = super().check_input()
        name = self.module_name_edit.text().strip()
        if name and name in self.taken_names:
            errors.insert(0, validate.Issue(
                f"モジュール名 '{name}' は既に使われています。",
                where="module_name"))
        return errors, warnings


class InstanceDialog(QtWidgets.QDialog):
    """インスタンスの接続を編集する。

    ポートの並びはモジュール定義が決めるので、ここでは読み取り専用。
    打つのは Wire 名だけ。Tab は Wire 名の列だけを渡り歩く。
    """

    NEW_MODULE = "＜新しいモジュールを定義…＞"

    COL_DIRECTION = 0
    COL_PORT = 1
    COL_WIRE = 2

    def __init__(self, parent=None, design=None, instance=None):
        super().__init__(parent)
        self.setWindowTitle("インスタンス")
        self.design = design if design is not None else netlist.Design()
        self.connections = dict(instance.connections) if instance else {}
        self.port_names = []
        self.setLayout(QtWidgets.QVBoxLayout())

        # モジュールの選択
        row = QtWidgets.QHBoxLayout()
        self.module_combo = QtWidgets.QComboBox()
        self.reload_modules(instance.module_name if instance else None)
        self.module_combo.currentIndexChanged.connect(self.on_module_changed)
        row.addWidget(QtWidgets.QLabel("モジュール:"))
        row.addWidget(self.module_combo, 1)

        self.edit_module_button = QtWidgets.QPushButton("定義を編集…")
        self.edit_module_button.clicked.connect(self.edit_module)
        row.addWidget(self.edit_module_button)
        self.layout().addLayout(row)

        # インスタンス名
        self.instance_name_edit = QtWidgets.QLineEdit(instance.name if instance else "")
        self.instance_name_edit.setPlaceholderText("空欄なら自動で付ける")
        self.layout().addWidget(QtWidgets.QLabel("インスタンス名:"))
        self.layout().addWidget(self.instance_name_edit)

        # 接続
        self.table = WireTable(0, 3, self.COL_WIRE)
        self.table.setHorizontalHeaderLabels(["向き", "ポート", "Wire名"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout().addWidget(QtWidgets.QLabel("接続:"))
        self.layout().addWidget(self.table)

        add_hint(self, WIRE_HINT)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout().addWidget(button_box)

        add_shortcut(self, "Ctrl+Return", self.accept)
        add_shortcut(self, "Ctrl+Enter", self.accept)
        clear_default_buttons(self)
        self.instance_name_edit.returnPressed.connect(self.table.setFocus)

        self.reload_ports()

    def showEvent(self, event):
        super().showEvent(event)
        clear_default_buttons(self)

    # -- モジュール ---------------------------------------------------------

    def reload_modules(self, selected=None):
        self.module_combo.blockSignals(True)
        self.module_combo.clear()
        self.module_combo.addItems(sorted(self.design.modules))
        self.module_combo.addItem(self.NEW_MODULE)
        if selected:
            index = self.module_combo.findText(selected)
            if index >= 0:
                self.module_combo.setCurrentIndex(index)
        self.module_combo.blockSignals(False)

    def current_module_name(self):
        name = self.module_combo.currentText()
        return "" if name == self.NEW_MODULE else name

    def current_module(self):
        return self.design.modules.get(self.current_module_name())

    def on_module_changed(self):
        if self.module_combo.currentText() == self.NEW_MODULE:
            self.define_new_module()
        else:
            self.suggest_instance_name()
        self.reload_ports()

    def define_new_module(self):
        dialog = ModuleDefDialog(self, taken_names=self.design.modules)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            module = dialog.get_module()
            self.design.modules[module.name] = module
            self.reload_modules(module.name)
            self.suggest_instance_name()
        else:
            self.reload_modules(next(iter(sorted(self.design.modules)), None))

    def edit_module(self):
        module = self.current_module()
        if module is None:
            self.define_new_module()
            return

        dialog = ModuleDefDialog(self, module=module,
                                 taken_names=self.design.modules)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        updated = dialog.get_module()
        renames = dialog.get_renames()
        apply_module_change(self.design, module.name, updated, renames)
        self.connections = rename_keys(self.connections, renames)
        self.reload_modules(updated.name)
        self.reload_ports()

    def suggest_instance_name(self):
        if not self.instance_name_edit.text().strip():
            name = self.current_module_name()
            if name:
                self.instance_name_edit.setText(
                    self.design.next_instance_name(name))

    # -- 接続 ---------------------------------------------------------------

    def reload_ports(self):
        self.remember_wires()
        self.port_names = []
        self.table.setRowCount(0)

        module = self.current_module()
        if module is None:
            return

        for direction, port in module.ports():
            row = self.table.rowCount()
            self.table.insertRow(row)
            bits = f"[{port.width - 1}:0]" if port.width > 1 else ""
            self.table.setItem(row, self.COL_DIRECTION,
                               read_only_item("入力" if direction == "input" else "出力"))
            self.table.setItem(row, self.COL_PORT,
                               read_only_item(f"{port.name} {bits}".strip()))
            self.table.setItem(row, self.COL_WIRE, QtWidgets.QTableWidgetItem(
                self.connections.get(port.name, "")))
            self.port_names.append(port.name)

        if self.table.rowCount():
            self.table.setCurrentCell(0, self.COL_WIRE)

    def remember_wires(self):
        """表を作り直す前に、打ってある Wire 名を控える。"""
        for row, port_name in enumerate(self.port_names):
            if row >= self.table.rowCount():
                break
            item = self.table.item(row, self.COL_WIRE)
            if item is not None:
                self.connections[port_name] = item.text().strip()

    def get_data(self):
        self.remember_wires()
        module_name = self.current_module_name()
        instance_name = self.instance_name_edit.text().strip()
        if not instance_name and module_name:
            instance_name = self.design.next_instance_name(module_name)
        connections = {name: wire
                       for name, wire in self.connections.items()
                       if name in self.port_names and wire}
        return {"module_name": module_name,
                "instance_name": instance_name,
                "connections": connections}

    def accept(self):
        data = self.get_data()
        errors = []

        if not data["module_name"]:
            errors.append("モジュールが選ばれていません。")
        else:
            problem = validate.identifier_problem(data["instance_name"])
            if problem:
                errors.append(f"インスタンス名: {problem}")

        if errors:
            QtWidgets.QMessageBox.warning(
                self, "入力の確認",
                "次の点を直してください。\n\n"
                + "\n".join(f"・{message}" for message in errors))
            return

        missing = [name for name in self.port_names
                   if not data["connections"].get(name)]
        if missing:
            reply = QtWidgets.QMessageBox.question(
                self, "確認",
                "次のポートに Wire 名がありません。このまま閉じますか?\n\n"
                + "\n".join(f"・{name}" for name in missing),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                return

        super().accept()


def rename_keys(connections, renames):
    """接続のキーをポート名の変更に合わせて付け替える。"""
    if not renames:
        return dict(connections)
    return {renames.get(name, name): wire for name, wire in connections.items()}


def apply_module_change(design, old_name, updated, renames):
    """モジュール定義の変更を、全インスタンスの接続に反映する。

    ポート名の変更は接続を付け替え、消えたポートの接続は捨てる。
    """
    design.modules.pop(old_name, None)
    design.modules[updated.name] = updated
    port_names = set(updated.port_names())

    for instance in design.instances:
        if instance.module_name != old_name:
            continue
        instance.module_name = updated.name
        moved = rename_keys(instance.connections, renames)
        instance.connections = {name: wire for name, wire in moved.items()
                                if name in port_names}
