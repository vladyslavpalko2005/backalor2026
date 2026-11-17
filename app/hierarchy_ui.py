"""A single hierarchy view; source annotation IDs remain stable."""
from PyQt6 import QtCore,QtWidgets

COPY={
 'search':('Пошук у дереві…','Hľadať v strome…'),
 'delete':('Видалити гілку','Odstrániť vetvu'),
 'duplicate':('Дублювати гілку','Duplikovať vetvu'),
 'caption':('Група / підпис','Skupina / popis'),
 'reference':('Пов’язаний відкритий текст','Prepojený otvorený text'),
 'bulk':('Змінити вибрані…','Upraviť vybrané…'),
 'unchanged':('Не змінювати','Nemeniť'),
 'apply':('Застосувати','Použiť'),
 'selection':('Вибрано L3: {count}. Зміни стосуються лише поточної сторінки й скасовуються однією дією.','Vybrané L3: {count}. Zmeny platia len pre aktuálnu stranu a dajú sa vrátiť jedným krokom.'),
 'choose':('Спочатку вибери рядки L3 (Cmd/Ctrl або Shift).','Najprv vyber riadky L3 (Cmd/Ctrl alebo Shift).'),
 'changed':('Змінено анотацій: {count}','Zmenené anotácie: {count}'),
 'invalid_transcription_reference':('Некоректний зв’язок із текстом','Neplatný odkaz na text'),
}


def translate(workspace,key):return COPY[key][0 if workspace.language=='uk' else 1]


class HierarchyPanel(QtWidgets.QWidget):
    def __init__(self,workspace):
        super().__init__();self.workspace=workspace;self.nodes={}
        layout=QtWidgets.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.search=QtWidgets.QLineEdit();self.search.textChanged.connect(self.filter);layout.addWidget(self.search)
        self.tree=QtWidgets.QTreeWidget();self.tree.setHeaderHidden(True);self.tree.setMinimumHeight(180);self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self.select)
        row=QtWidgets.QHBoxLayout();self.buttons={}
        for key,callback in [('duplicate',lambda:workspace.duplicate_current_annotation()),('delete',lambda:workspace.delete_annotation(workspace._active_annotation))]:
            button=QtWidgets.QPushButton();button.clicked.connect(lambda checked=False,fn=callback:workspace._guard(fn));self.buttons[key]=button;row.addWidget(button)
        layout.addLayout(row);layout.addWidget(self.tree,1);self.translate()
    def translate(self):
        self.search.setPlaceholderText(translate(self.workspace,'search'))
        for key,button in self.buttons.items():button.setText(translate(self.workspace,key))
    def rebuild(self):
        expanded={key:node.isExpanded() for key,node in self.nodes.items()};had_nodes=bool(self.nodes)
        blocker=QtCore.QSignalBlocker(self.tree);self.tree.clear();self.nodes={}
        for item in sorted(self.workspace.annotation_items,key=lambda item:({'L1':1,'L2':2,'L3':3}.get(item.level,4),item.id)):
            caption=item.label if item.label not in ('symbol','not_symbol') else ''
            content=item.transcription or item.symbol_code
            node=QtWidgets.QTreeWidgetItem([f'{item.level} #{item.id}'+(' · '+caption if caption else '')+(' — '+content if content else '')])
            node.setData(0,QtCore.Qt.ItemDataRole.UserRole,item.id)
            node.setToolTip(0,' · '.join(value for value in (caption,content,item.notes) if value))
            parent=self.nodes.get(item.parent_id)
            if parent is None:self.tree.addTopLevelItem(node)
            else:parent.addChild(node)
            self.nodes[item.id]=node;node.setExpanded(expanded.get(item.id,not had_nodes))
        active=self.nodes.get(self.workspace._active_annotation)
        if active:self.tree.setCurrentItem(active)
        del blocker;self.filter(self.search.text())
    def select(self,current,previous):
        if current is None:return
        self.workspace._pending_selection=(current.data(0,QtCore.Qt.ItemDataRole.UserRole),self.workspace.current_image_path)
        if hasattr(self.workspace,'selection_timer'):self.workspace.selection_timer.start(0)
    def highlight(self,annotation_id):
        node=self.nodes.get(annotation_id)
        if node:
            blocker=QtCore.QSignalBlocker(self.tree);self.tree.setCurrentItem(node)
            parent=node.parent()
            while parent:parent.setExpanded(True);parent=parent.parent()
            self.tree.scrollToItem(node);del blocker
    def filter(self,query):
        query=query.casefold()
        def visit(node):
            child_matches=[visit(node.child(index)) for index in range(node.childCount())]
            match=query in (node.text(0)+' '+node.toolTip(0)).casefold() or any(child_matches)
            node.setHidden(not match)
            if query and any(child_matches):node.setExpanded(True)
            return match
        for index in range(self.tree.topLevelItemCount()):visit(self.tree.topLevelItem(index))
