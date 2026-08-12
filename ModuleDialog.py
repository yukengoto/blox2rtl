from PySide6 import QtCore, QtGui, QtWidgets

import validate

# キー割り当ての説明。ダイアログ下部に出す
SHORTCUT_HINT = ("Ctrl+I 入力追加    Ctrl+O 出力追加    Tab 次のセル(行末で次の行)    "
                 "Enter 編集終了    Ctrl+Enter OK    Esc 取消")


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


class BaseModuleDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, module_data=None, is_instance=False):
        super().__init__(parent)
        self.setWindowTitle("モジュール情報入力")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.is_instance = is_instance

        # モジュール名
        self.module_name_edit = QtWidgets.QLineEdit()
        self.layout().addWidget(QtWidgets.QLabel("モジュール名:"))
        self.layout().addWidget(self.module_name_edit)

        # インスタンス固有のUI要素
        self.setup_instance_specific_ui()

        # 入力ポートのテーブル
        self.setup_input_table()
        self.input_table.appendRowRequested.connect(self.append_input_port)
        self.layout().addWidget(QtWidgets.QLabel("入力ポート:"))
        self.layout().addWidget(self.input_table)

        # 入力ポートの追加・削除・移動ボタン
        input_button_layout = QtWidgets.QHBoxLayout()
        add_input_button = QtWidgets.QPushButton("入力ポート追加 (Ctrl+I)")
        add_input_button.clicked.connect(self.add_input_port)
        remove_input_button = QtWidgets.QPushButton("入力ポート削除")
        remove_input_button.clicked.connect(self.remove_input_port)
        
        # 上下移動ボタンを追加
        move_input_up_button = QtWidgets.QPushButton("↑")
        move_input_up_button.clicked.connect(lambda: self.move_port(self.input_table, -1))
        move_input_up_button.setToolTip("選択したポートを上に移動")
        move_input_up_button.setFixedWidth(30)
        
        move_input_down_button = QtWidgets.QPushButton("↓")
        move_input_down_button.clicked.connect(lambda: self.move_port(self.input_table, 1))
        move_input_down_button.setToolTip("選択したポートを下に移動")
        move_input_down_button.setFixedWidth(30)
        
        input_button_layout.addWidget(add_input_button)
        input_button_layout.addWidget(remove_input_button)
        input_button_layout.addWidget(move_input_up_button)
        input_button_layout.addWidget(move_input_down_button)
        self.layout().addLayout(input_button_layout)

        # 出力ポートのテーブル
        self.setup_output_table()
        self.output_table.appendRowRequested.connect(self.append_output_port)
        self.layout().addWidget(QtWidgets.QLabel("出力ポート:"))
        self.layout().addWidget(self.output_table)

        # 出力ポートの追加・削除・移動ボタン
        output_button_layout = QtWidgets.QHBoxLayout()
        add_output_button = QtWidgets.QPushButton("出力ポート追加 (Ctrl+O)")
        add_output_button.clicked.connect(self.add_output_port)
        remove_output_button = QtWidgets.QPushButton("出力ポート削除")
        remove_output_button.clicked.connect(self.remove_output_port)
        
        # 上下移動ボタンを追加
        move_output_up_button = QtWidgets.QPushButton("↑")
        move_output_up_button.clicked.connect(lambda: self.move_port(self.output_table, -1))
        move_output_up_button.setToolTip("選択したポートを上に移動")
        move_output_up_button.setFixedWidth(30)
        
        move_output_down_button = QtWidgets.QPushButton("↓")
        move_output_down_button.clicked.connect(lambda: self.move_port(self.output_table, 1))
        move_output_down_button.setToolTip("選択したポートを下に移動")
        move_output_down_button.setFixedWidth(30)
        
        output_button_layout.addWidget(add_output_button)
        output_button_layout.addWidget(remove_output_button)
        output_button_layout.addWidget(move_output_up_button)
        output_button_layout.addWidget(move_output_down_button)
        self.layout().addLayout(output_button_layout)

        # キー割り当ての説明
        hint = QtWidgets.QLabel(SHORTCUT_HINT)
        hint.setStyleSheet("color: gray;")
        hint_font = hint.font()
        hint_font.setPointSize(max(hint_font.pointSize() - 1, 7))
        hint.setFont(hint_font)
        self.layout().addWidget(hint)

        # OKとキャンセルボタン
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout().addWidget(button_box)

        self.setup_shortcuts()

        # 既存データがあれば設定
        if module_data:
            self.load_module_data(module_data)

    def setup_shortcuts(self):
        for key, slot in (("Ctrl+I", self.add_input_port),
                          ("Ctrl+O", self.add_output_port),
                          ("Ctrl+Return", self.accept),
                          ("Ctrl+Enter", self.accept)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            # 既定の WindowShortcut はウィンドウがアクティブであることを要求する。
            # このダイアログの中だけで効けばよいので範囲を狭める
            shortcut.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)

        self.clear_default_buttons()

        # 名前欄で Enter を押したら表へ移る
        self.module_name_edit.returnPressed.connect(self.input_table.setFocus)
        if self.is_instance:
            self.instance_name_edit.returnPressed.connect(self.input_table.setFocus)

    def clear_default_buttons(self):
        """既定ボタンを無くす。

        既定ボタンがあると、どこで Enter を押してもダイアログが閉じる。
        閉じる経路は OK ボタンと Ctrl+Enter だけにする。
        """
        for button in self.findChildren(QtWidgets.QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)

    def showEvent(self, event):
        super().showEvent(event)
        # QDialogButtonBox は表示のたびに OK を既定ボタンへ戻すので、その後で外す
        self.clear_default_buttons()

    def move_port(self, table, direction):
        """
        選択されたポートを上または下に移動する
        direction: -1 (上へ移動) または 1 (下へ移動)
        """
        current_row = table.currentRow()
        if current_row < 0:  # 選択されていない場合
            return
            
        target_row = current_row + direction
        if target_row < 0 or target_row >= table.rowCount():  # 範囲外の移動を防止
            return
            
        # 行の内容を保存
        row_data = self.save_row_data(table, current_row)
        target_row_data = self.save_row_data(table, target_row)
        
        # 行を入れ替え
        self.set_row_data(table, current_row, target_row_data)
        self.set_row_data(table, target_row, row_data)
        
        # 移動後の行を選択状態にする
        table.selectRow(target_row)

    def save_row_data(self, table, row):
        """テーブルの行データを保存する"""
        data = {}
        
        # 通常のセルアイテムを保存
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                data[f'item_{col}'] = item.text()
            else:
                data[f'item_{col}'] = None
                
        # セルウィジェットを保存（チェックボックスなど）
        for col in range(table.columnCount()):
            widget = table.cellWidget(row, col)
            if isinstance(widget, QtWidgets.QCheckBox):
                data[f'checkbox_{col}'] = widget.isChecked()
                
        return data

    def set_row_data(self, table, row, data):
        """保存したデータでテーブルの行を設定する"""
        # 通常のセルアイテムを設定
        for col in range(table.columnCount()):
            key = f'item_{col}'
            if key in data and data[key] is not None:
                table.setItem(row, col, QtWidgets.QTableWidgetItem(data[key]))
                
        # セルウィジェットを設定（チェックボックスなど）
        for col in range(table.columnCount()):
            key = f'checkbox_{col}'
            if key in data:
                checkbox = QtWidgets.QCheckBox()
                checkbox.setChecked(data[key])
                table.setCellWidget(row, col, checkbox)

    def setup_instance_specific_ui(self):
        # サブクラスでオーバーライド
        pass

    def setup_input_table(self):
        # サブクラスでオーバーライド
        pass

    def setup_output_table(self):
        # サブクラスでオーバーライド
        pass

    def load_module_data(self, module_data):
        self.module_name_edit.setText(module_data.get("module_name", ""))
        self.set_table_data(self.input_table, module_data.get("inputs", []))
        self.set_table_data(self.output_table, module_data.get("outputs", []))

    def insert_row(self, table, row):
        """row 番目に行を挿入し、そこから打ち始められる状態にする。"""
        table.insertRow(row)
        self.setup_new_row(table, row)

        # ビット幅を空のままにすると get_table_data() がその行を拾わず、
        # ポートが黙って消える。既定値を入れておく
        table.setItem(row, validate.COL_WIDTH, QtWidgets.QTableWidgetItem("1"))

        name_item = QtWidgets.QTableWidgetItem("")
        table.setItem(row, validate.COL_NAME, name_item)
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
        """末尾に足す (Tab / Enter で行末まで来たとき)。"""
        self.insert_row(self.input_table, self.input_table.rowCount())

    def remove_input_port(self):
        selidx = self.input_table.selectedIndexes()
        if len(selidx) > 0:
            current_row = self.input_table.currentRow()
            self.input_table.removeRow(current_row)

    def add_output_port(self):
        """選択行の下に足す。選択が無ければ末尾。"""
        row = self.output_table.currentRow()
        at = row + 1 if row >= 0 else self.output_table.rowCount()
        self.insert_row(self.output_table, at)

    def append_output_port(self):
        """末尾に足す (Tab / Enter で行末まで来たとき)。"""
        self.insert_row(self.output_table, self.output_table.rowCount())

    def remove_output_port(self):
        selidx = self.output_table.selectedIndexes()
        if len(selidx) > 0:
            current_row = self.output_table.currentRow()
            self.output_table.removeRow(current_row)

    def setup_new_row(self, table, row):
        # サブクラスでオーバーライド
        pass

    def set_table_data(self, table, data):
        # サブクラスでオーバーライド
        pass

    def get_table_data(self, table):
        # サブクラスでオーバーライド
        pass

    def get_data(self):
        # サブクラスでオーバーライド
        pass

    # -- 閉じるときの検証 ---------------------------------------------------

    def raw_rows(self, table):
        """セルの中身を文字列のまま読む。int() に通す前に検査するため。"""
        rows = []
        for row in range(table.rowCount()):
            values = []
            for column in (validate.COL_NAME, validate.COL_WIDTH):
                item = table.item(row, column)
                values.append(item.text().strip() if item else "")
            wire = None
            if self.is_instance:  # Wire 名の列を持つのはサブモジュール側だけ
                item = table.item(row, validate.COL_WIRE)
                wire = item.text().strip() if item else ""
            rows.append((values[0], values[1], wire))
        return rows

    def check_input(self):
        return validate.check(
            self.module_name_edit.text(),
            self.raw_rows(self.input_table),
            self.raw_rows(self.output_table),
            instance_name=self.instance_name_edit.text() if self.is_instance else None,
        )

    def focus_issue(self, issue):
        """指摘のあった場所にカーソルを移す。"""
        if issue.where == "module_name":
            self.module_name_edit.setFocus()
            self.module_name_edit.selectAll()
        elif issue.where == "instance_name" and self.is_instance:
            self.instance_name_edit.setFocus()
            self.instance_name_edit.selectAll()
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

        if self.is_instance:  # Wire 名の列を持つのはサブモジュール側だけ
            wire = table.item(row, validate.COL_WIRE)
            if wire and wire.text().strip():
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
    def __init__(self, parent=None, module_data=None):
        super().__init__(parent, module_data, is_instance=False)

    def setup_input_table(self):
        self.input_table = PortTable(0, 3)
        self.input_table.setHorizontalHeaderLabels(["入力ポート名", "ビット幅", "Wire非表示"])

    def setup_output_table(self):
        self.output_table = PortTable(0, 2)
        self.output_table.setHorizontalHeaderLabels(["出力ポート名", "ビット幅"])

    def setup_new_row(self, table, row):
        if table == self.input_table:
            checkbox = QtWidgets.QCheckBox()
            table.setCellWidget(row, 2, checkbox)

    def set_table_data(self, table, data):
        table.setRowCount(len(data))
        for row, rinfo in enumerate(data):
            portname = rinfo[0]
            width = rinfo[1]
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(portname))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(width)))
            if table == self.input_table:
                checkbox = QtWidgets.QCheckBox()
                if len(rinfo) > 2:
                    checkbox.setChecked(rinfo[2])
                table.setCellWidget(row, 2, checkbox)

    def get_table_data(self, table):
        data = []
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            width_item = table.item(row, 1)
            if name_item and width_item:
                name = name_item.text()
                width = int(width_item.text())
                if table == self.input_table:
                    checkbox = table.cellWidget(row, 2)
                    hide_wire = checkbox.isChecked() if checkbox else False
                    data.append((name, width, hide_wire))
                else:
                    data.append((name, width))
        return data

    def get_data(self):
        module_name = self.module_name_edit.text()
        return {
            "module_name": module_name,
            "inputs": self.get_table_data(self.input_table),
            "outputs": self.get_table_data(self.output_table),
        }

    def get_hidden_portwires(self):
        ret = []
        for row in range(self.input_table.rowCount()):
            name_item = self.input_table.item(row, 0)
            checkbox = self.input_table.cellWidget(row, 2)
            if checkbox and checkbox.isChecked():
                name = name_item.text()
                ret.append(name)
        return ret


class SubmoduleDialog(BaseModuleDialog):
    def __init__(self, parent=None, module_data=None):
        super().__init__(parent, module_data, is_instance=True)

    def setup_instance_specific_ui(self):
        # インスタンス名
        self.instance_name_edit = QtWidgets.QLineEdit()
        inst_text = "インスタンス名 (空欄で自動生成):"
        self.layout().addWidget(QtWidgets.QLabel(inst_text))
        self.layout().addWidget(self.instance_name_edit)

    def setup_input_table(self):
        self.input_table = PortTable(0, 3)
        self.input_table.setHorizontalHeaderLabels(["入力ポート名", "ビット幅", "Wire名"])

    def setup_output_table(self):
        self.output_table = PortTable(0, 3)
        self.output_table.setHorizontalHeaderLabels(["出力ポート名", "ビット幅", "Wire名"])

    def load_module_data(self, module_data):
        super().load_module_data(module_data)
        self.instance_name_edit.setText(module_data.get("instance_name", ""))

    def set_table_data(self, table, data):
        table.setRowCount(len(data))
        for row, rinfo in enumerate(data):
            portname = rinfo[0]
            width = rinfo[1]
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(portname))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(width)))
            if len(rinfo) > 2:
                wirename = rinfo[2]
                table.setItem(row, 2, QtWidgets.QTableWidgetItem(wirename))

    def get_table_data(self, table):
        data = []
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            width_item = table.item(row, 1)
            wire_item = table.item(row, 2)
            if name_item and width_item:
                name = name_item.text()
                width = int(width_item.text())
                if wire_item:
                    wire = wire_item.text()
                    data.append((name, width, wire))
                else:
                    data.append((name, width))
        return data

    def get_data(self):
        module_name = self.module_name_edit.text()
        instance_name = self.instance_name_edit.text()
        if not instance_name:  # 自動生成
            instance_name = f"{module_name.lower()}_0"
        return {
            "module_name": module_name,
            "instance_name": instance_name,
            "inputs": self.get_table_data(self.input_table),
            "outputs": self.get_table_data(self.output_table),
        }
