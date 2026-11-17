"""Backalor's research workbench: dark navigation, light surfaces, forest green."""
from pathlib import Path
from PyQt6 import QtGui,QtWidgets

COLORS={'ink':'#202e26','secondary':'#56665c','accent':'#206b49','accent_hover':'#185639',
        'rail':'#182820','paper':'#f7f8f5','surface':'#ffffff','line':'#d8e0d8','selection':'#deeee2'}

STYLE="""
QWidget { color: #202e26; font-size: 13px; }
QMainWindow, QDialog { background: #f7f8f5; }
QFrame#navigationRail, QFrame#loginBrand { background: #182820; border: none; }
QLabel#brandWordmark { color: #f1f5ef; font-size: 18px; font-weight: 600; letter-spacing: 2px; background: transparent; }
QLabel#brandMuted { color: #b9cfc0; background: transparent; }
QLabel#loginHero { color: #f1f5ef; font-size: 30px; font-weight: 600; background: transparent; }
QLabel#screenTitle { font-size: 27px; font-weight: 600; color: #20392b; padding: 4px 0; }
QLabel#secondaryText, QLabel#mutedLabel, QLabel#statusLabel { color: #56665c; }
QLabel#serviceReady { color: #206b49; }
QToolButton#railButton { text-align: left; padding: 11px 12px; color: #d7e4db; background: transparent; border: none; border-radius: 7px; }
QToolButton#railButton:hover { background: #263e31; }
QToolButton#railButton:checked { background: #2d523d; color: #ffffff; font-weight: 600; }
QToolButton#railButton:disabled { color: #8fa998; }
QPushButton#railButton, QPushButton#railProfile { text-align: left; color: #d7e4db; background: #21382b; border: 1px solid #3e5947; padding: 11px 12px; border-radius: 7px; }
QPushButton#railButton:hover, QPushButton#railProfile:hover { background: #2d4937; }
QPushButton#railActive { text-align: left; color: #ffffff; background: #2d523d; border: none; padding: 13px; font-weight: 600; }
QWidget#appHeader { background: transparent; border: none; }
QLabel#appBrand { font-size: 23px; font-weight: 600; color: #20392b; }
QLabel#emptyTitle { font-size: 22px; font-weight: 600; padding: 10px; }
QLabel#workflowHelp { background: #e9f2e9; color: #274d35; border-radius: 6px; }
QLabel#panelTitle, QLabel#previewTitle { font-weight: 600; color: #354e3d; padding: 5px 0; }
QToolBar { background: #ffffff; border: 1px solid #d8e0d8; border-radius: 7px; padding: 5px; spacing: 5px; }
QToolBar QLabel { background: transparent; color: #56665c; }
QToolButton { color: #334c3c; background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 7px 10px; }
QToolButton:hover { background: #e6eee5; }
QToolButton:checked { background: #deeee2; color: #185639; }
QToolButton:disabled { color: #708575; }
QPushButton { color: #334c3c; background: #ffffff; border: 1px solid #bdcebf; border-radius: 6px; padding: 9px 13px; }
QPushButton:hover { background: #edf4ed; border-color: #8da991; }
QPushButton:pressed { background: #deeee2; }
QPushButton[primary="true"] { color: #ffffff; background: #206b49; border-color: #206b49; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #185639; border-color: #185639; }
QPushButton:disabled { color: #65776a; background: #edf1eb; border-color: #d5dfd4; }
QPushButton#googleButton { background: #ffffff; color: #23372b; border: 1px solid #aabcaa; font-size: 15px; font-weight: 600; padding: 14px 20px; }
QPushButton#googleButton:hover { background: #e9f2e9; border-color: #206b49; }
QPushButton#googleButton:disabled { color: #65776a; background: #edf1eb; }
QPushButton:focus, QToolButton:focus { border: 2px solid #347e55; }
QTabWidget::pane { border: none; background: #ffffff; }
QTabBar::tab { background: transparent; color: #56665c; padding: 11px 16px; border: none; border-bottom: 2px solid transparent; margin-right: 8px; }
QTabBar::tab:selected { color: #185639; border-bottom: 2px solid #206b49; font-weight: 600; }
QTabBar::tab:hover { background: #edf4ed; }
QTabBar::tab:disabled { color: #65776a; }
QGroupBox { border: 1px solid #d8e0d8; border-radius: 7px; margin-top: 14px; padding: 10px 6px 6px; background: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #354e3d; }
QGroupBox:flat { background: transparent; padding-top: 4px; border: none; }
QListWidget, QTableWidget, QTreeWidget, QPlainTextEdit { background: #ffffff; color: #202e26; border: 1px solid #d8e0d8; border-radius: 6px; selection-background-color: #deeee2; selection-color: #163f2b; }
QListWidget::item { padding: 9px 9px; border-radius: 4px; }
QTreeWidget::item { min-height: 29px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #deeee2; color: #163f2b; }
QListWidget::item:hover, QTreeWidget::item:hover { background: #edf4ed; }
QHeaderView::section { background: #f0f4ed; color: #3c5845; padding: 10px; border: none; border-bottom: 1px solid #d8e0d8; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { color: #202e26; background: #ffffff; border: 1px solid #bdcebf; border-radius: 5px; padding: 8px; selection-background-color: #deeee2; selection-color: #163f2b; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #206b49; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { background: #edf1eb; color: #65776a; }
QCheckBox, QRadioButton { color: #334c3c; spacing: 7px; background: transparent; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { background: #ffffff; border: 1px solid #819d87; border-radius: 3px; }
QCheckBox::indicator:checked { background: #206b49; border-color: #206b49; image: url(CHECK_ICON); }
QRadioButton::indicator { background: #ffffff; border: 1px solid #819d87; border-radius: 8px; }
QRadioButton::indicator:checked { background: #206b49; border: 3px solid #b9d2c0; }
QGraphicsView { border: none; background: #e7ebe4; }
QScrollArea { border: none; background: #ffffff; }
QScrollBar:vertical { background: #eef2eb; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #adbfad; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #e0e7dc; width: 4px; }
QStatusBar { border-top: 1px solid #d8e0d8; background: #ffffff; color: #56665c; }
QMenuBar, QMenu { background: #ffffff; color: #334c3c; }
QMenuBar::item, QMenu::item { padding: 7px 11px; }
QMenuBar::item:selected, QMenu::item:selected { background: #deeee2; color: #163f2b; }
QToolTip { background: #20392b; color: #f1f5ef; padding: 6px; border: none; }
QProgressBar { border: none; background: #e3ece2; border-radius: 2px; }
QProgressBar::chunk { background: #206b49; }
"""


def apply_theme(app):
    app.setStyle('Fusion')
    palette=QtGui.QPalette()
    for role,color in {QtGui.QPalette.ColorRole.Window:'#f7f8f5',QtGui.QPalette.ColorRole.WindowText:'#202e26',
        QtGui.QPalette.ColorRole.Base:'#ffffff',QtGui.QPalette.ColorRole.AlternateBase:'#f0f4ed',
        QtGui.QPalette.ColorRole.Text:'#202e26',QtGui.QPalette.ColorRole.Button:'#ffffff',
        QtGui.QPalette.ColorRole.ButtonText:'#334c3c',QtGui.QPalette.ColorRole.Highlight:'#deeee2',
        QtGui.QPalette.ColorRole.HighlightedText:'#163f2b',QtGui.QPalette.ColorRole.PlaceholderText:'#607466',
        QtGui.QPalette.ColorRole.ToolTipBase:'#20392b',QtGui.QPalette.ColorRole.ToolTipText:'#f1f5ef'}.items():palette.setColor(role,QtGui.QColor(color))
    palette.setColor(QtGui.QPalette.ColorGroup.Disabled,QtGui.QPalette.ColorRole.Text,QtGui.QColor('#65776a'))
    app.setPalette(palette);font=app.font();font.setPointSize(10);app.setFont(font)
    app.setStyleSheet(STYLE.replace('CHECK_ICON',(Path(__file__).parent/'assets'/'check.svg').as_posix()))
