from __future__ import annotations
from pathlib import PurePosixPath
import zipfile


def validate_archive(path):
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>50000 or sum(item.file_size for item in entries)>2*1024**3:
            raise ValueError('Project archive is too large after decompression')
        names=set()
        for item in entries:
            name=PurePosixPath(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename or not name.parts:
                raise ValueError('Invalid archive path')
            if item.filename in names:raise ValueError('Duplicate archive entry')
            names.add(item.filename)
            if (item.external_attr >> 16) & 0o170000 == 0o120000:raise ValueError('Symbolic links are not supported')
            if name.parts[0] not in {'images_raw','images_processed','annotations','results','project.json'}:
                raise ValueError('Unknown project file')
            if name.parts[0]=='results' and str(name) not in {'results','results/preprocess_pipeline.json','results/yolo_config.json','results/cipher_library.json'}:
                raise ValueError('Only portable configuration is accepted in results')
            if item.flag_bits & 1:raise ValueError('Encrypted archives are not supported')
        if not entries:raise ValueError('Empty archive')
