import sys
import json
from PySide6 import QtCore, QtWidgets, QtGui, QtPrintSupport

from ModuleDialog import ModuleDialog
from ModuleDialog import SubmoduleDialog

BG_COLOR = "white"
BLOCK_COLOR = "lightblue"
WIRE_COLOR = "black"
LINE_COLOR = "black"
TEXT_COLOR = "black"
FOCUS_COLOR = "red"
GRID_SIZE = 10

def bitwidth2linewidth(bit_width):
    if bit_width == 1: wire_width = 1
    elif bit_width < 20: wire_width = 2
    else: wire_width = 4
    return wire_width

# モジュール情報入力ダイアログ
# モジュール名を描画するクラス
class ModuleNameItem(QtWidgets.QGraphicsTextItem):
    def __init__(self, text):
        super().__init__(text)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setDefaultTextColor(QtGui.QColor(LINE_COLOR))
    
    def paint(self, painter, option, widget=None):
        # 四角枠を描画
        rect = self.boundingRect()
        pen = QtGui.QPen(QtGui.QColor(LINE_COLOR), 1)
        painter.setPen(pen)
        painter.drawRect(rect)

        # テキストを中央揃えで描画
        painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, QtCore.Qt.AlignCenter, self.toPlainText())
    
    def mouseDoubleClickEvent(self, event):
        new_name, ok = QtWidgets.QInputDialog.getText(None, "モジュール名の変更", "新しいモジュール名:", text=self.toPlainText())
        if ok and new_name:
            self.setPlainText(new_name)

# ポートを描画するクラス
class PortItem(QtWidgets.QGraphicsPolygonItem):
    def __init__(self, x, y, name, width=1, is_input=True, main_window=None):
        super().__init__()
        self.setPos(x,y)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setBrush(QtGui.QBrush(QtGui.QColor(BLOCK_COLOR if is_input else BLOCK_COLOR)))
        self.setPen(QtGui.QPen(QtGui.QColor(LINE_COLOR), 2))
        
        # ポートの形状を設定
        path = QtGui.QPainterPath()
        if is_input:
            path.moveTo(0, 0)
            path.lineTo(30, 0)
            path.lineTo(40, 5)
            path.lineTo(30, 10)
            path.lineTo(0, 10)
        else:
            path.moveTo(40, 0)
            path.lineTo(10, 0)
            path.lineTo(0, 5)
            path.lineTo(10, 10)
            path.lineTo(40, 10)
        path.closeSubpath()
        self.setPolygon(path.toFillPolygon())
        
        # ポート名とビット幅を設定
        self.name = name
        self.width = width
        self.is_input = is_input
        self.main_window = main_window
        self.text_item = QtWidgets.QGraphicsTextItem(self)
        self.text_item.setDefaultTextColor(QtGui.QColor(TEXT_COLOR))
        self.update_text()
    
    def update_text(self):
        bit_width = f"[{self.width-1}:0]" if self.width > 1 else ""
        self.text_item.setPlainText(f"{self.name}{bit_width}")
        if self.is_input:
            self.text_item.setPos(45, -15)  # 入力ポートの右側に配置
        else:
            self.text_item.setPos(-self.text_item.boundingRect().width() - 5, -15)  # 出力ポートの左側に配置

    def boundingRect(self):
        # 描画領域を定義
        if self.is_input:
            return QtCore.QRectF(0, 0, 100, 10)
        else:
            return QtCore.QRectF(-60, 0, 100, 10)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # ワイヤーを描画
        line_width = bitwidth2linewidth(self.width)
        painter.setPen(QtGui.QPen(QtGui.QColor(WIRE_COLOR), line_width))
        if self.is_input:
            painter.drawLine(40, 5, 100, 5)  # 入力ポートの右側から右に伸びる
        else:
            painter.drawLine(0, 5, -60, 5)  # 出力ポートの左側から左に伸びる
    
    def wire_point(self): 
        if self.is_input: return self.mapToScene(100, 5)
        else: return self.mapToScene(-60, 5)

    def mouseDoubleClickEvent(self, event):
        new_name, ok = QtWidgets.QInputDialog.getText(None, "ポート名の変更", "新しいポート名:", text=self.name)
        if ok and new_name:
            self.name = new_name
            self.update_text()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        # グリッドにスナップ
        new_x = round(self.x() / GRID_SIZE) * GRID_SIZE
        new_y = round(self.y() / GRID_SIZE) * GRID_SIZE
        self.setPos(new_x, new_y)
        if self.main_window:
            self.main_window.updateWires()
        #self.update()  # 再描画をトリガー


# サブモジュールブロックを描画するクラス
class BlockItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, x, y, width, height, module_data=None, main_window=None):
        super().__init__(x, y, width, height)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setBrush(QtGui.QBrush(QtGui.QColor(BLOCK_COLOR)))
        self.main_window = main_window
        self.module_data = module_data or {
            "module_name": "module",
            "instance_name": "instance",
            "inputs": [],
            "outputs": []
        }
        self.port_separation = 20 # vertical distance between ports
        self.wire_length = 40
        self.first_port_offset = 45
        self.update_size_and_labels()

    def boundingRect(self):
        # 再描画範囲を拡張して、ワイヤーやワイヤー名を含むようにする
        rect = self.rect()
        hmargin = 100  # ワイヤーの長さや名前の表示を考慮した余白
        topmargin = 20 # for instance name
        return rect.adjusted(-hmargin, -topmargin, hmargin, 0)

    def sink_wires(self):
        wires = []
        # input ports are sinks
        for i, (portname, width, wire_name) in enumerate(self.module_data["inputs"]):
            x_pos = self.rect().x() - self.wire_length
            y_pos = self.rect().y() + self.first_port_offset + i * self.port_separation
            pos = self.mapToScene(x_pos, y_pos)
            wires.append( (wire_name, pos, width) )
        return wires

    def source_wires(self):
        wires = []
        # output ports are sources
        for i, (name, width, wire) in enumerate(self.module_data["outputs"]):
            x_pos = self.rect().x() + self.rect().width() + self.wire_length
            y_pos = self.rect().y() + self.first_port_offset + i * self.port_separation
            pos = self.mapToScene(x_pos, y_pos)
            wires.append( ( wire, pos, width) )
        return wires
        
    def update_size_and_labels(self):
        # ポート数に応じて高さを調整
        max_ports = max(len(self.module_data["inputs"]), len(self.module_data["outputs"]))
        self.setRect(self.rect().x(), self.rect().y(), 150, self.first_port_offset + max_ports * self.port_separation)

    def mouseDoubleClickEvent(self, event):
        dialog = SubmoduleDialog(module_data=self.module_data)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.module_data = dialog.get_data()
            self.update_size_and_labels()
            self.update()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        # グリッドにスナップ
        new_x = round(self.x() / GRID_SIZE) * GRID_SIZE
        new_y = round(self.y() / GRID_SIZE) * GRID_SIZE
        self.setPos(new_x, new_y)

        if self.main_window:
            self.main_window.updateWires()


    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # 枠線の描画
        if self.isSelected():
            pen = QtGui.QPen(QtGui.QColor(FOCUS_COLOR), 2, QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.rect())
        else:
            pen = QtGui.QPen(QtGui.QColor(LINE_COLOR), 2)
            painter.setPen(pen)
            painter.drawRect(self.rect())
        
        # モジュール名とインスタンス名の描画
        painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))

        fontsize = painter.font().pointSize()

        # モジュール名のフォント設定
        module_font = painter.font()
        module_font.setBold(True)  # 太字に設定
        module_font.setPointSize(fontsize + 4)  # フォントサイズを大きく設定（例: +4ポイント）
        painter.setFont(module_font)
        painter.drawText(self.rect().x() + 5, self.rect().y() + 20, f"{self.module_data['module_name']}")

        # インスタンス名のフォント設定
        instance_font = painter.font()
        instance_font.setBold(True)  # 太字に設定
        instance_font.setPointSize(fontsize)  # フォントサイズを大きく設定（例: +4ポイント）
        painter.setFont(instance_font)
        painter.drawText(self.rect().x() + 5, self.rect().y() - 5, f"{self.module_data['instance_name']}")

        painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))
        font = painter.font()
        # font.setBold(True)  # 太字に設定
        # painter.setFont(font)
        # painter.drawText(self.rect().x() + 5, self.rect().y() - 5, f"{self.module_data['instance_name']}")
        # painter.drawText(self.rect().x() + 5, self.rect().y() + 15, f"{self.module_data['module_name']}")
        font.setBold(False)  # 通常のフォントに戻す 

        # 入力ポート名とワイヤーの描画

        painter.setFont(font)
        port_separation = self.port_separation
        for i, (name, width, wire) in enumerate(self.module_data["inputs"]):
            y_pos = self.rect().y() + self.first_port_offset + i * port_separation
            bit_width = f"[{width-1}:0]" if width > 1 else ""
            painter.drawText(self.rect().x() + 5, y_pos, f"{name} {bit_width}")
            # ワイヤーの矢印を描画
            line_width = bitwidth2linewidth(width)
            arrow_start_x = self.rect().x() - self.wire_length
            arrow_start_y = y_pos + 0
            arrow_end_x = self.rect().x()
            arrow_end_y = arrow_start_y
            painter.setPen(QtGui.QPen(QtGui.QColor(WIRE_COLOR), line_width))
            painter.drawLine(arrow_start_x, arrow_start_y, arrow_end_x, arrow_end_y)
            painter.drawLine(arrow_end_x, arrow_end_y, arrow_end_x - 10, arrow_end_y - 5)
            painter.drawLine(arrow_end_x, arrow_end_y, arrow_end_x - 10, arrow_end_y + 5)
            
            # ワイヤー名を描画
            painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))
            painter.drawText(arrow_start_x, arrow_start_y - 5, wire)
        
        # 出力ポート名とワイヤーの描画
        for i, (name, width, wire) in enumerate(self.module_data["outputs"]):
            y_pos = self.rect().y() + self.first_port_offset + i * port_separation
            bit_width = f"[{width-1}:0]" if width > 1 else ""
            text = f"{name} {bit_width}"
            text_width = painter.fontMetrics().horizontalAdvance(text)
            painter.drawText(self.rect().x() + self.rect().width() - text_width - 5, y_pos, text)
            
            # ワイヤーの矢印を描画
            line_width = bitwidth2linewidth(width)
            arrow_start_x = self.rect().x() + self.rect().width()
            arrow_start_y = y_pos + 0
            arrow_end_x = arrow_start_x + self.wire_length
            arrow_end_y = arrow_start_y
            painter.setPen(QtGui.QPen(QtGui.QColor(WIRE_COLOR), line_width))
            painter.drawLine(arrow_start_x, arrow_start_y, arrow_end_x, arrow_end_y)
            #painter.drawLine(arrow_end_x, arrow_end_y, arrow_end_x - 10, arrow_end_y - 5)
            #painter.drawLine(arrow_end_x, arrow_end_y, arrow_end_x - 10, arrow_end_y + 5)
            
            # ワイヤー名を描画
            painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))
            painter.drawText(arrow_start_x + 10, arrow_start_y - 5, wire)

class WireJunctionManager:
    """ワイヤーの分岐点を管理するクラス"""
    def __init__(self):
        self.junctions = {}  # ワイヤー名をキーとした分岐点情報
        self.wire_paths = {}  # 各ワイヤーの経路情報
    
    def clear(self):
        self.junctions = {}
        self.wire_paths = {}
    
    def add_wire(self, wire_name, wire_item):
        """ワイヤー情報を追加"""
        if wire_name not in self.wire_paths:
            self.wire_paths[wire_name] = []
        
        self.wire_paths[wire_name].append(wire_item)
    
    def calculate_junctions(self):
        """各ワイヤーの分岐点を計算"""
        self.junctions = {}
        
        # 同じ名前のワイヤーをグループ化
        for wire_name, wire_items in self.wire_paths.items():
            if len(wire_items) > 1:  # 複数の接続がある場合
                # 左から右への信号線を基準にする
                left_to_right_wires = [w for w in wire_items if w.start_pos.x() < w.end_pos.x()]
                
                if left_to_right_wires:
                    # 基準となる左から右への信号線を選択
                    rightmost_wire = left_to_right_wires[0]
                    for wire in left_to_right_wires:
                        if wire.get_midx() > rightmost_wire.get_midx():
                            rightmost_wire = wire
                    left_to_right_wires.remove(rightmost_wire)
                    for base_wire in left_to_right_wires:
                        # 基準ワイヤーの縦線のx座標を取得
                        junction_x = base_wire.get_midx()
                        # 分岐点のy座標は、基準ワイヤーの始点のy座標
                        junction_y = base_wire.start_pos.y()
                        # 分岐点を保存
                        if wire_name not in self.junctions:
                            self.junctions[wire_name] = []
                        self.junctions[wire_name].append(QtCore.QPointF(junction_x, junction_y))
    
    def get_junction_points(self, wire_name):
        """指定したワイヤー名の分岐点を取得"""
        return self.junctions.get(wire_name, [])


class JunctionItem(QtWidgets.QGraphicsEllipseItem):
    """分岐点を表す黒丸"""
    def __init__(self, x, y, radius=4):
        super().__init__(x - radius, y - radius, radius * 2, radius * 2)
        self.setBrush(QtGui.QBrush(QtGui.QColor(WIRE_COLOR)))
        self.setPen(QtGui.QPen(QtGui.QColor(WIRE_COLOR)))

class WireItem(QtWidgets.QGraphicsPathItem):
    instances = [] # all instances of this class
    vertical_wire_lines = []
    WIRE_SEPARATION = 5
    
    def __init__(self, start_pos, end_pos, default_name, width, junction_manager=None):
        super().__init__()
        WireItem.instances.append(self)
        self.width = width
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable | 
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        line_width = bitwidth2linewidth(width)
        self.setPen(QtGui.QPen(QtGui.QColor(WIRE_COLOR), line_width, QtCore.Qt.SolidLine))
        
        # 線の始点と終点を設定
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.name = default_name
        self.junction_manager = junction_manager
        self.mid_x = None  # 縦線のx座標を保存
        
        # 信号線を描画
        self.update_path()
        
        # ジャンクションマネージャーにワイヤー情報を追加
        if self.junction_manager:
            self.junction_manager.add_wire(self.name, self)
        

    def update_path(self):
        """信号線を縦または横の線で描画"""
        path = QtGui.QPainterPath()
        path.moveTo(self.start_pos)

        # 始点と終点の位置関係を確認
        is_right_to_left = self.start_pos.x() > self.end_pos.x()
        
        if is_right_to_left:
            # 右から左への信号の場合
            # 始点から右に少し伸ばす
            right_offset = self.start_pos.x() + 20
            right_offset = self.get_uniq_x(right_offset, self.start_pos.y(), self.end_pos.y())
            path.lineTo(right_offset, self.start_pos.y())
            
            # 上または下に伸ばす（他の線と重ならないように）
            vertical_offset = self.get_vertical_offset()
            path.lineTo(right_offset, vertical_offset)
            
            # 終点の左側まで水平に伸ばす
            left_offset = self.end_pos.x() - 20
            left_offset = self.get_uniq_x(left_offset, self.start_pos.y(), self.end_pos.y())
            path.lineTo(left_offset, vertical_offset)
            
            # 終点の高さまで垂直に伸ばす
            path.lineTo(left_offset, self.end_pos.y())
            
            # 縦線のx座標を保存
            self.mid_x = right_offset
        else:
            # 左から右への信号の場合
            mid_x = self.get_midx()
            path.lineTo(mid_x, self.start_pos.y())  # 横線
            path.lineTo(mid_x, self.end_pos.y())    # 縦線
            
            # 縦線のx座標を保存
            self.mid_x = mid_x
        
        # 最終点に接続
        path.lineTo(self.end_pos)
        
        self.setPath(path)

    def get_vertical_offset(self):
        """重ならない垂直位置を計算"""
        base_y = (self.start_pos.y() + self.end_pos.y()) / 2
        
        # 既存のワイヤーの位置を確認して重ならないようにする
        wire_count = 0
        for wire in WireItem.instances:
            if wire != self and wire.start_pos.x() > wire.end_pos.x():
                wire_count += 1
        
        return base_y - (wire_count * 15)  # 15ピクセルずつずらす

    def get_uniq_x(self, x_in, y0_in, y1_in):
        mid_xs = []
        x = x_in
        for vline in WireItem.vertical_wire_lines:
            omidx = vline["x"]
            mid_xs.append(omidx)
        sorted_xs = mid_xs.sort()
        for xex in mid_xs:
            if x == xex: x += WireItem.WIRE_SEPARATION
        WireItem.vertical_wire_lines.append({"x":x, "y0":y0_in, "y1":y1_in})
        return x


    def get_midx(self):
        """縦線のx座標を取得"""
        if self.mid_x is not None:
            return self.mid_x
            
        mid_x = (self.start_pos.x() + self.end_pos.x()) / 2
        mid_x = self.get_uniq_x(mid_x, self.start_pos.y(), self.end_pos.y())
        return mid_x

    # def mouseDoubleClickEvent(self, event):
    #     # ダブルクリックでWire名を変更
    #     new_name, ok = QtWidgets.QInputDialog.getText(None, "Wire名の変更", "新しいWire名:", text=self.name)
    #     if ok and new_name:
    #         self.name = new_name
    #         self.update_text()


# カスタムQGraphicsViewクラスを作成
class CustomGraphicsView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.main_window = parent

    def keyPressEvent(self, event):
        # 選択されているアイテムを取得
        selected_items = self.scene().selectedItems()
        
        if selected_items:
            # 矢印キーの処理
            if event.key() == QtCore.Qt.Key_Left:
                for item in selected_items:
                    item.moveBy(-GRID_SIZE, 0)
                self.main_window.updateWires()
                event.accept()
                return
            elif event.key() == QtCore.Qt.Key_Right:
                for item in selected_items:
                    item.moveBy(GRID_SIZE, 0)
                self.main_window.updateWires()
                event.accept()
                return
            elif event.key() == QtCore.Qt.Key_Up:
                for item in selected_items:
                    item.moveBy(0, -GRID_SIZE)
                self.main_window.updateWires()
                event.accept()
                return
            elif event.key() == QtCore.Qt.Key_Down:
                for item in selected_items:
                    item.moveBy(0, GRID_SIZE)
                self.main_window.updateWires()
                event.accept()
                return
                
        super().keyPressEvent(event)

# メインウィンドウの定義
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ブロック図作成ツール")
        self.resize(800, 600)
        
        # QGraphicsSceneとQGraphicsViewを利用して描画領域を設定
        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(BG_COLOR)))  # 背景色

        self.view = CustomGraphicsView(self.scene, self)
        self.setCentralWidget(self.view)
        #self.view = QtWidgets.QGraphicsView(self.scene)
        #self.setCentralWidget(self.view)

        # メニューバーを作成
        menubar = self.menuBar()
        
        # ファイルメニューを作成
        fileMenu = menubar.addMenu("ファイル")

        openAction = QtGui.QAction("ブロック図を開く", self)
        openAction.triggered.connect(self.openDiagram)
        fileMenu.addAction(openAction)
        
        saveAction = QtGui.QAction("ブロック図を保存", self)
        saveAction.triggered.connect(self.saveDiagram)
        fileMenu.addAction(saveAction)

        printAction = QtGui.QAction("印刷", self)
        printAction.triggered.connect(self.printDiagram)
        fileMenu.addAction(printAction)
       
        # ブロック図メニューを作成
        diagramMenu = menubar.addMenu("編集")
        
        editModuleAction = QtGui.QAction("モジュール情報", self)
        editModuleAction.triggered.connect(self.editModule)
        diagramMenu.addAction(editModuleAction)
        
        addBlockAction = QtGui.QAction("サブモジュール追加", self)
        addBlockAction.triggered.connect(self.addBlock)
        diagramMenu.addAction(addBlockAction)
        
        deleteBlockAction = QtGui.QAction("サブモジュール削除", self)
        deleteBlockAction.triggered.connect(self.deleteSelectedBlock)
        diagramMenu.addAction(deleteBlockAction)
        
        connectWiresAction = QtGui.QAction("Update wires (debug)", self)
        connectWiresAction.triggered.connect(self.updateWires)
        diagramMenu.addAction(connectWiresAction)
        
        # ショートカットキーの設定
        deleteBlockAction.setShortcut(QtGui.QKeySequence.Delete)

        # # ツールバーにボタンを配置
        # toolbar = QtWidgets.QToolBar("ツール")
        # self.addToolBar(toolbar)
        
        # editModuleAction = QtGui.QAction("モジュール編集", self)
        # editModuleAction.triggered.connect(self.editModule)
        # toolbar.addAction(editModuleAction)
        
        # addBlockAction = QtGui.QAction("サブモジュールブロック追加", self)
        # addBlockAction.triggered.connect(self.addBlock)
        # toolbar.addAction(addBlockAction)
        
        # deleteBlockAction = QtGui.QAction("サブモジュールブロック削除", self)
        # deleteBlockAction.triggered.connect(self.deleteSelectedBlock)
        # toolbar.addAction(deleteBlockAction)
        
        # saveAction = QtGui.QAction("保存", self)
        # saveAction.triggered.connect(self.saveDiagram)
        # toolbar.addAction(saveAction)
        
        # openAction = QtGui.QAction("開く", self)
        # openAction.triggered.connect(self.openDiagram)
        # toolbar.addAction(openAction)

        # openAction = QtGui.QAction("Connect Wires", self)
        # openAction.triggered.connect(self.connectWires)
        # toolbar.addAction(openAction)
        
        # モジュール名をシーンに追加
        self.module_name_item = ModuleNameItem("ModuleName")
        self.scene.addItem(self.module_name_item)
        self.wires_to_hide = [] # add names of wires to hide
    
    def editModule(self):
        module_data = {
            "module_name": self.module_name_item.toPlainText(),
            "inputs": [(item.name, item.width, item.name in self.wires_to_hide) for item in self.scene.items() if isinstance(item, PortItem) and item.is_input],
            "outputs": [(item.name, item.width) for item in self.scene.items() if isinstance(item, PortItem) and not item.is_input]
        }
        dialog = ModuleDialog(module_data=module_data)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            data = dialog.get_data()
            self.module_name_item.setPlainText(data["module_name"])
            positions = {} # remember positions before update
            for item in self.scene.items():
                if isinstance(item, PortItem):
                    positions[item.name] = item.pos()
                    self.scene.removeItem(item)
            posy = 0
            for name, width, hide_wire in data["inputs"]:
                port = PortItem(0, posy, name, width, is_input=True, main_window=self)
                if positions.get(name): 
                    port.setPos(positions[name])
                self.scene.addItem(port)
                posy += 50
            posy = 0
            for output_data in data["outputs"]:
                name = output_data[0]
                width = output_data[1]
                hide_wire = output_data[2] if len(output_data) > 2 else False
                #
                port = PortItem(1000, posy, name, width, is_input=False, main_window=self)
                if positions.get(name): 
                    port.setPos(positions[name])
                self.scene.addItem(port)
                posy += 50
            self.wires_to_hide = dialog.get_hidden_portwires()
            self.updateWires()
    
    def addBlock(self):
        # サブモジュールの情報を入力するダイアログを開く
        dialog = SubmoduleDialog()
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            #
            x = 50 + (self.scene.itemsBoundingRect().width() % 400)
            y = 50 + (self.scene.itemsBoundingRect().height() % 300)
            block = BlockItem(x, y, 150, 50, main_window=self, module_data=dialog.get_data())
            self.scene.addItem(block)
            block.update()
            self.updateWires()  # update wires

    def deleteSelectedBlock(self):
        for item in self.scene.selectedItems():
            if isinstance(item, BlockItem):
                reply = QtWidgets.QMessageBox.question(self, '確認', f"インスタンス '{item.module_data['instance_name']}' を削除しますか？",
                                                       QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
                if reply == QtWidgets.QMessageBox.Yes:
                    self.scene.removeItem(item)
                    self.updateWires()  # update wires

    # MainWindowクラスのupdateWiresメソッドを修正
    def updateWires(self):
        # 分岐点管理オブジェクトを作成
        junction_manager = WireJunctionManager()
        
        # 既存のワイヤーと分岐点を削除
        for item in self.scene.items():
            if isinstance(item, WireItem) or isinstance(item, JunctionItem):
                self.scene.removeItem(item)
                if isinstance(item, WireItem):
                    WireItem.instances.remove(item)
        WireItem.vertical_wire_lines = []

        # ワイヤーの接続情報を収集
        wire_srcs = []
        wire_snks = []
        for item in self.scene.items():
            if isinstance(item, PortItem):
                if item.is_input:  # source
                    wire_srcs.append((item.name, item.wire_point(), item.width))
                else:  # sink
                    wire_snks.append((item.name, item.wire_point(), item.width))
            elif isinstance(item, BlockItem):
                for wire in item.sink_wires():
                    wire_snks.append(wire)
                for wire in item.source_wires():
                    wire_srcs.append(wire)

        # ワイヤーを作成
        for src_wire, srcpos, srcw in wire_srcs:
            for snk_wire, snkpos, snkw in wire_snks:
                if src_wire == snk_wire:
                    if src_wire not in self.wires_to_hide:
                        width = 1
                        if srcw: width = srcw
                        elif snkw: width = snkw
                        wire = WireItem(srcpos, snkpos, src_wire, width, junction_manager)
                        self.scene.addItem(wire)
        
        # 分岐点を計算
        junction_manager.calculate_junctions()
        
        # 分岐点を描画
        for wire_name, points in junction_manager.junctions.items():
            for point in points:
                junction = JunctionItem(point.x(), point.y())
                self.scene.addItem(junction)

    def saveDiagram(self):
        items_data = []
        for item in self.scene.items():
            if isinstance(item, ModuleNameItem):
                items_data.append({
                    "type": "module_name",
                    "text": item.toPlainText(),
                    "x": item.pos().x(),
                    "y": item.pos().y()
                })
            elif isinstance(item, PortItem):
                items_data.append({
                    "type": "port",
                    "name": item.name,
                    "width": item.width,
                    "is_input": item.is_input,
                    "x": item.pos().x(),
                    "y": item.pos().y()
                })
            elif isinstance(item, BlockItem):
                items_data.append({
                    "type": "submodule",
                    "x": item.pos().x(),
                    "y": item.pos().y(),
                    "module_data": item.module_data
                })
        items_data.append({
            "type": "global", 
            "wires_to_hide": self.wires_to_hide 
        })
        
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "ブロック図を保存", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'w') as file:
                json.dump(items_data, file, indent=4)

    def openDiagram(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "ブロック図を開く", "", "JSON Files (*.json)")
        if file_path:
            with open(file_path, 'r') as file:
                items_data = json.load(file)
            
            self.scene.clear()
            for item_data in items_data:
                if item_data["type"] == "module_name":
                    module_name = ModuleNameItem(item_data["text"])
                    module_name.setPos(item_data["x"], item_data["y"])
                    self.scene.addItem(module_name)
                    self.module_name_item = module_name
                elif item_data["type"] == "port":
                    port = PortItem(0, 0, item_data["name"], item_data["width"], item_data["is_input"], main_window=self)
                    port.setPos(item_data["x"], item_data["y"])
                    self.scene.addItem(port)
                elif item_data["type"] == "submodule":
                    block = BlockItem(0, 0, 150, 50, item_data["module_data"], self)
                    block.setPos(item_data["x"], item_data["y"])
                    self.scene.addItem(block)
                elif item_data["type"] == "global":
                    self.wires_to_hide = item_data["wires_to_hide"]
            self.updateWires()

    def printDiagram(self):
        printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
        dialog = QtPrintSupport.QPrintDialog(printer, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            painter = QtGui.QPainter(printer)
            self.scene.render(painter)
            painter.end()

# アプリケーション実行部
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())