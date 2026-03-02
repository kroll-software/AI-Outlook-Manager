# my_qt_extensions.py

from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QTextEdit,
    QSplitterHandle,
    QComboBox
)
from PySide6.QtGui import QIcon, QColor, QPainter, QPixmap
from PySide6.QtCore import Qt, QSize, QMimeData
from PySide6.QtSvg import QSvgRenderer

class DotSplitterHandle(QSplitterHandle):
    def __init__(self, orientation, splitter):
        super().__init__(orientation, splitter)
        self.splitter = splitter  

    def paintEvent(self, event):
        #super().paintEvent(event)        
        
        with QPainter(self) as p:        
            p.setRenderHint(QPainter.Antialiasing)
            color = self.splitter.grip_color()        
            p.setBrush(color)
            p.setPen(Qt.NoPen)

            # Punkte mittig platzieren
            w, h = self.width(), self.height()
            num_points = 5  # Anzahl der Punkte in der Mitte
            dot_spacing = 2  # Abstand zwischen den Punkten
            dot_size = 2            
            
            if self.orientation() == Qt.Vertical:   # teilt oben/unten
                # Berechne den Startpunkt, um die Punkte mittig im Splitter zu platzieren
                start_x = (w - (num_points * dot_spacing + (num_points - 1) * dot_spacing)) // 2
                for i in range(num_points):
                    # Berechne die x-Position für die Punkte
                    x = start_x + i * (dot_size + dot_spacing)  # 4 ist der Durchmesser der Punkte
                    p.drawEllipse(x, h // 2 - 1, dot_size, dot_size)  # 2,2 ist die Größe der Punkte
            else:
                # Berechne den Startpunkt, um die Punkte mittig zu platzieren
                start_y = (h - (num_points * dot_spacing + (num_points - 1) * dot_spacing)) // 2
                for i in range(num_points):
                    # Berechne die y-Position für die Punkte
                    y = start_y + i * (dot_size + dot_spacing)  # 4 ist der Durchmesser der Punkte
                    # Punkte mittig entlang der Breite platzieren
                    p.drawEllipse(w // 2 - 1, y, dot_size, dot_size)  # 2,2 ist die Größe der Punkte        

class DotSplitter(QSplitter):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._grip_color = QColor("#888")  # Standardfarbe (z. B. Rot)

    def createHandle(self):
        return DotSplitterHandle(self.orientation(), self)
    
    # Getter für grip_color
    def grip_color(self):
        return self._grip_color

    # Setter für grip_color
    def set_grip_color(self, color: QColor):
        self._grip_color = color
        self.update()  # Damit das Handle neu gemalt wird

class MyQMainWindow (QMainWindow):{}

class PlainTextEdit(QTextEdit):
    def insertFromMimeData(self, source: QMimeData):
        if source.hasText():
            self.insertPlainText(source.text())  # Nur Text einfügen

def get_colored_svg_icon(svg_path: str, size: QSize, color: QColor) -> QIcon:
    renderer = QSvgRenderer(svg_path)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()

    return QIcon(pixmap)


class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        # Scroll-Ereignis ignorieren
        event.ignore()