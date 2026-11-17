from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets


class ImageView(QtWidgets.QGraphicsView):
    viewChanged = QtCore.pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setBackgroundBrush(QtGui.QColor('#e7ebe4'))
        self.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pixmap = None
        self._fitted = True
        self._syncing = False
        self._panning = False
        self.setMinimumSize(150,180)

    def set_image(self,image,reset=False):
        previous = self.sceneRect().size()
        transform = self.transform()
        center = self.mapToScene(self.viewport().rect().center())
        self.scene().clear(); self._pixmap = None
        if image is None:
            self.scene().setSceneRect(QtCore.QRectF()); return
        self._pixmap = self.scene().addPixmap(QtGui.QPixmap.fromImage(image))
        self.setSceneRect(QtCore.QRectF(0,0,image.width(),image.height()))
        if reset or self._fitted:
            self.fit_image()
        else:
            self.setTransform(transform)
            self.centerOn(center.x()*image.width()/max(1,previous.width()),center.y()*image.height()/max(1,previous.height()))

    def fit_image(self):
        self._fitted = True
        if self._pixmap:
            self.fitInView(self.sceneRect(),QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            self.viewChanged.emit()

    def zoom(self,factor):
        if not self._pixmap: return
        scale = self.transform().m11()*factor
        if 0.005 <= scale <= 16:
            self._fitted = False; self.scale(factor,factor); self.viewChanged.emit()

    def actual_size(self):
        if self._pixmap:
            self._fitted=False; self.resetTransform(); self.viewChanged.emit()

    def wheelEvent(self,event):
        self.zoom(1.2 if event.angleDelta().y()>0 else 1/1.2);event.accept()

    def mouseMoveEvent(self,event):
        super().mouseMoveEvent(event)
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._fitted=False;self.viewChanged.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self._fitted and self._pixmap: self.fit_image()

    def scrollContentsBy(self,dx,dy):
        super().scrollContentsBy(dx,dy)
        if hasattr(self,'_syncing') and not self._syncing and self._panning: self.viewChanged.emit()

    def mousePressEvent(self,event):
        self._panning=True;super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self._panning=False

    def synchronize_from(self,other):
        if not self._pixmap or not other._pixmap: return
        self._syncing=True
        try:
            center=other.mapToScene(other.viewport().rect().center())
            ratio=self.sceneRect().width()/max(1,other.sceneRect().width())
            transform=QtGui.QTransform(other.transform());transform.scale(1/ratio,1/ratio)
            self.setTransform(transform)
            self.centerOn(center.x()*ratio,center.y()*self.sceneRect().height()/max(1,other.sceneRect().height()))
            self._fitted=other._fitted
        finally: self._syncing=False
