from __future__ import annotations
import copy
import csv
import json
import os
from pathlib import Path
import tempfile
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from app.annotations import AnnotationFile, AnnotationItem, save_annotations
from app.project import ensure_project_structure
from app.digitization import build_key
from app.cipher_library import (build_ciphertext, export_ciphertext, validate_document,
                                key_mapping, compare_documents, search_library, CipherLibrary)
from app.storage import SaveConflict


def key_annotations():
    return AnnotationFile('page.png', [
        AnnotationItem(1, 'L1', None, [0, 0, 100, 100]),
        AnnotationItem(2, 'L2', 1, [0, 0, 100, 50]),
        AnnotationItem(3, 'L3', 2, [1, 1, 10, 10], text_role='plaintext', element_type='readable', transcription='A', reviewed=True),
        AnnotationItem(4, 'L3', 2, [20, 1, 10, 10], text_role='ciphertext', element_type='cipher_symbol', symbol_code='S1', reviewed=True),
    ], 5)


def text_annotations():
    return AnnotationFile('page.png', [
        AnnotationItem(1, 'L1', None, [0, 0, 100, 100], text_role='ciphertext'),
        AnnotationItem(2, 'L2', 1, [0, 0, 100, 50]),
        # Deliberately stored in reverse reading order; S1 and S10 stay distinct.
        AnnotationItem(5, 'L3', 2, [40, 1, 10, 10], element_type='cipher_symbol', symbol_code='S10', reviewed=True),
        AnnotationItem(4, 'L3', 2, [20, 1, 10, 10], element_type='cipher_symbol', symbol_code='S1', reviewed=True),
        AnnotationItem(3, 'L3', 2, [1, 1, 10, 10], element_type='cipher_symbol', symbol_code='S1', reviewed=True),
    ], 6)


class CipherLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        ensure_project_structure(self.root)
        Image.new('RGB', (100, 100)).save(self.root/'images_raw/page.png')
        self.write(key_annotations())
        self.key = build_key(self.root)
        self.write(text_annotations())
        self.text = build_ciphertext(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data):
        save_annotations(self.root/'annotations/page.json', data)

    def test_text_export_order_and_source_references(self):
        tokens = self.text['pages'][0]['lines'][0]['tokens']
        self.assertEqual([token['id'] for token in tokens], [3, 4, 5])
        self.assertEqual([token['value'] for token in tokens], ['S1', 'S1', 'S10'])
        self.assertEqual(self.text['status'], 'ready')
        self.assertEqual(tokens[0]['bbox'], [1, 1, 10, 10])

    def test_json_csv_roundtrip(self):
        export_ciphertext(self.root, self.root/'text.json')
        self.assertEqual(json.loads((self.root/'text.json').read_text()), self.text)
        export_ciphertext(self.root, self.root/'text.csv')
        with (self.root/'text.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row['value'] for row in rows], ['S1', 'S1', 'S10'])

    def test_coverage_is_exact_token_coverage_and_unknowns_visible(self):
        result = compare_documents(self.key, self.text)
        self.assertAlmostEqual(result['coverage'], 2/3)
        self.assertEqual((result['matched'], result['total']), (2, 3))
        self.assertEqual((result['distinct_matched'], result['distinct_total']), (1, 2))
        self.assertEqual(result['unknown'], ['S10'])
        self.assertEqual(result['preview'][0]['text'], 'A A ⟨S10⟩')

    def test_search_both_directions_and_no_mutation(self):
        library = CipherLibrary(self.root)
        library.add('key', self.key); library.add('text', self.text)
        original = copy.deepcopy(library.entries)
        forward = search_library(self.text, library.entries)
        reverse = search_library(self.key, library.entries)
        self.assertEqual(forward[0]['coverage'], reverse[0]['coverage'])
        self.assertEqual((forward[0]['name'], reverse[0]['name']), ('key', 'text'))
        self.assertEqual(library.entries, original)
        self.assertNotIn('document_type', self.key)

    def test_candidates_rank_by_coverage(self):
        key = copy.deepcopy(self.key)
        key['pages'][0]['pairs'][0]['ciphertext'][0]['symbol_code'] = 'S10'
        library = CipherLibrary(self.root)
        library.add('rare', key); library.add('frequent', self.key)
        self.assertEqual([result['name'] for result in search_library(self.text, library.entries)], ['frequent', 'rare'])

    def test_unreviewed_tokens_excluded_and_zero_is_not_full_match(self):
        for token in self.text['pages'][0]['lines'][0]['tokens']:
            token['reviewed'] = False
        result = compare_documents(self.key, self.text)
        self.assertEqual((result['coverage'], result['total'], result['excluded']), (0, 0, 3))

    def test_draft_key_pairs_are_not_used(self):
        self.key['pages'][0]['pairs'][0]['status'] = 'draft'
        self.assertEqual(compare_documents(self.key, self.text)['coverage'], 0)

    def test_ambiguous_mapping_exposed(self):
        pair = copy.deepcopy(self.key['pages'][0]['pairs'][0])
        pair['plaintext'][0]['transcription'] = 'B'
        self.key['pages'][0]['pairs'].append(pair)
        result = compare_documents(self.key, self.text)
        self.assertEqual(result['ambiguous'], {'S1': ['A', 'B']})
        self.assertIn('[A / B]', result['preview'][0]['text'])

    def test_multiple_plaintexts_require_explicit_reference(self):
        pair = self.key['pages'][0]['pairs'][0]
        other = copy.deepcopy(pair['plaintext'][0]); other.update(id=9, transcription='B')
        pair['plaintext'].append(other)
        self.assertEqual(key_mapping(self.key), {})
        pair['ciphertext'][0]['transcription_ref_id'] = 9
        self.assertEqual(key_mapping(self.key), {'S1': ['B']})

    def test_missing_annotation_and_orphans_stay_draft(self):
        data = text_annotations(); data.items[-1].parent_id = 999
        self.write(data)
        self.assertIn('unpaired_elements', build_ciphertext(self.root)['pages'][0]['issues'])
        Image.new('RGB', (10, 10)).save(self.root/'images_raw/missing.png')
        document = build_ciphertext(self.root)
        self.assertEqual(document['status'], 'draft')
        self.assertTrue(any('missing_annotations' in page['issues'] for page in document['pages']))

    def test_plaintext_only_is_not_ciphertext(self):
        data = text_annotations(); data.items[0].text_role = 'plaintext'
        self.write(data)
        self.assertEqual(build_ciphertext(self.root)['pages'][0]['issues'], ['no_ciphertext'])

    def test_invalid_geometry_excluded(self):
        data = text_annotations(); data.items[-1].bbox = [99, 0, 10, 10]
        self.write(data)
        result = compare_documents(self.key, build_ciphertext(self.root))
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['excluded'], 3)

    def test_library_persists_deduplicates_and_detects_conflicts(self):
        library = CipherLibrary(self.root); other = CipherLibrary(self.root)
        identifier = library.add('first', self.key)
        self.assertEqual(library.add('again', self.key), identifier)
        self.assertEqual(len(CipherLibrary(self.root).entries), 1)
        with self.assertRaises(SaveConflict): other.add('text', self.text)
        self.assertEqual(len(other.entries), 0)

    def test_bad_import_does_not_write(self):
        library = CipherLibrary(self.root)
        for payload in ({}, {'schema_version': 99}, {'schema_version': 1, 'document_type': 'ciphertext', 'status': 'ready', 'pages': [{}]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                library.add('bad', payload)
        self.assertFalse(library.path.exists())

    def test_empty_project_is_draft(self):
        (self.root/'images_raw/page.png').unlink()
        self.assertEqual(build_ciphertext(self.root)['status'], 'draft')

    def test_readable_ciphertext_tokens_are_atomic(self):
        token = self.text['pages'][0]['lines'][0]['tokens'][0]
        token.update(element_type='readable', transcription='42')
        pair_token = self.key['pages'][0]['pairs'][0]['ciphertext'][0]
        pair_token.update(element_type='readable', transcription='42')
        self.assertEqual(compare_documents(self.key, self.text)['matched'], 1)

    def test_reading_order_with_baseline_variation(self):
        data = text_annotations()
        data.items[-1].bbox[1] = 3
        self.write(data)
        tokens = build_ciphertext(self.root)['pages'][0]['lines'][0]['tokens']
        self.assertEqual([token['id'] for token in tokens], [3, 4, 5])

    def test_duplicate_stems_rejected(self):
        Image.new('RGB', (100, 100)).save(self.root/'images_raw/page.jpg')
        with self.assertRaises(ValueError): build_ciphertext(self.root)

    def test_bad_reference_import_rejected(self):
        self.key['pages'][0]['pairs'][0]['ciphertext'][0]['transcription_ref_id'] = []
        with self.assertRaises(ValueError): validate_document(self.key)

    def test_bundle_preserves_library(self):
        from app.datasets import export_bundle, import_bundle
        library = CipherLibrary(self.root); library.add('key', self.key)
        export_bundle(self.root, self.root/'project.zip')
        import_bundle(self.root/'project.zip', self.root/'imported')
        self.assertEqual(CipherLibrary(self.root/'imported').entries, library.entries)


class CipherLibraryUITests(unittest.TestCase):
    setUp = CipherLibraryTests.setUp
    tearDown = CipherLibraryTests.tearDown
    write = CipherLibraryTests.write
    def test_modeless_window_search_and_both_languages(self):
        from PyQt6 import QtWidgets
        from app.workspace import WorkspaceWindow
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        workspace = WorkspaceWindow(self.root)
        try:
            library = CipherLibrary(self.root); library.add('key', self.key); library.add('text', self.text)
            workspace.digitization.open_library()
            window = workspace.digitization.library_window
            window.query.setCurrentIndex(1); window.search(); app.processEvents()
            self.assertFalse(window.isModal())
            self.assertEqual(window.table.rowCount(), 1)
            self.assertIn('66.7%', window.table.item(0, 1).text())
            self.assertIn('S10', window.details.toPlainText())
            window.query.setCurrentIndex(0); window.search()
            self.assertEqual(window.table.item(0, 0).text(), 'text')
            workspace.language = 'sk'
            self.assertEqual(window.t('search'), 'Nájsť zhody')
            other_root = self.root/'other'
            ensure_project_structure(other_root)
            workspace.switch_project(other_root)
            self.assertFalse(window.isVisible())
            self.assertIsNone(workspace.digitization.library_window)
            window.close()
        finally:
            workspace.close(); app.processEvents()
