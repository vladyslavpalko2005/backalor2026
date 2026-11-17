"""Small consistent outline icons drawn as native vectors, no font glyphs."""
from PyQt6 import QtCore,QtGui


def icon(name,color='#d7e4db'):
    pixmap=QtGui.QPixmap(24,24);pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter=QtGui.QPainter(pixmap);painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen=QtGui.QPen(QtGui.QColor(color),1.7);pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin);pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap);painter.setPen(pen)
    if name=='scans':
        painter.drawRoundedRect(QtCore.QRectF(5,3,14,18),2,2);painter.drawLine(8,8,16,8);painter.drawLine(8,12,16,12);painter.drawLine(8,16,13,16)
    elif name=='annotate':
        painter.drawRoundedRect(QtCore.QRectF(4,4,16,16),2,2);painter.drawRect(QtCore.QRectF(8,8,8,8))
    elif name=='symbols':
        for x,y in [(4,4),(14,4),(4,14),(14,14)]:painter.drawRoundedRect(QtCore.QRectF(x,y,6,6),1,1)
    elif name=='review':
        painter.drawEllipse(QtCore.QRectF(3,3,18,18));painter.drawLine(7,12,10,15);painter.drawLine(10,15,17,8)
    elif name=='models':
        for y,x in [(6,8),(12,16),(18,10)]:
            painter.drawLine(3,y,21,y);painter.setBrush(QtGui.QColor('#182820'));painter.drawEllipse(QtCore.QRectF(x-2,y-2,4,4));painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    else:
        painter.drawRoundedRect(QtCore.QRectF(3,7,18,13),2,2);painter.drawLine(4,7,4,4);painter.drawLine(4,4,10,4);painter.drawLine(10,4,13,7)
    painter.end();return QtGui.QIcon(pixmap)
