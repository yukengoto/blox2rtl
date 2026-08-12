import sys
import json
import math
from pathlib import Path
from PySide6 import QtCore, QtWidgets, QtGui, QtPrintSupport

from ModuleDialog import ModuleDialog
from ModuleDialog import InstanceDialog
from ModuleDialog import ModuleDefDialog
from ModuleDialog import apply_module_change

import netlist
import verilog

BG_COLOR = "white"
BLOCK_COLOR = "lightblue"
WIRE_COLOR = "black"
LINE_COLOR = "black"
TEXT_COLOR = "black"
FOCUS_COLOR = "red"
GRID_SIZE = 10

GRID_COLOR = "#e8e8e8"
GRID_MAJOR_COLOR = "#c8c8c8"
GRID_MAJOR_EVERY = 10          # 10 マスごとに濃い線
GRID_MIN_PIXELS = 4            # 画面上でこれより細かくなったら細線は描かない
CANVAS_BORDER_COLOR = "#909090"
CANVAS_MARGIN = 40             # 要素の外接矩形にこれだけ余白を足す
NEW_ITEM_STEP = 30             # 新しい要素が重なったときにずらす量
PORT_COLUMN_GAP = 160          # サブモジュールの左右からポートまでの距離

WINDOW_TITLE = "ブロック図作成ツール"

def bitwidth2linewidth(bit_width):
    if bit_width == 1: wire_width = 1
    elif bit_width < 20: wire_width = 2
    else: wire_width = 4
    return wire_width

MISSING_MODULE_COLOR = "#f0c0c0"


def snap_to_grid(item):
    item.setPos(round(item.x() / GRID_SIZE) * GRID_SIZE,
                round(item.y() / GRID_SIZE) * GRID_SIZE)


def snap_selection(moved_item):
    """まとめて動かした選択アイテムを全部グリッドに合わせる。

    ドラッグを受け取るのは1個だけなので、そのアイテムだけを揃えると
    一緒に動いた残りがグリッドから外れたままになる。
    """
    scene = moved_item.scene()
    items = list(scene.selectedItems()) if scene else []
    if moved_item not in items:
        items.append(moved_item)
    for item in items:
        snap_to_grid(item)

    main_window = getattr(moved_item, "main_window", None)
    if main_window:
        main_window.updateWires()

# モジュール情報入力ダイアログ
# モジュール名を描画するクラス
class ModuleNameItem(QtWidgets.QGraphicsTextItem):
    def __init__(self, text, main_window=None):
        super().__init__(text)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsSelectable |
                      QtWidgets.QGraphicsItem.ItemIsFocusable)
        self.setDefaultTextColor(QtGui.QColor(LINE_COLOR))
        self.main_window = main_window
    
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
        # 名前だけでなくポートも直せるように、モジュール情報の編集を開く
        if self.main_window is not None:
            self.main_window.editModule()
            return
        new_name, ok = QtWidgets.QInputDialog.getText(
            None, "モジュール名の変更", "新しいモジュール名:", text=self.toPlainText())
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
        snap_selection(self)


# サブモジュールブロックを描画するクラス
class BlockItem(QtWidgets.QGraphicsRectItem):
    """モジュールのインスタンスを表すブロック。

    ポートの定義は持たない。どのモジュールかという名前だけを持ち、
    ポートの並びは design.modules から引く。同じモジュールのブロックは
    すべて同じ定義を見るので、定義を直せば全部に効く。
    """

    def __init__(self, x, y, width, height, instance=None, main_window=None):
        super().__init__(x, y, width, height)
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsMovable |
                      QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setBrush(QtGui.QBrush(QtGui.QColor(BLOCK_COLOR)))
        self.main_window = main_window
        self.instance = instance or netlist.Instance("module", "instance")
        self.port_separation = 20 # vertical distance between ports
        self.wire_length = 40
        self.first_port_offset = 45
        self.update_size_and_labels()

    def module(self):
        """このブロックが指すモジュール定義。無ければ None。"""
        if self.main_window is None:
            return None
        return self.main_window.design.modules.get(self.instance.module_name)

    def ports(self):
        module = self.module()
        return module.ports() if module else []

    def port_rows(self, direction):
        """(行番号, Port) を、その向きのポートについて返す。

        行番号は入力・出力それぞれ 0 から数える (左右で高さを揃えるため)。
        """
        rows = []
        index = 0
        for port_direction, port in self.ports():
            if port_direction == direction:
                rows.append((index, port))
                index += 1
        return rows

    def boundingRect(self):
        # 再描画範囲を拡張して、ワイヤーやワイヤー名を含むようにする
        rect = self.rect()
        hmargin = 100  # ワイヤーの長さや名前の表示を考慮した余白
        topmargin = 20 # for instance name
        return rect.adjusted(-hmargin, -topmargin, hmargin, 0)

    def sink_wires(self):
        wires = []
        # input ports are sinks
        for i, port in self.port_rows("input"):
            x_pos = self.rect().x() - self.wire_length
            y_pos = self.rect().y() + self.first_port_offset + i * self.port_separation
            pos = self.mapToScene(x_pos, y_pos)
            wires.append((self.instance.wire_for(port.name), pos, port.width))
        return wires

    def source_wires(self):
        wires = []
        # output ports are sources
        for i, port in self.port_rows("output"):
            x_pos = self.rect().x() + self.rect().width() + self.wire_length
            y_pos = self.rect().y() + self.first_port_offset + i * self.port_separation
            pos = self.mapToScene(x_pos, y_pos)
            wires.append((self.instance.wire_for(port.name), pos, port.width))
        return wires

    def update_size_and_labels(self):
        # ポート数に応じて高さを調整
        module = self.module()
        max_ports = 0
        if module:
            max_ports = max(len(module.inputs), len(module.outputs))
        self.setRect(self.rect().x(), self.rect().y(), 150,
                     self.first_port_offset + max_ports * self.port_separation)

    def mouseDoubleClickEvent(self, event):
        if self.main_window is None:
            return
        self.main_window.editInstance(self)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        snap_selection(self)

    def paint(self, painter, option, widget=None):
        # 定義が見つからないインスタンスは色を変えて示す
        missing = self.module() is None
        self.setBrush(QtGui.QBrush(QtGui.QColor(
            MISSING_MODULE_COLOR if missing else BLOCK_COLOR)))

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
        painter.drawText(self.rect().x() + 5, self.rect().y() + 20,
                         self.instance.module_name)

        # インスタンス名のフォント設定
        instance_font = painter.font()
        instance_font.setBold(True)  # 太字に設定
        instance_font.setPointSize(fontsize)  # フォントサイズを大きく設定（例: +4ポイント）
        painter.setFont(instance_font)
        painter.drawText(self.rect().x() + 5, self.rect().y() - 5,
                         self.instance.name)

        painter.setPen(QtGui.QPen(QtGui.QColor(TEXT_COLOR)))
        font = painter.font()
        font.setBold(False)  # 通常のフォントに戻す

        # 入力ポート名とワイヤーの描画

        painter.setFont(font)
        port_separation = self.port_separation
        for i, port in self.port_rows("input"):
            name, width = port.name, port.width
            wire = self.instance.wire_for(name)
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
        for i, port in self.port_rows("output"):
            name, width = port.name, port.width
            wire = self.instance.wire_for(name)
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
        # ワイヤーは updateWires() のたびに全部作り直すので、選択させない。
        # 選んでも次の更新で消えるうえ、矩形選択や矢印キー移動に混ざる
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
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
    """グリッドとキャンバス枠を描くビュー。

    どちらも画面上の目安なので、ビュー側に描く。scene.render() はビューの
    drawBackground / drawForeground を呼ばないため、印刷には出ない。
    """

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.main_window = parent
        self.show_grid = True
        self.show_canvas_border = True

        # 空白からのドラッグで矩形選択。アイテム上のドラッグは移動のまま。
        # 判定は既定の IntersectsItemShape のままにする。BlockItem.boundingRect()
        # はワイヤー用に左右へ 100 広げてあるので、BoundingRect 判定にすると
        # 本体から離れたところをかすめただけで掴んでしまう
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setRubberBandSelectionMode(QtCore.Qt.IntersectsItemShape)

        # 左ドラッグを矩形選択に取られるので、中ボタンで画面を掴んで動かす
        self._pan_origin = None

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self._pan_origin = event.position().toPoint()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None:
            point = event.position().toPoint()
            delta = point - self._pan_origin
            self._pan_origin = point
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton and self._pan_origin is not None:
            self._pan_origin = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def setShowGrid(self, visible):
        self.show_grid = visible
        self.viewport().update()

    def setShowCanvasBorder(self, visible):
        self.show_canvas_border = visible
        self.viewport().update()

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return

        # 縮小しすぎたときに線を敷き詰めない
        scale = self.transform().m11()
        draw_minor = GRID_SIZE * scale >= GRID_MIN_PIXELS
        major_step = GRID_SIZE * GRID_MAJOR_EVERY
        if major_step * scale < GRID_MIN_PIXELS:
            return

        minor_lines, major_lines = [], []

        x = math.floor(rect.left() / GRID_SIZE) * GRID_SIZE
        while x <= rect.right():
            line = QtCore.QLineF(x, rect.top(), x, rect.bottom())
            if x % major_step == 0:
                major_lines.append(line)
            elif draw_minor:
                minor_lines.append(line)
            x += GRID_SIZE

        y = math.floor(rect.top() / GRID_SIZE) * GRID_SIZE
        while y <= rect.bottom():
            line = QtCore.QLineF(rect.left(), y, rect.right(), y)
            if y % major_step == 0:
                major_lines.append(line)
            elif draw_minor:
                minor_lines.append(line)
            y += GRID_SIZE

        # 太さ 0 は拡大率によらず 1px (コスメティックペン)
        if minor_lines:
            painter.setPen(QtGui.QPen(QtGui.QColor(GRID_COLOR), 0))
            painter.drawLines(minor_lines)
        if major_lines:
            painter.setPen(QtGui.QPen(QtGui.QColor(GRID_MAJOR_COLOR), 0))
            painter.drawLines(major_lines)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self.show_canvas_border:
            return
        pen = QtGui.QPen(QtGui.QColor(CANVAS_BORDER_COLOR), 0, QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(self.sceneRect())

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
        openAction.setShortcut(QtGui.QKeySequence.Open)
        openAction.triggered.connect(self.openDiagram)
        fileMenu.addAction(openAction)

        saveAction = QtGui.QAction("上書き保存", self)
        saveAction.setShortcut(QtGui.QKeySequence.Save)
        saveAction.triggered.connect(self.saveDiagram)
        fileMenu.addAction(saveAction)

        saveAsAction = QtGui.QAction("名前を付けて保存", self)
        saveAsAction.setShortcut(QtGui.QKeySequence.SaveAs)
        saveAsAction.triggered.connect(self.saveDiagramAs)
        fileMenu.addAction(saveAsAction)

        exportVerilogAction = QtGui.QAction("Verilogを出力", self)
        exportVerilogAction.triggered.connect(self.exportVerilog)
        fileMenu.addAction(exportVerilogAction)

        printAction = QtGui.QAction("印刷", self)
        printAction.setShortcut(QtGui.QKeySequence.Print)
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

        duplicateAction = QtGui.QAction("選択したブロックを複製", self)
        duplicateAction.setShortcut(QtGui.QKeySequence("Ctrl+D"))
        duplicateAction.triggered.connect(self.duplicateSelectedBlocks)
        diagramMenu.addAction(duplicateAction)

        editModuleDefAction = QtGui.QAction("モジュール定義…", self)
        editModuleDefAction.triggered.connect(self.editModuleDefinition)
        diagramMenu.addAction(editModuleDefAction)

        deleteBlockAction = QtGui.QAction("サブモジュール削除", self)
        deleteBlockAction.triggered.connect(self.deleteSelectedBlock)
        diagramMenu.addAction(deleteBlockAction)
        
        connectWiresAction = QtGui.QAction("Update wires (debug)", self)
        connectWiresAction.triggered.connect(self.updateWires)
        diagramMenu.addAction(connectWiresAction)
        
        # ショートカットキーの設定
        deleteBlockAction.setShortcut(QtGui.QKeySequence.Delete)

        # 表示メニュー
        viewMenu = menubar.addMenu("表示")

        self.showGridAction = QtGui.QAction("グリッドを表示", self, checkable=True)
        self.showGridAction.setChecked(True)
        self.showGridAction.toggled.connect(self.view.setShowGrid)
        viewMenu.addAction(self.showGridAction)

        self.showBorderAction = QtGui.QAction("キャンバス枠を表示", self, checkable=True)
        self.showBorderAction.setChecked(True)
        self.showBorderAction.toggled.connect(self.view.setShowCanvasBorder)
        viewMenu.addAction(self.showBorderAction)

        fitAction = QtGui.QAction("キャンバス全体を表示", self)
        fitAction.triggered.connect(self.fitCanvas)
        viewMenu.addAction(fitAction)

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
        
        # モジュール定義はブロックではなく設計側が持つ。
        # 位置と接続はシーンのアイテムが持ち、定義だけをここで共有する
        self.design = netlist.Design()

        # モジュール名をシーンに追加
        self.module_name_item = ModuleNameItem("ModuleName", main_window=self)
        self.scene.addItem(self.module_name_item)
        self.wires_to_hide = [] # add names of wires to hide

        self.current_file_path = None
        self.setCurrentFile(None)
        self.updateSceneRect()

    # -- キャンバス ---------------------------------------------------------

    def updateSceneRect(self):
        """置かれている要素の範囲にキャンバスを合わせる。

        sceneRect を指定しないと、QGraphicsScene は過去に置かれた全アイテムの
        外接矩形を保持し続けて縮まない。毎回入れ直すことで広がりも縮みも追う。
        """
        rect = self.scene.itemsBoundingRect()
        if rect.isNull():
            rect = QtCore.QRectF(0, 0, 400, 300)

        left = math.floor((rect.left() - CANVAS_MARGIN) / GRID_SIZE) * GRID_SIZE
        top = math.floor((rect.top() - CANVAS_MARGIN) / GRID_SIZE) * GRID_SIZE
        right = math.ceil((rect.right() + CANVAS_MARGIN) / GRID_SIZE) * GRID_SIZE
        bottom = math.ceil((rect.bottom() + CANVAS_MARGIN) / GRID_SIZE) * GRID_SIZE

        self.scene.setSceneRect(left, top, right - left, bottom - top)
        self.view.viewport().update()   # 枠を描き直す
        self.showCanvasSize()

    def showCanvasSize(self):
        rect = self.scene.sceneRect()
        self.statusBar().showMessage(
            f"キャンバス {int(rect.width())} × {int(rect.height())}"
            f"    グリッド {GRID_SIZE}")

    def fitCanvas(self):
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        self.view.viewport().update()

    # -- ファイル -----------------------------------------------------------

    def setCurrentFile(self, file_path):
        self.current_file_path = file_path
        name = Path(file_path).name if file_path else "(未保存)"
        self.setWindowTitle(f"{name} - {WINDOW_TITLE}")
    
    def ports(self, is_input=None):
        """トップのポートを、図の上から下の順で返す。

        scene.items() は z 順 (ほぼ挿入の逆) で返すので、そのまま使うと
        並びが逆さまになる。位置で並べ直す。
        """
        items = [item for item in self.scene.items() if isinstance(item, PortItem)]
        if is_input is not None:
            items = [item for item in items if item.is_input == is_input]
        items.sort(key=lambda item: (item.pos().y(), item.pos().x()))
        return items

    def editModule(self):
        module_data = {
            "module_name": self.module_name_item.toPlainText(),
            "inputs": [(item.name, item.width, item.name in self.wires_to_hide)
                       for item in self.ports(is_input=True)],
            "outputs": [(item.name, item.width)
                        for item in self.ports(is_input=False)],
        }
        dialog = ModuleDialog(module_data=module_data)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        data = dialog.get_data()
        self.module_name_item.setPlainText(data["module_name"])

        positions = {}  # 既にあるポートは置き場所を変えない
        for item in self.ports():
            positions[item.name] = item.pos()
            self.scene.removeItem(item)

        left, right = self.portColumns()
        top = self.contentRect().top()

        for column, entries, is_input in ((left, data["inputs"], True),
                                          (right, data["outputs"], False)):
            posy = top
            for entry in entries:
                name, width = entry[0], entry[1]
                port = PortItem(0, 0, name, width, is_input=is_input,
                                main_window=self)
                if name in positions:
                    port.setPos(positions[name])
                else:
                    port.setPos(column, posy)
                    snap_to_grid(port)
                self.scene.addItem(port)
                posy += 50

        self.wires_to_hide = dialog.get_hidden_portwires()
        self.updateWires()

    # -- 新しい要素の置き場所 -----------------------------------------------

    def contentRect(self):
        """今ある要素 (ブロックとポート) が占める範囲。

        itemsBoundingRect() はワイヤー用の余白まで含むので、本体だけを見る。
        """
        rects = [block.mapRectToScene(block.rect()) for block in self.blocks()]
        rects += [port.mapRectToScene(QtCore.QRectF(0, 0, 40, 10))
                  for port in self.ports()]
        if not rects:
            return QtCore.QRectF(0, 0, 400, 200)

        rect = rects[0]
        for other in rects[1:]:
            rect = rect.united(other)
        return rect

    def portColumns(self):
        """入力ポートと出力ポートを置く x 座標。

        サブモジュールのかたまりの左右に付ける。固定値だと、図が小さいときに
        本体からうんと離れた場所に置かれてしまう。
        """
        rects = [block.mapRectToScene(block.rect()) for block in self.blocks()]
        if rects:
            left = min(rect.left() for rect in rects)
            right = max(rect.right() for rect in rects)
        else:
            content = self.contentRect()
            left, right = content.left(), content.right()
        return left - PORT_COLUMN_GAP, right + PORT_COLUMN_GAP

    def freePosition(self, width, height):
        """他の要素と重ならない置き場所を、今ある要素のそばで探す。"""
        content = self.contentRect()
        x, y = content.left() + NEW_ITEM_STEP, content.top() + NEW_ITEM_STEP

        for _ in range(200):
            area = QtCore.QRectF(x, y, width, height)
            taken = [item for item in self.scene.items(area, QtCore.Qt.IntersectsItemShape)
                     if isinstance(item, (BlockItem, PortItem))]
            if not taken:
                break
            x += NEW_ITEM_STEP
            y += NEW_ITEM_STEP
            if x > content.right():
                x = content.left() + NEW_ITEM_STEP
                y += NEW_ITEM_STEP

        return (round(x / GRID_SIZE) * GRID_SIZE,
                round(y / GRID_SIZE) * GRID_SIZE)


    # -- インスタンスとモジュール定義 ---------------------------------------

    def blocks(self):
        return [item for item in self.scene.items() if isinstance(item, BlockItem)]

    def syncInstances(self):
        """シーンにあるブロックの内容を design.instances に写す。

        定義の変更を全インスタンスへ反映する処理は design 側にあるので、
        ダイアログを開く前に実体を揃えておく。
        """
        self.design.instances = [block.instance for block in self.blocks()]

    def addBlock(self):
        self.syncInstances()
        dialog = InstanceDialog(self, design=self.design)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            self.refreshBlocks()
            return

        data = dialog.get_data()
        x, y = self.freePosition(150, 100)
        instance = netlist.Instance(data["module_name"], data["instance_name"],
                                    x, y, data["connections"])
        block = BlockItem(0, 0, 150, 50, instance=instance, main_window=self)
        block.setPos(x, y)
        self.scene.addItem(block)
        self.refreshBlocks()

    def editInstance(self, block):
        self.syncInstances()
        dialog = InstanceDialog(self, design=self.design, instance=block.instance)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            self.refreshBlocks()
            return

        data = dialog.get_data()
        block.instance.module_name = data["module_name"]
        block.instance.name = data["instance_name"]
        block.instance.connections = data["connections"]
        self.refreshBlocks()

    def editModuleDefinition(self):
        """モジュールを選んで定義を編集する。変更は全インスタンスに効く。"""
        self.syncInstances()
        if not self.design.modules:
            QtWidgets.QMessageBox.information(
                self, "モジュール定義", "まだモジュールがありません。")
            return

        name, ok = QtWidgets.QInputDialog.getItem(
            self, "モジュール定義", "編集するモジュール:",
            sorted(self.design.modules), 0, False)
        if not ok:
            return

        module = self.design.modules[name]
        dialog = ModuleDefDialog(self, module=module,
                                 taken_names=self.design.modules)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return

        apply_module_change(self.design, name, dialog.get_module(),
                            dialog.get_renames())
        self.refreshBlocks()

    def duplicateSelectedBlocks(self):
        """同じモジュールの別インスタンスを作る。接続は引き継がない。"""
        self.syncInstances()
        created = []
        for block in self.scene.selectedItems():
            if not isinstance(block, BlockItem):
                continue
            instance = netlist.Instance(
                block.instance.module_name,
                self.design.next_instance_name(block.instance.module_name),
                block.instance.x + 40, block.instance.y + 40)
            self.design.instances.append(instance)
            copy = BlockItem(0, 0, 150, 50, instance=instance, main_window=self)
            copy.setPos(block.x() + 40, block.y() + 40)
            self.scene.addItem(copy)
            created.append(copy)

        if created:
            self.scene.clearSelection()
            for block in created:
                block.setSelected(True)
            self.refreshBlocks()

    def refreshBlocks(self):
        """定義が変わったあとにブロックの大きさと表示を作り直す。"""
        for block in self.blocks():
            block.update_size_and_labels()
            block.update()
        self.syncInstances()
        self.updateWires()

    def deleteSelectedBlock(self):
        blocks = [item for item in self.scene.selectedItems()
                  if isinstance(item, BlockItem)]
        if not blocks:
            return

        names = "\n".join(f"・{block.instance.name}" for block in blocks)
        reply = QtWidgets.QMessageBox.question(
            self, '確認', f"次の {len(blocks)} 個を削除しますか?\n\n{names}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return

        for block in blocks:
            self.scene.removeItem(block)
        self.refreshBlocks()

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
            # Wire 名が空欄のポートは接続先未定。空文字列同士を同名として
            # 結線してしまわないように、ここで除く
            if not src_wire:
                continue
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

        # 要素が動いたあとなので、キャンバスの範囲を取り直す
        self.updateSceneRect()

    def buildDesign(self):
        """シーンの内容を netlist.Design にまとめる。

        モジュール定義は self.design が持ち、位置と接続はシーンから拾う。
        保存と Verilog 出力の両方から使う。
        """
        design = netlist.Design(
            name=self.module_name_item.toPlainText(),
            name_pos=(self.module_name_item.pos().x(),
                      self.module_name_item.pos().y()),
            modules=self.design.modules,
            wires_to_hide=list(self.wires_to_hide))

        for item in self.scene.items():
            if isinstance(item, PortItem):
                port = netlist.TopPort(item.name, item.width, item.is_input,
                                       item.pos().x(), item.pos().y())
                (design.inputs if port.is_input else design.outputs).append(port)
            elif isinstance(item, BlockItem):
                item.instance.x = item.pos().x()
                item.instance.y = item.pos().y()
                design.instances.append(item.instance)

        design.inputs.sort(key=lambda port: port.y)
        design.outputs.sort(key=lambda port: port.y)
        design.instances.sort(key=lambda inst: (inst.x, inst.y))
        return design

    def collectItemsData(self):
        """保存形式 (形式2) の dict にする。"""
        return netlist.dump(self.buildDesign())

    def saveDiagram(self):
        """上書き保存。保存先が未定なら名前を付けて保存に落とす。"""
        if not self.current_file_path:
            return self.saveDiagramAs()
        self.writeDiagram(self.current_file_path)

    def saveDiagramAs(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "名前を付けて保存", self.current_file_path or "", "JSON Files (*.json)")
        if file_path:
            self.writeDiagram(file_path)

    def writeDiagram(self, file_path):
        items_data = self.collectItemsData()
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(items_data, file, indent=4)
        self.setCurrentFile(file_path)
        self.statusBar().showMessage(f"保存しました: {file_path}", 3000)

    def exportVerilog(self):
        try:
            text, warnings = verilog.generate(self.collectItemsData())
        except verilog.GenerationError as error:
            QtWidgets.QMessageBox.warning(self, "Verilog出力", str(error))
            return

        default_name = f"{self.module_name_item.toPlainText()}.v"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Verilogを出力", default_name, "Verilog Files (*.v)")
        if not file_path:
            return

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(text)

        if warnings:
            QtWidgets.QMessageBox.information(self, "Verilog出力",
                                              "出力しました。以下を確認してください。\n\n" + "\n".join(warnings))

    def openDiagram(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "ブロック図を開く", "", "JSON Files (*.json)")
        if not file_path:
            return

        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)

        design, warnings = netlist.load(data)
        self.loadDesign(design)
        self.setCurrentFile(file_path)

        if warnings:
            QtWidgets.QMessageBox.information(
                self, "読み込み",
                "読み込みました。以下を確認してください。\n\n"
                + "\n".join(f"・{message}" for message in warnings))

    def loadDesign(self, design):
        """Design の内容でシーンを作り直す。"""
        self.scene.clear()
        self.design = design
        self.wires_to_hide = list(design.wires_to_hide)

        self.module_name_item = ModuleNameItem(design.name, main_window=self)
        self.module_name_item.setPos(*design.name_pos)
        self.scene.addItem(self.module_name_item)

        for port in design.inputs + design.outputs:
            item = PortItem(0, 0, port.name, port.width, port.is_input,
                            main_window=self)
            item.setPos(port.x, port.y)
            self.scene.addItem(item)

        for instance in design.instances:
            block = BlockItem(0, 0, 150, 50, instance=instance, main_window=self)
            block.setPos(instance.x, instance.y)
            self.scene.addItem(block)

        self.refreshBlocks()

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