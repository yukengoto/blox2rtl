from PySide6 import QtWidgets

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
        self.layout().addWidget(QtWidgets.QLabel("入力ポート:"))
        self.layout().addWidget(self.input_table)

        # 入力ポートの追加・削除・移動ボタン
        input_button_layout = QtWidgets.QHBoxLayout()
        add_input_button = QtWidgets.QPushButton("入力ポート追加")
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
        self.layout().addWidget(QtWidgets.QLabel("出力ポート:"))
        self.layout().addWidget(self.output_table)

        # 出力ポートの追加・削除・移動ボタン
        output_button_layout = QtWidgets.QHBoxLayout()
        add_output_button = QtWidgets.QPushButton("出力ポート追加")
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

        # OKとキャンセルボタン
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout().addWidget(button_box)

        # 既存データがあれば設定
        if module_data:
            self.load_module_data(module_data)

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

    def add_input_port(self):
        row = 0
        selidx = self.input_table.selectedIndexes()
        if len(selidx) > 0:
            row = self.input_table.currentRow()
        else:
            row = self.input_table.rowCount()
        self.input_table.insertRow(row)
        self.setup_new_row(self.input_table, row)

    def remove_input_port(self):
        selidx = self.input_table.selectedIndexes()
        if len(selidx) > 0:
            current_row = self.input_table.currentRow()
            self.input_table.removeRow(current_row)

    def add_output_port(self):
        row = 0
        selidx = self.output_table.selectedIndexes()
        if len(selidx) > 0:
            row = self.output_table.currentRow()
        else:
            row = self.output_table.rowCount()
        self.output_table.insertRow(row)
        self.setup_new_row(self.output_table, row)

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
    
class ModuleDialog(BaseModuleDialog):
    def __init__(self, parent=None, module_data=None):
        super().__init__(parent, module_data, is_instance=False)

    def setup_input_table(self):
        self.input_table = QtWidgets.QTableWidget(0, 3)
        self.input_table.setHorizontalHeaderLabels(["入力ポート名", "ビット幅", "Wire非表示"])

    def setup_output_table(self):
        self.output_table = QtWidgets.QTableWidget(0, 2)
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
        self.input_table = QtWidgets.QTableWidget(0, 3)
        self.input_table.setHorizontalHeaderLabels(["入力ポート名", "ビット幅", "Wire名"])

    def setup_output_table(self):
        self.output_table = QtWidgets.QTableWidget(0, 3)
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
