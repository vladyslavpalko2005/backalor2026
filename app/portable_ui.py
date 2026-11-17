from pathlib import Path
import json
from PyQt6 import QtWidgets
from .portable import export_settings, import_settings
from .project import save_pipeline, load_pipeline

COPY={
 'import_settings':('Імпорт налаштувань…','Importovať nastavenia…'),
 'export_settings':('Експорт налаштувань…','Exportovať nastavenia…'),
 'done':('Налаштування перенесено. Шляхи до моделей перевір на цьому комп’ютері.','Nastavenia prenesené. Skontroluj cesty k modelom na tomto počítači.'),
}


def transfer_settings(workspace, importing):
    if workspace._task is not None or workspace._process is not None:return
    t=lambda key:COPY[key][0 if workspace.language=='uk' else 1]
    if importing:
        source,_=QtWidgets.QFileDialog.getOpenFileName(workspace,t('import_settings'),str(workspace.root),'JSON (*.json)')
        if not source:return
        if Path(source).stat().st_size>1024*1024:raise ValueError('Settings JSON exceeds 1 MiB')
        payload=json.loads(Path(source).read_text(encoding='utf-8-sig'))
        import_settings(workspace.root,payload)
        workspace.steps=load_pipeline(workspace.root);workspace.refresh_steps_list();workspace._load_model_settings();workspace.update_preview()
    else:
        target,_=QtWidgets.QFileDialog.getSaveFileName(workspace,t('export_settings'),str(workspace.root/'results/settings.json'),'JSON (*.json)')
        if not target:return
        save_pipeline(workspace.root,workspace.steps);workspace.save_model_settings()
        export_settings(workspace.root,Path(target))
    workspace.statusBar().showMessage(t('done'))
