from __future__ import annotations
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from PIL import Image
from .project import list_raw_images


def import_sources(root: Path, sources: list[Path]) -> int:
    """Validate and stage input before adding any pages to the project."""
    metadata_path = root/'project.json'
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    groups = metadata.setdefault('image_groups',{})
    stems = {p.stem.casefold() for p in list_raw_images(root)}
    staged = []
    with tempfile.TemporaryDirectory(dir=root) as temporary:
        staging = Path(temporary)
        for source in sources:
            document = f'{source.stem}-{uuid.uuid4().hex[:8]}'
            def reserve(name):
                candidate = Path(name); count = 1
                while candidate.stem.casefold() in stems:
                    candidate = Path(f'{Path(name).stem}_{count}{Path(name).suffix}'); count += 1
                stems.add(candidate.stem.casefold())
                return candidate.name
            if source.suffix.lower() == '.pdf':
                try:
                    import fitz
                except ImportError as exc:
                    raise RuntimeError('Install PyMuPDF to import PDF documents') from exc
                with fitz.open(source) as pdf:
                    if pdf.needs_pass: raise ValueError(f'{source.name}: encrypted PDF')
                    for index,page in enumerate(pdf):
                        name = reserve(f'{source.stem}-page{index+1:04d}.png')
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(150/72,150/72),alpha=False)
                        pixmap.save(staging/name); staged.append((name,document))
            else:
                with Image.open(source) as image: image.verify()
                name = reserve(source.name); shutil.copy2(source,staging/name); staged.append((name,document))
        for name,document in staged:
            shutil.move(str(staging/name),str(root/'images_raw'/name)); groups[name] = document
    metadata_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(staged)
