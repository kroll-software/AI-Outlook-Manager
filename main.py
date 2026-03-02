# main.py

from utils.stop_watch import get_stop_watch

import sys
import asyncio
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale  
#from PySide6.QtCore import Qt
from qasync import QEventLoop
from gui.main_window import MainWindow
from core import setting_manager
from core.utils import *
from myagents.setup import create_agents, get_manager
from core.contact_db import init_contact_db
from core.id_map_db import init_idmap_db
from core.graph_auth_client import init_graph_client
from gui.theme_loader import init_themes

async def main():
    settings_path = get_settings_dir()
    makedir(settings_path)
    setting_manager.load_settings(os.path.join(settings_path, ".settings", "settings.json"))

    # ── Übersetzer laden ─────────────────────────────────────  
    #QLocale.setDefault(QLocale(QLocale.German)) # Zahlenformate, Datumsformate, ...
    
    installed_languages = ["de", "en", "fr", "es", "it", "zh_CN"]
    locale = setting_manager.get_setting("locale", None)
    if not locale or not locale in installed_languages:
        system_qt_locale = QLocale.system()  
        lang_code = system_qt_locale.name()  
        if "_" in lang_code:  
            lang, country = lang_code.split("_", 1)  
        else:  
            lang, country = lang_code, ""  
        
        if lang == "zh":  
            candidate = f"zh_{country}"
        else:  
            candidate = lang  
        
        if candidate not in installed_languages:  
            if lang in installed_languages:  
                candidate = lang  
        
        if candidate in installed_languages:  
            locale = candidate            
        else:  
            locale = "en"
        setting_manager.set_setting("locale", locale)

    app.translator = QTranslator()    
    qm_file = os.path.join("translations", f"outlookmanager_{locale}.qm") 
  
    if app.translator.load(qm_file):
        app.installTranslator(app.translator)
        print(f"Übersetzung für {locale} geladen.")  
    else:  
        print(f"[Warnung] Übersetzung für {locale} nicht gefunden - nutze Standardtext.")  
    
    # ── Alles andere laden ─────────────────────────────────────  
    init_themes()
    db_path = os.path.join(settings_path, ".sqlite")
    try:
        init_contact_db(db_path=db_path)
        init_idmap_db(db_path=db_path)
    except Exception as e:
        print(str(e))

    init_graph_client() # zuletzt!
    workspace_dir = setting_manager.get_setting("workspace_dir")
    if not workspace_dir:
        workspace_dir = os.path.join(settings_path, "workspace")
        setting_manager.set_setting("workspace_dir", workspace_dir)
    makedir(workspace_dir)
    
    create_agents()
    window = MainWindow(agent=get_manager())
    window.show()
    window.raise_()
    window.activateWindow()
    return window  # Fenster „übergeben“, damit es nicht „verschwindet“

if __name__ == "__main__":    
    app = QApplication(sys.argv)    
    app.setStyle("fusion")

    # Nur unter Windows Schrift global etwas grösser
    if sys.platform.startswith("win"):
        font = app.font()        
        font.setPointSize(int(font.pointSize() * 1.2))        
        app.setFont(font)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        main_window = loop.run_until_complete(main())  # <- Referenz erhalten
        loop.run_forever()
