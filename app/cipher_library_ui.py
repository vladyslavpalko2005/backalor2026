"""Modeless, project-local candidate library in the existing research workbench."""
from pathlib import Path
import json
from PyQt6 import QtCore, QtWidgets
from .cipher_library import CipherLibrary, build_ciphertext, search_library
from .digitization import build_key

COPY = {
    'title': ('Бібліотека ключів і шифротекстів', 'Knižnica kľúčov a šifrových textov'),
    'intro': ('Додай ключі та шифротексти з проєктів або JSON. Вибери документ: пошук знайде кандидатів іншого типу.', 'Pridaj kľúče a šifrové texty z projektov alebo JSON. Vyber dokument: vyhľadávanie nájde kandidátov druhého typu.'),
    'limits': ('Коди символів мають збігатися між документами. Покриття — частка перевірених токенів, відомих ключу, а не ймовірність правильності. Використовуються лише перевірені дані без помилок; неоднозначності позначено дужками.', 'Kódy symbolov sa musia zhodovať medzi dokumentmi. Pokrytie je podiel overených tokenov známych kľúču, nie pravdepodobnosť správnosti. Používajú sa iba overené údaje bez chýb; nejednoznačnosti sú v zátvorkách.'),
    'key': ('Ключ', 'Kľúč'), 'ciphertext': ('Шифротекст', 'Šifrový text'),
    'current_key': ('Додати ключ проєкту', 'Pridať kľúč projektu'),
    'current_text': ('Додати шифротекст проєкту', 'Pridať šifrový text projektu'),
    'import': ('Імпорт JSON…', 'Importovať JSON…'),
    'query': ('Документ для пошуку', 'Dokument na vyhľadávanie'),
    'search': ('Знайти відповідності', 'Nájsť zhody'),
    'empty': ('Бібліотека порожня. Додай ключ і шифротекст. Знімки зберігаються в поточному проєкті.', 'Knižnica je prázdna. Pridaj kľúč a šifrový text. Snímky sa ukladajú do aktuálneho projektu.'),
    'none': ('Кандидатів іншого типу немає. Додай відповідні JSON або знімок іншого проєкту.', 'Nie sú kandidáti druhého typu. Pridaj príslušné JSON alebo snímku iného projektu.'),
    'name': ('Документ', 'Dokument'), 'coverage': ('Покриття', 'Pokrytie'),
    'tokens': ('Токени', 'Tokeny'), 'distinct': ('Різні коди', 'Rôzne kódy'),
    'status': ('Стан', 'Stav'), 'ready': ('Перевірено', 'Overené'), 'draft': ('Чернетка', 'Koncept'),
    'details': ('Попередній результат', 'Predbežný výsledok'),
    'unknown': ('Невідомі коди', 'Neznáme kódy'), 'ambiguous': ('Неоднозначні коди', 'Nejednoznačné kódy'),
    'excluded': ('Виключено неперевірених / неповних токенів', 'Vylúčené neoverené / neúplné tokeny'),
    'no_tokens': ('Немає придатних перевірених токенів для порівняння.', 'Nie sú vhodné overené tokeny na porovnanie.'),
}


class CipherLibraryWindow(QtWidgets.QDialog):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.root = workspace.root
        self.library = CipherLibrary(workspace.root)
        self.results = []
        self.setWindowTitle(self.t('title'))
        self.resize(960, 680)
        self.setMinimumSize(740, 540)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        for key in ('intro', 'limits'):
            label = QtWidgets.QLabel(self.t(key)); label.setWordWrap(True)
            if key == 'limits': label.setObjectName('mutedLabel')
            layout.addWidget(label)
        actions = QtWidgets.QHBoxLayout()
        for key, callback in [('current_key', lambda: self.add_current('key')), ('current_text', lambda: self.add_current('ciphertext')), ('import', self.import_json)]:
            button = QtWidgets.QPushButton(self.t(key))
            button.clicked.connect(lambda checked=False, fn=callback: workspace._guard(fn))
            actions.addWidget(button)
        layout.addLayout(actions)
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(self.t('query'))
        self.query = QtWidgets.QComboBox(); self.query.setMinimumContentsLength(18)
        self.query.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        label.setBuddy(self.query); row.addWidget(label); row.addWidget(self.query, 1)
        self.search_button = QtWidgets.QPushButton(self.t('search')); self.search_button.setProperty('primary', True)
        self.search_button.clicked.connect(lambda: workspace._guard(self.search))
        row.addWidget(self.search_button); layout.addLayout(row)
        self.query.currentIndexChanged.connect(self.clear_results)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([self.t(key) for key in ('name', 'coverage', 'tokens', 'distinct', 'status')])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_result)
        layout.addWidget(self.table, 1)
        label = QtWidgets.QLabel(self.t('details')); layout.addWidget(label)
        self.details = QtWidgets.QPlainTextEdit(); self.details.setReadOnly(True)
        self.details.setAccessibleName(self.t('details')); layout.addWidget(self.details, 1)
        self.message = QtWidgets.QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        self.reload()

    def t(self, key):
        return COPY[key][0 if self.workspace.language == 'uk' else 1]

    def reload(self, selected=None):
        self.query.clear()
        for entry in self.library.entries:
            kind = entry['document'].get('document_type', 'key')
            self.query.addItem(f"{entry['name']} · {self.t(kind)} · {self.t(entry['document']['status'])}", entry['id'])
        if selected:
            self.query.setCurrentIndex(self.query.findData(selected))
        self.search_button.setEnabled(bool(self.library.entries))
        self.message.setText(self.t('empty') if not self.library.entries else '')

    def clear_results(self, *_):
        self.results = []
        if hasattr(self, 'table'):
            self.table.setRowCount(0); self.details.clear(); self.message.clear()

    def add_current(self, kind):
        if self.workspace.root != self.root or self.workspace._task is not None or self.workspace._process is not None:
            return
        if self.workspace.save_annotations_current(silent=True) is False:
            return
        document = build_key(self.workspace.root) if kind == 'key' else build_ciphertext(self.workspace.root)
        identifier = self.library.add(self.workspace.root.name, document)
        self.reload(identifier)

    def import_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, self.t('import'), str(self.workspace.root), 'JSON (*.json)')
        if not path:
            return
        document = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        identifier = self.library.add(Path(path).stem, document)
        self.reload(identifier)

    def search(self):
        query = next((entry['document'] for entry in self.library.entries if entry['id'] == self.query.currentData()), None)
        if query is None:
            return
        self.results = search_library(query, self.library.entries)
        self.table.setRowCount(len(self.results))
        for row, result in enumerate(self.results):
            values = [result['name'], f"{result['coverage']:.1%}", f"{result['matched']}/{result['total']}",
                      f"{result['distinct_matched']}/{result['distinct_total']}", self.t(result['status'])]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        self.message.setText('' if self.results else self.t('none'))
        if self.results:
            self.table.selectRow(0)

    def show_result(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.results):
            return
        result = self.results[row]
        lines = [self.t('excluded') + ': ' + str(result['excluded']),
                 self.t('unknown') + ': ' + ', '.join(result['unknown']),
                 self.t('ambiguous') + ': ' + ', '.join(result['ambiguous'])]
        if not result['total']:
            lines.append(self.t('no_tokens'))
        lines.extend(f"{line['image']} / L2 #{line['line_id']}: {line['text']}" for line in result['preview'])
        self.details.setPlainText('\n'.join(lines))
