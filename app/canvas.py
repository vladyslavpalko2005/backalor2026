from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets
from .main import AnnotationCanvas


class EditorCanvas(AnnotationCanvas):
    """Original-pixel coordinates with drawing, pan, zoom and corner resize."""
    selected = QtCore.pyqtSignal(int)
    boxEdited = QtCore.pyqtSignal(int, object)

    def __init__(self):
        super().__init__()
        self._edit_item = None
        self._edit_start = None
        self._edit_rect = None
        self._resizing = False
        self._resize_corner = None
        self._pan_start = None
        self._fitted = True
        self._selected_id = None
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor('#e7ebe4'))
        # Foreground handles extend beyond item bounds. Partial scroll reuse
        # leaves their old pixels behind when panning or editing a rectangle.
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def set_image(self, qimage):
        self._cancel_gesture()
        transform = self.transform()
        previous_size = self.sceneRect().size()
        super().set_image(qimage)
        if qimage and previous_size == self.sceneRect().size():
            self.setTransform(transform)

    def _cancel_gesture(self):
        self._edit_item=None
        self._edit_rect=None
        self._edit_start=None
        self._pan_start=None
        self._drawing=False
        self._temp_rect=None

    def clear_annotations(self):
        self._cancel_gesture()
        super().clear_annotations()

    def resizeEvent(self, event):
        QtWidgets.QGraphicsView.resizeEvent(self, event)
        if self._fitted and self._pixmap_item:
            self.fit_image()

    def fit_image(self):
        self._fitted = True
        self.fitInView(self.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor):
        next_scale = self.transform().m11()*factor
        if 0.01 <= next_scale <= 30:
            self._fitted = False
            self.scale(factor, factor)

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1/1.2)
        event.accept()

    def highlight_item(self, annotation_id):
        self._selected_id = annotation_id
        super().highlight_item(annotation_id)
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.MiddleButton or (event.button()==QtCore.Qt.MouseButton.LeftButton and event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            self._pan_start = event.position().toPoint()
            self.viewport().setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept();return
        if not self._drawing_enabled and event.button() == QtCore.Qt.MouseButton.LeftButton:
            position = self.mapToScene(event.position().toPoint())
            selected = next((i for i in self.scene().items() if isinstance(i,QtWidgets.QGraphicsRectItem) and i.data(0)==self._selected_id and i.isVisible()),None)
            corner = self._near_corner(selected,position) if selected else None
            candidates = [selected] if corner else [i for i in self.scene().items(position) if isinstance(i, QtWidgets.QGraphicsRectItem) and isinstance(i.data(0), int)]
            if candidates:
                self._edit_item = min(candidates, key=lambda i: i.rect().width()*i.rect().height())
                self._edit_rect = QtCore.QRectF(self._edit_item.rect())
                self._edit_start = position
                self._resize_corner = corner
                self._resizing = self._resize_corner is not None
                self.selected.emit(self._edit_item.data(0))
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_start is not None:
            point=event.position().toPoint();delta=point-self._pan_start;self._pan_start=point
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y())
            self._fitted=False;event.accept();return
        if self._edit_item is not None:
            position = self.mapToScene(event.position().toPoint())
            rect = QtCore.QRectF(self._edit_rect)
            if self._resizing:
                getattr(rect,'set'+self._resize_corner)(position)
                rect = rect.normalized()
            else:
                rect.translate(position-self._edit_start)
            self._edit_item.setRect(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_start is not None:
            self._pan_start=None;self.viewport().unsetCursor();event.accept();return
        if self._edit_item is not None:
            item, old = self._edit_item, self._edit_rect
            rect = QtCore.QRectF(item.rect())
            item.setRect(old)
            self._edit_item = None
            if rect != old:
                self.boxEdited.emit(item.data(0), rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _near_corner(self,item,position):
        tolerance=12/max(self.transform().m11(),0.01)
        for name in ('TopLeft','TopRight','BottomLeft','BottomRight'):
            point=getattr(item.rect(),name[0].lower()+name[1:])()
            if (position-point).manhattanLength()<=tolerance:return name
        return None

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        for item in self.scene().items():
            if isinstance(item, QtWidgets.QGraphicsRectItem) and item.isVisible() and item.data(0) == self._selected_id:
                size = 8/max(self.transform().m11(), 0.01)
                painter.setPen(QtGui.QPen(QtGui.QColor('#172c51'), 0))
                painter.setBrush(QtGui.QColor('white'))
                for point in (item.rect().topLeft(), item.rect().topRight(), item.rect().bottomLeft(), item.rect().bottomRight()):
                    painter.drawRect(QtCore.QRectF(point.x()-size/2, point.y()-size/2, size, size))
                break
