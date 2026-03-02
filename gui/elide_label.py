# elide_label.py

from PySide6.QtWidgets import QLabel, QStyleOptionFrame, QStyle
from PySide6.QtGui import QPainter
from PySide6.QtCore import Qt, QSize

class ElideLabel(QLabel):
    _elideMode = Qt.TextElideMode.ElideRight

    def elideMode(self):
        return self._elideMode

    def setElideMode(self, mode):
        if self._elideMode != mode and mode != Qt.TextElideMode.ElideNone:
            self._elideMode = mode
            self.updateGeometry()

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        hint = self.fontMetrics().boundingRect(self.text()).size()
        cm = self.contentsMargins()        
        margin = self.margin() * 2
        return QSize(
            min(100, hint.width()) + cm.left() + cm.right() + margin, 
            min(self.fontMetrics().height(), hint.height()) + cm.top() + cm.bottom() + margin
        )
    
    def paintEvent(self, event):
        with QPainter(self) as qp:
            opt = QStyleOptionFrame()
            self.initStyleOption(opt)
            self.style().drawControl(QStyle.CE_ShapedFrame, opt, qp, self)
            #cm = self.contentsMargins()
            margin = self.margin()
            try:
                # since Qt >= 5.11
                m = self.fontMetrics().horizontalAdvance('x') / 2 - margin
            except:
                m = self.fontMetrics().width('x') / 2 - margin
            r = self.contentsRect().adjusted(
                margin + m,  margin, -(margin + m), -margin)
            qp.drawText(r, self.alignment(), 
                self.fontMetrics().elidedText(
                    self.text(), self.elideMode(), r.width()))
            
    def setText(self, text: str):
        super().setText(text)
        self._updateTooltip()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._updateTooltip()

    def _updateTooltip(self):
        text = self.text()
        elided = self.fontMetrics().elidedText(text, self._elideMode, self.contentsRect().width())
        if elided != text:
            self.setToolTip(text)
        else:
            self.setToolTip("")    
