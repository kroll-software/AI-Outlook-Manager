# gui/main_window.py

import os
import sys
import json
import asyncio
import ast
import logging
from copy import deepcopy
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextBrowser, QToolBar, QStatusBar, QDialog,
    QLabel, QMenu, QMenuBar, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLineEdit, QPushButton, QComboBox, QFrame, QTextEdit, QSizePolicy, 
    QToolButton, QSizeGrip, QMessageBox, QStyleOptionFrame, QStyle, QTabWidget,
    QSplitterHandle, QButtonGroup
)
from PySide6.QtGui import QAction, QActionGroup, QIcon, QColor, QFontDatabase, QFont, QPainter, QPixmap, QTextCursor
from PySide6.QtCore import Qt, QTimer, QEvent, QSize, QMimeData, QTranslator, QLocale, Signal
#from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtSvg import QSvgRenderer
from markdown_it import MarkdownIt
from gui.qt_extensions import *

from gui.theme_loader import load_theme_colors, theme_choices
from gui.message_renderer import DefaultMessageRenderer, CompactMessageRenderer
#from core import models
from config import *
from myagents.tools_helpers import get_user_info_func

from myagents.setup import recreate_agents
from typing import List, Dict
from agents import Agent, tracing, trace
from core import setting_manager
from gui.options_dialog import OptionsDialog
from gui.about_dialog import AboutDialog
from core.chat_history import ChatHistory
from myagents.tools_helpers import register_tool_confirmation_handler
from core.chat_memory import ChatMemory, ChatMemorySession
from core.utils import extract_thinking_blocks, remove_thinking_blocks, shorten_text, shorten_value, get_settings_dir
import core.setting_manager as settings_manager
from core.graph_auth_client import GraphAuthClient
from utils.input_buffer import InputBuffer
import core.model_provider
from core.id_map_db import get_idmap_db

from gui.elide_label import ElideLabel

from agents import Agent, Runner, SQLiteSession, Span, RunConfig, RunHooks
from myagents import BaseAgent
#from agents.memory import Session
from openai import OpenAIError, NotFoundError
from core.graph_auth_client import get_graph_client
from core.local_trace_processor import LocalTraceProcessor, add_tokens_from_run_result, get_total_tokens, reset_token_count

from utils.stop_watch import get_stop_watch

#logging.basicConfig(level=logging.DEBUG)

class MainWindow(MyQMainWindow):
    loginFinished = Signal(bool, dict)   # Signal für Login-Callback

    def __init__(self, agent: BaseAgent = None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Outlook Manager")        
        self.restore_window_state()

        self.loginFinished.connect(self.on_login_finished, Qt.QueuedConnection)

        n_ctx = core.model_provider.get_model_ctx_size()
        static_tokens = 3577    # input_tokens nach Chat mit leerer History
        settings_path = get_settings_dir()
        chatmemory_filepath = os.path.join(settings_path, ".settings", "history.json")
        self.chatmemory = ChatMemory(n_ctx, file_path=chatmemory_filepath, static_tokens=static_tokens)
        self.chat_session = ChatMemorySession(session_id="outlook-manager", chat_memory=self.chatmemory)
        self.chat_history = ChatHistory(logfile_dir=os.path.join(settings_path, "logfiles"))
        
        # OpenAi Session-Manager
        #db_path = os.path.join(".settings", "history.db")
        #self.chat_session = SQLiteSession("outlook-manager")        
        
        # Register for tracing_processor notifications
        core.model_provider.get_tracing_processor().add_trace_end_listener(self.on_trace_complete)

        self.user_name = None
        self.input_buffer = InputBuffer()
        self.status_stack = []
        self.last_trace_box_html = None

        theme_file = setting_manager.get_setting("theme_file", "solarized_dark.json")
        self.theme = load_theme_colors(os.path.join("themes", theme_file))
        #self.theme = load_theme_colors(os.path.join("themes", "solarized_light.json"))
        #self.theme = load_theme_colors(os.path.join("themes", "monokai_dark.json"))
        #self.theme = load_theme_colors(os.path.join("themes", "monokai_light.json"))

        style = setting_manager.get_setting("render_style", "standard")
        if style == "standard":
            self.renderer = DefaultMessageRenderer(theme=self.theme)
        else:
            self.renderer = CompactMessageRenderer(theme=self.theme)        

        self.agent = agent
        self.agent_is_running = False

        #self.agent_session = SQLiteSession("123")        

        self.md = MarkdownIt()        

        # Menüleiste
        self._create_menu()

        # Symbolleiste
        self._create_toolbar()

        # Statusleiste
        self._create_statusbar()        

        # Hauptlayout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Splitter anstelle des direkten VBox-Layouts
        #self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter = DotSplitter(Qt.Orientation.Vertical)        
        main_layout.addWidget(self.splitter)

        # Tabs oben
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(200)   # oder je nach Bedarf  
        self.splitter.addWidget(self.tabs)

        # Chat Tab
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        chat_layout.setContentsMargins(3, 3, 3, 3)
        chat_layout.setSpacing(0)

        self.chat_box = QTextBrowser()
        self.chat_box.setOpenExternalLinks(True)
        self.chat_box.setFrameStyle(QTextBrowser.NoFrame)
        chat_layout.addWidget(self.chat_box)
        self.tabs.addTab(chat_tab, self.tr("Chat"))

        # Trace Tab
        trace_tab = QWidget()
        trace_layout = QVBoxLayout(trace_tab)
        trace_layout.setContentsMargins(3, 3, 3, 3)
        trace_layout.setSpacing(0)

        self.trace_box = QTextBrowser()
        self.trace_box.setOpenExternalLinks(True)
        self.trace_box.setFrameStyle(QTextBrowser.NoFrame)
        trace_layout.addWidget(self.trace_box)
        self.tabs.addTab(trace_tab, self.tr("Trace-Log"))

        # Eingabe unten
        self.input_frame = QFrame()
        self.input_frame.setFrameShape(QFrame.Shape.Box)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)
        self.input_frame.setLayout(input_layout)
        self.input_frame.setContentsMargins(4, 4, 4, 4)

        # Drop-down
        self.option_box = QComboBox()
        self.option_box.setVisible(False)
        input_layout.addWidget(self.option_box)

        # Eingabefeld
        self.input_edit = PlainTextEdit()
        self.input_edit.setPlaceholderText(self.tr("Nachricht eingeben..."))
        self.input_edit.setMinimumHeight(80)   # Mindesthöhe
        #self.input_edit.setMaximumHeight(300)  # Optional: Limit
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)  
        self.input_edit.setSizePolicy(policy) 

        self.input_edit.acceptRichText = False
        self.input_edit.installEventFilter(self)                
        input_layout.addWidget(self.input_edit, stretch=1)

        # Button
        self.send_button = QPushButton()
        self.send_button.setFixedSize(32, 32)
        self.send_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_layout.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignTop)

        # Input-Frame als zweites Panel in den Splitter
        self.splitter.addWidget(self.input_frame)

        # Verhältnis einstellen (z.B. 80% oben, 20% unten)
        self.splitter.setStretchFactor(0, 1)   # Top soll all das zusätzliche/wegfallende Raum aufnehmen  
        self.splitter.setStretchFactor(1, 0)   # Bottom behält seine Größe  
        self.splitter.setCollapsible(0, False)  
        self.splitter.setCollapsible(1, False)  

        # --- Splitter‑State --------------------------------------------------  
        splitter_s = setting_manager.get_setting("splitter_sizes")  
        if splitter_s:
            # Splitter_s ist ein String „400,200“  
            try:  
                sizes = [int(v) for v in splitter_s.split(",")]  
                if len(sizes) == 2:                   # nur wenn wir genau 2 Panels haben  
                    self.splitter.setSizes(sizes)  
            except ValueError:  
                # irgendwas war schief – ignorieren und Standard‑Verhalten lassen  
                pass  

        '''        
        font_id = QFontDatabase.addApplicationFont(os.path.join("assets", "fa-solid-900.ttf"))
        if font_id != -1:
            font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            self.icon_font = QFont(font_family, 14)
        else:
            print("⚠️ Font Awesome konnte nicht geladen werden.")
        '''
        
        self.apply_font_settings()

        # Theme        
        self.set_color_theme()

        self.show_status_model()        
        self.show_status_connection()
        self.show_status_user()        
        self.show_status()        

        register_tool_confirmation_handler(self.tool_confirmation_dialog)
        self.update_auth_buttons(False)

        # Display latest Chat
        last_history_file = settings_manager.get_setting("last_history_file", None)
        if last_history_file and os.path.exists(last_history_file):
            self.chat_history.load_from_file(last_history_file)
            self.show_chat_from_history()  # this also displays all contents from history
        else:
            settings_manager.set_setting("last_history_file", self.chat_history.get_logfile_name())
            self.new_chat_action.setEnabled(False)

        self.input_edit.setFocus()
        self.check_about_dialog()
        
        get_stop_watch().stop()
        print(f"Programm Startdauer: {get_stop_watch().get_formatted_duration()}")

        # Standard Cursor setzen
        #app.restoreOverrideCursor()

    def _create_menu(self):  
        """  
        Builds the application menu with a "Datei" (File) menu and an "Extras" menu  
        containing a language submenu. The submenu shows the language names in their  
        own scripts and toggles the UI language accordingly.  
        """  
        # ----- Standard menu bar -----  
        menu_bar = self.menuBar()  
    
        # 1. „Datei“-Menü (wie Du es schon hattest)  
        file_menu = menu_bar.addMenu(self.tr("&Datei"))  
        file_menu.addAction(self.tr("Be&enden"), self.close)  
    
        # 2. Neues „Extras“-Menü  
        extras_menu = menu_bar.addMenu(self.tr("E&xtras"))  
    
        # 3. Untermenü „Sprache“  
        lang_menu = extras_menu.addMenu(self.tr("&Sprache"))  
    
        # 4. Aktionen für die Sprachen  
        #   (label shown in the language’s own script)  
        action_de = lang_menu.addAction("&Deutsch")  
        action_en = lang_menu.addAction("&English")  
        action_fr = lang_menu.addAction("Français")
        action_es = lang_menu.addAction("Español")
        action_it = lang_menu.addAction("Italiano")
        action_zh = lang_menu.addAction("简体中文")   # Simplified Chinese  
    
        # ----- Action as checkable -----  
        for act in (action_de, action_en, action_fr, action_es, action_it, action_zh):  
            act.setCheckable(True)  
    
        # ----- Button‑Group for exclusive state -----  
        atn_group = QActionGroup(lang_menu)  
        atn_group.setExclusive(True)  
        for act in (action_de, action_en, action_fr, action_es, action_it, action_zh):  
            atn_group.addAction(act)  
    
        # ----- Current locale (default to English) -----  
        locale = setting_manager.get_setting("locale", "en")  
    
        # Map locale code → corresponding QAction  
        locale_to_action = {  
            "de": action_de,  
            "en": action_en,  
            "fr": action_fr,  
            "es": action_es,  
            "it": action_it,  
            "zh_CN": action_zh,          # Chinese (Simplified)  
        }  
        # Default to English if unknown  
        action_to_check = locale_to_action.get(locale, action_en)  
        action_to_check.setChecked(True)  
    
        # ----- Trigger slots -----  
        action_de.triggered.connect(lambda: self.set_gui_language("de"))  
        action_en.triggered.connect(lambda: self.set_gui_language("en"))  
        action_fr.triggered.connect(lambda: self.set_gui_language("fr"))  
        action_es.triggered.connect(lambda: self.set_gui_language("es"))  
        action_it.triggered.connect(lambda: self.set_gui_language("it"))  
        action_zh.triggered.connect(lambda: self.set_gui_language("zh_CN"))  

    def set_gui_language(self, lang_code="en"):        
        setting_manager.set_setting("locale", lang_code)
        msg = self.tr("Bitte starten Sie die Anwendung neu, damit die Änderungen wirksam werden.")
        
        # 3. Zeige sie in einer MessageBox an  
        QMessageBox.information(  
            self,                     # Eltern‑Widget (Window)  
            self.tr("Information"),   # Titel der Box  
            msg,                      # Body‑Text  
            QMessageBox.Ok             # nur OK‑Button  
        )  


    def _create_toolbar(self):
        self.toolbar = QToolBar(self.tr("Hauptwerkzeugleiste"))
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)        
        self.addToolBar(self.toolbar)

        # Leeres Spacer-Widget
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)  # ← Jetzt werden alle folgenden Elemente rechts ausgerichtet

        icon = get_colored_svg_icon(os.path.join("assets", "star.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.new_chat_action = QAction(iconText=" " + self.tr("Neuer Chat"), icon=icon, parent=self)
        self.new_chat_action.setToolTip(self.tr("Neuer Chat"))
        self.new_chat_action.triggered.connect(self.on_new_chat_clicked)

        icon = get_colored_svg_icon(os.path.join("assets", "circle-info.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.about_action = QAction(iconText=" " + self.tr("Über.."), icon=icon, parent=self)
        self.about_action.setToolTip(self.tr("Über Outlook-Manager.."))
        self.about_action.triggered.connect(self.on_about_clicked)
        icon = get_colored_svg_icon(os.path.join("assets", "gear.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.options_action = QAction(iconText=" " + self.tr("Optionen.."), icon=icon, parent=self)
        self.options_action.setToolTip("")
        self.options_action.triggered.connect(self.show_options_dialog)        
        
        icon = get_colored_svg_icon(os.path.join("assets", "right-to-bracket.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.login_action = QAction(iconText=" " + self.tr("Anmelden.."), icon=icon, parent=self)        
        self.login_action.setToolTip(self.tr("Bei Microsoft Outlook anmelden.."))
        icon = get_colored_svg_icon(os.path.join("assets", "right-from-bracket.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.logout_action = QAction(iconText=" " + self.tr("Abmelden.."), icon=icon, parent=self)
        self.logout_action.setToolTip(self.tr("Von Microsoft Outlook abmelden"))

        self.login_action.triggered.connect(self.login)
        self.logout_action.triggered.connect(self.logout)

        icon = get_colored_svg_icon(os.path.join("assets", "circle-half-stroke.svg"), QSize(16, 16), QColor(self.theme["Base00"]))
        self.theme_action = QToolButton()
        self.theme_action.setIcon(icon)
        self.theme_action.setText(" " + self.tr("Thema"))
        self.theme_action.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.theme_action.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.theme_action.setToolTip(self.tr("Farbschema wählen"))

        theme_menu = QMenu(self.theme_action)
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)

        current_theme = setting_manager.get_setting("theme_file", "solarized_dark.json")

        for filename, label in theme_choices.items():
            action = QAction(label, self, checkable=True)
            action.setData(filename)            
            action.setChecked(current_theme == filename) # markiere aktuelles Theme
            action.triggered.connect(self.on_theme_selected)
            self.theme_group.addAction(action)
            theme_menu.addAction(action)

        self.theme_action.setMenu(theme_menu)        
        
        self.toolbar.addAction(self.new_chat_action)
        self.toolbar.addAction(self.options_action)
        #self.toolbar.addSeparator()
        self.toolbar.addAction(self.login_action)
        self.toolbar.addAction(self.logout_action)
        self.toolbar.addAction(self.about_action)
        self.toolbar.addWidget(self.theme_action)    

    def on_about_clicked(self):
        self.show_about_dialog()

    def on_new_chat_clicked(self):
        if self.agent_is_running:
            return
        reply = QMessageBox.question(
            self,
            self.tr("Neuen Chat starten"),
            self.tr("Verlauf leeren und einen neuen Chat beginnen?"),
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok            
        )

        if reply == QMessageBox.Ok:
            self.chatmemory.reset()
            self.chat_history.reset()            
            idmap_db = get_idmap_db()
            if idmap_db:
                try:
                    idmap_db.reset_db()
                except Exception as e:
                    self.show_error(str(e))
            get_graph_client().reset_folder_map()
            self.last_trace_box_html = None
            settings_manager.set_setting("last_history_file", self.chat_history.get_logfile_name())
            self.chat_box.clear()
            self.trace_box.clear()            
            self.new_chat_action.setEnabled(False)

    def _create_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)        

        #self.status_label = QLabel("Bereit.")
        self.status_label = ElideLabel(self.tr("Bereit."))
        #self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # Optional
        self.status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        #self.status_label.setMaximumWidth(300)  # Max. Breite in Pixeln
        self.status_label.setElideMode(Qt.ElideRight)  # "...", wenn zu lang        

        self.model_label = QLabel(self.tr("🧠 Model: -"))
        self.model_label.setToolTip(self.tr("KI-Modell"))
        self.token_label = QLabel(self.tr("Tokens: 0"))
        self.token_label.setToolTip(self.tr("Verbrauchte Tokens"))
        self.connection_label = QLabel(self.tr("🔌 Nicht verbunden"))
        self.connection_label.setToolTip(self.tr("Verbindung zum Microsoft-Outlook Dienst"))
        self.user_label = QLabel(self.tr("👤 Benutzer: -"))
        self.user_label.setToolTip(self.tr("Angemeldeter Benutzer"))
        self.status.addWidget(self.status_label, 1) #linksbündig        
        self.status.addPermanentWidget(self.model_label)
        self.status.addPermanentWidget(self.token_label)
        self.status.addPermanentWidget(self.connection_label)
        self.status.addPermanentWidget(self.user_label)
        # Größegriff (rechts unten)
        #gripper = QSizeGrip(self)
        #self.status.addPermanentWidget(gripper)


    def set_color_theme(self):

        scrollbar_style = f"""
            MyQMainWindow QScrollBar:vertical {{
                background: {self.theme['Base02']};
                width: 12px;
                margin: 0px;
            }}
            MyQMainWindow QScrollBar::handle:vertical {{
                background: {self.theme['Base01']};
                min-height: 20px;
                border-radius: 6px;
            }}
            MyQMainWindow QScrollBar::handle:vertical:hover {{
                background: {self.theme['Base00']};
            }}
            MyQMainWindow QScrollBar::add-line:vertical,
            MyQMainWindow QScrollBar::sub-line:vertical {{
                background: none;
                height: 0px;
            }}

            MyQMainWindow QScrollBar:horizontal {{
                background: {self.theme['Base02']};
                height: 12px;
                margin: 0px;
            }}
            MyQMainWindow QScrollBar::handle:horizontal {{
                background: {self.theme['Base01']};
                min-width: 20px;
                border-radius: 6px;
            }}
            MyQMainWindow QScrollBar::handle:horizontal:hover {{
                background: {self.theme['Base00']};
            }}
            MyQMainWindow QScrollBar::add-line:horizontal,
            MyQMainWindow QScrollBar::sub-line:horizontal {{
                background: none;
                width: 0px;
            }}

            MyQMainWindow QScrollBar::add-page, QScrollBar::sub-page {{
                background: none;
            }}
        """

        self.setStyleSheet(f"MyQMainWindow {{background-color: {self.theme['Base03']}; color: {self.theme['Base2']};}}")

        self.menuBar().setStyleSheet(f"""
            MyQMainWindow QMenuBar {{
                padding: 4px 0px;
                background-color: {self.theme["Base02"]};
                color: {self.theme["Base2"]};
            }}
            MyQMainWindow QMenuBar::item {{
                spacing: 3px;
                padding: 4px 8px;
                background: transparent;
                border-radius: 4px;
            }}
            MyQMainWindow QMenuBar::item:selected {{
                background: {self.theme["Base01"]};
            }}
        """)

        self.toolbar.setStyleSheet(f"""
            MyQMainWindow QToolBar {{
                background-color: {self.theme['Base03']};
                padding: 4px;
            }}
            MyQMainWindow QToolButton {{
                qproperty-iconSize: 16px;
                background-color: {self.theme['Base03']};
                color: {self.theme['Base3']};
            }}
            MyQMainWindow QWidget {{                
                background-color: {self.theme['Base03']};
                color: {self.theme['Base3']};
            }}            
            MyQMainWindow QToolButton:disabled {{
                color: {self.theme['Base00']};
            }}            
        """)       

        self.status.setStyleSheet(f"""
            MyQMainWindow QStatusBar {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base2']};
                padding: 0px;
            }}
            MyQMainWindow QLabel {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base2']};
                padding: 4px;
            }}
            MyQMainWindow QSizeGrip {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base3']};            
            }}        
        """)

        self.chat_box.setStyleSheet(f"MyQMainWindow QTextBrowser {{ background-color: {self.theme['Base03']}; padding: 8px; border: none; }}" + scrollbar_style)
                
        self.input_frame.setStyleSheet(f"MyQMainWindow QFrame {{ background-color: {self.theme['Base02']}; padding: 8px; border: none; }}")

        self.splitter.set_grip_color(self.theme['Base00'])

        self.input_edit.setStyleSheet(f"""
            MyQMainWindow PlainTextEdit {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base3']};
                padding: 6px;
                border: none;
                border-radius: 4px;
            }}
            MyQMainWindow PlainTextEdit:focus {{
                border: 2px solid {self.theme['Blue']};
            }}
        """ + scrollbar_style)

        self.send_button.setStyleSheet(f"""
            MyQMainWindow QPushButton {{
                background-color: {self.theme['Base02']};
                border: none;
                padding: 6px;
                border-radius: 4px;
            }}
            MyQMainWindow QPushButton:hover {{
                background-color: {self.theme['Base01']};
            }}
            MyQMainWindow QPushButton:pressed {{
                background-color: {self.theme['Base00']};
            }}
            MyQMainWindow QPushButton:focus {{
                border: 2px solid {self.theme['Blue']};
            }}
        """)

        self.tabs.setStyleSheet(f"""
            MyQMainWindow QTabBar::tab {{            
                color: {self.theme['Base1']};               
            }}
            MyQMainWindow QTabBar::tab:selected {{                
                color: {self.theme['Base3']};                
            }}
            MyQMainWindow QTabWidget {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base3']};
                padding: 0px;
                border: none;
                border-radius: 4px;
            }}
            MyQMainWindow QWidget {{
                background-color: {self.theme['Base02']};
                color: {self.theme['Base3']};                
                border: none;
                border-radius: 4px;
            }}            
            MyQMainWindow QTextBrowser {{
                background-color: {self.theme['Base03']};
                color: {self.theme['Base3']};
                padding: 8px; 
                border: none;
                border-radius: 4px;
            }}
        """ + scrollbar_style
        )        

        # Icons
        icon = get_colored_svg_icon(os.path.join("assets", "paper-plane.svg"), QSize(24, 24), QColor(self.theme['Base00']))
        self.send_button.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "star.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.new_chat_action.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "circle-info.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.about_action.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "gear.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.options_action.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "right-to-bracket.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.login_action.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "right-from-bracket.svg"), QSize(16, 16), QColor(self.theme['Base00']))
        self.logout_action.setIcon(icon)

        icon = get_colored_svg_icon(os.path.join("assets", "circle-half-stroke.svg"), QSize(16, 16), QColor(self.theme["Base00"]))
        self.theme_action.setIcon(icon)

        # Renderer Theme
        self.renderer.set_theme(self.theme)
        # Chatverlauf neu rendern
        self.show_chat_from_history()

    def show_chat_from_history(self):
        # Chatverlauf neu rendern
        self.chat_box.clear()
        for entry in self.chat_history.get_all():
            role = entry["role"]
            name = entry["name"]
            content = entry["content"]
            metadata = entry.get("metadata", {})
            self.append_message(role, name, content, **metadata)
        
        self.set_trace_box_content(self.last_trace_box_html)


    def show_status(self, message : str = None):
        if message:
            self.status_stack.append(message)
            self.status_label.setText("⌛ " + message)
        else:
            for _ in range(0, 2):
                message = self.status_stack.pop() if len(self.status_stack) > 0 else None
            if message:
                self.status_label.setText("⌛ " + message)
            else:
                self.status_label.setText(self.tr("Bereit."))

    def clear_status(self):
        self.status_stack.clear()
        self.show_status()

    def show_status_model(self):
        if self.agent:
            try:
                model_name = self.agent.get_agent().model.model
            except:
                model_name = "none"
            self.model_label.setText(f"🧠 {model_name}")
        else:
            self.model_label.setText(f"🧠 none")

    def show_status_tokens(self):
        self.token_label.setText(f"Tokens: {get_total_tokens():,}".replace(",", "."))

    def show_status_connection(self, connected : bool = False):
        if connected:
            self.connection_label.setText(self.tr("🔌 Verbunden"))
        else:
            self.connection_label.setText(self.tr("🔌 Nicht verbunden"))

    def show_status_user(self, username : str = None):
        if username:            
            self.user_label.setText(f"👤 {username}")
            self.user_label.setVisible(True)
        else:                        
            self.user_label.setVisible(False)    

    def scroll_down(self):
        # Nach unten scrollen
        cursor = self.chat_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat_box.setTextCursor(cursor)
        self.chat_box.ensureCursorVisible()

    def on_theme_change(self, new_theme_file):        
        self.theme = load_theme_colors(os.path.join("themes", new_theme_file))
        self.set_color_theme()

    def on_theme_selected(self):
        action = self.sender()
        if isinstance(action, QAction):
            filename = action.data()
            self.theme_file = filename
            new_theme = load_theme_colors(os.path.join("themes", filename))
            self.theme = new_theme
            self.set_color_theme()
            setting_manager.set_setting("theme_file", filename, True)

    def eventFilter(self, obj, event):
        if obj == self.input_edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                if get_graph_client().is_login_running():
                    get_graph_client().cancel_login()
                    self.update_auth_buttons(False)
                    self.show_status("")
                    return True
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                if event.modifiers() == Qt.ShiftModifier:
                    return False  # Neue Zeile einfügen
                else:
                    self.on_send_clicked()
                    return True  # Enter abfangen
            if event.key() == Qt.Key_Tab:
                self.focusNextChild()  # Fokus weitergeben (wie in Forms)
                return True
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_Up:
                    prev = self.input_buffer.back()
                    self.input_edit.setPlainText(prev)
                    cursor = self.input_edit.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    self.input_edit.setTextCursor(cursor)
                    return True
                elif event.key() == Qt.Key.Key_Down:
                    next_text = self.input_buffer.forward()
                    self.input_edit.setPlainText(next_text)
                    cursor = self.input_edit.textCursor()
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    self.input_edit.setTextCursor(cursor)
                    return True
        return super().eventFilter(obj, event)

    def on_send_clicked(self):
        if self.agent_is_running:
            return
        user_input = self.input_edit.toPlainText().strip()        
        if not user_input:
            return
        
        self.input_buffer.add(user_input)
        self.input_edit.clear()        
        name = self.user_name
        if not name:
            name = self.tr("Benutzer")
        self.append_message("user", name, user_input)
        self.scroll_down()

        asyncio.create_task(self.handle_input(name, user_input))

    async def handle_input(self, user_name: str, user_input: str):
        self.show_status(self.tr("Verarbeite Nachricht..."))
        self.chat_history.add_entry("user", user_name, user_input)    
        result = None
        err_msg = None        
        try:
            self.agent_is_running = True
            with trace("Debug-Run"):                
                result = await Runner.run(self.agent.get_agent(), user_input, session=self.chat_session, max_turns=10000)
        except NotFoundError as e:            
            err_msg = self.extract_error_message(e)
            self.show_error(err_msg)
        except Exception as e:
            print(f"Error: {str(e)}")            
            err_msg = self.extract_error_message(e)
            self.show_error(err_msg)        
        finally:
            self.agent_is_running = False

        if result:            
            add_tokens_from_run_result(result)
            self.show_status_tokens()            

            agent_name = result.last_agent.name
            output = result.final_output

            thinking = extract_thinking_blocks(output)
            cleaned = remove_thinking_blocks(output)

            if not cleaned:
                cleaned = self.tr("[keine Antwort]")

            if thinking:
                self.append_message("thinking", agent_name, "\n".join(thinking))
                self.scroll_down()

            self.append_message("assistant", agent_name, cleaned)
            self.scroll_down()            

            if thinking:
                self.chat_history.add_entry("thinking", agent_name, thinking)
            self.chat_history.add_entry("assistant", agent_name, cleaned)
            self.clear_status()
            self.new_chat_action.setEnabled(True)
        elif err_msg:
            self.append_message("assistant", self.agent.get_agent().name, err_msg)
            self.chat_history.add_entry("assistant", self.agent.get_agent().name, err_msg)
            self.scroll_down()
            self.clear_status()


    def extract_error_message(self, e) -> str:
        # Wenn e ein dict ist
        if isinstance(e, dict):
            return e.get("error", {}).get("message") or e.get("message") or str(e)

        # Versuche, die letzte geschweifte Klammer als dict zu interpretieren
        if isinstance(e, Exception):
            s = str(e)
            try:
                # Suche nach dict-artigem Text
                start = s.find("{")
                if start != -1:
                    d = ast.literal_eval(s[start:])
                    if isinstance(d, dict):
                        return d.get("error", {}).get("message") or d.get("message") or s
            except Exception:
                pass
            return s

        return str(e)

    def show_error(self, msg: str):
        QMessageBox.critical(
            self,
            "Fehler",
            msg,
            QMessageBox.StandardButton.Ok,
        )

    def append_message(self, role: str, name: str, message: str, **kwargs):
        html = None        

        if role == "user":
            html = self.renderer.render_userinput(name, message)
        elif role == "thinking" and setting_manager.get_setting("show_thinking", True):
            html = self.renderer.render_thinking(name, message)
        elif role == "assistant":
            html = self.renderer.render_agentresponse(name, message)
        elif role == "tool" and setting_manager.get_setting("show_tools", True):
            #tool_name = kwargs.get("tool_name", "unbekanntes Tool")
            parameters = kwargs.get("parameters", [])
            html = self.renderer.render_tool_call(name, parameters)        

        if html:
            if not self.chat_box.document().isEmpty() and self.renderer.should_line_break():
                self.chat_box.append('<div></div>')  # Absatzabstand
                #self.chat_box.append('<div style="margin-bottom: 0.2em;"</div>')  # Absatzabstand
            self.chat_box.append(html)

    def update_theme_menu_selection(self, theme_filename: str):
        """Aktualisiert die Auswahl im Theme-Dropdown-Menü der Toolbar."""
        for action in self.theme_group.actions():
            if action.data() == theme_filename:
                action.setChecked(True)
                break

    def apply_font_settings(self):
        settings = settings_manager.load_settings()
        font_family = settings.get("font_family", "")
        font_size = settings.get("font_size", 12)

        font = QFont()

        if font_family:
            if QFontDatabase().hasFamily(font_family):
                font.setFamily(font_family)
            else:
                print(f"⚠️ Font '{font_family}' nicht gefunden, Standard wird verwendet")
                font.setFamily("Sans Serif")
        else:
            font.setFamily("Sans Serif")

        font.setPointSize(int(font_size))
        self.chat_box.setFont(font)        
        self.input_edit.setFont(font)

        tracefont = QFont()
        if font_family:
            if QFontDatabase().hasFamily(font_family):
                tracefont.setFamily(font_family)
            else:            
                tracefont.setFamily("Sans Serif")
        else:
            tracefont.setFamily("Sans Serif")
        tracefont.setPointSize(int(font_size) - 2)
        self.trace_box.setFont(tracefont)


    def show_options_dialog(self):
        if self.agent_is_running:
            return
        settings = settings_manager.load_settings().copy()
        settings["openai_api_key"] = settings_manager.get_setting("openai_api_key", encrypted=True)
        settings["generic_api_key"] = settings_manager.get_setting("generic_api_key", encrypted=True)
        old_settings = settings.copy()

        dialog = OptionsDialog(self, settings)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.get_values()

            # 1. Neue Settings speichern
            openai_api_key_changed = values["openai_api_key"] != old_settings["openai_api_key"]
            values["openai_api_key"] = settings_manager.encrypt_value(values["openai_api_key"])
            generic_api_key_changed = values["generic_api_key"] != old_settings["generic_api_key"]
            values["generic_api_key"] = settings_manager.encrypt_value(values["generic_api_key"])
            settings_manager.save_settings(values)            

            # 2. Prüfen, ob Theme, Schrift oder Darstellungsstil geändert wurden
            theme_changed = values.get("theme_file") != old_settings.get("theme_file")
            font_changed = (
                values.get("font_family") != old_settings.get("font_family")
                or values.get("font_size") != old_settings.get("font_size")
            )
            style_changed = values.get("render_style") != old_settings.get("render_style")
            visibility_changed = (
                values.get("show_thinking") != old_settings.get("show_thinking")
                or values.get("show_tools") != old_settings.get("show_tools")
            )

            if theme_changed:
                self.theme = load_theme_colors(os.path.join("themes", values["theme_file"]))
                self.update_theme_menu_selection(values["theme_file"])

            if style_changed:                
                style = values["render_style"]
                if style == "standard":
                    self.renderer = DefaultMessageRenderer(theme=self.theme)
                else:
                    self.renderer = CompactMessageRenderer(theme=self.theme)

            if theme_changed or style_changed or visibility_changed:
                self.set_color_theme()

            if font_changed:
                self.apply_font_settings()

            # 3. Modell geändert? (Vorbereitung, noch keine Umschaltung implementiert)
            if (
                values.get("provider") != old_settings.get("provider")
                or values.get("openai_model") != old_settings.get("openai_model")
                or values.get("ollama_model") != old_settings.get("ollama_model")
                or values.get("generic_model") != old_settings.get("generic_model")
                or values.get("generic_endpoint") != old_settings.get("generic_endpoint")
                or values.get("generic_num_ctx") != old_settings.get("generic_num_ctx")
                or openai_api_key_changed
                or generic_api_key_changed
            ):
                print("⚙️ Neues Modell gewählt.")
                core.model_provider.reset_model()
                self.agent = recreate_agents() # resettet core.model_provider
                n_ctx = core.model_provider.get_model_ctx_size()
                self.chatmemory.update_context_size(n_ctx)
                self.show_status_model()                
                reset_token_count()
                self.show_status_tokens()
        
        self.show_status()
            
    def show_about_dialog(self):        
        dialog = AboutDialog(self)        
        dialog.show()            

    def showEvent(self, event):
        super().showEvent(event)
        return        

    # wird gerade nicht verwendet
    def check_about_dialog(self):
        if not setting_manager.get_setting("about_shown", False):
            setting_manager.set_setting("about_shown", True, do_save=True)            
            QTimer.singleShot(1000, self.show_about_dialog)

    def tool_confirmation_dialog(self, tool_name: str, parameters: List[Dict[str, str]], requires_confirmation: bool) -> bool:
        if requires_confirmation and setting_manager.get_setting("confirm_tool_calls", True):
            # Bestätigung anzeigen
            if parameters:
                param_text = "\n".join(f"{p['name']}: {shorten_value(p['value'], 80)}" for p in parameters)
            else:
                param_text = None
            if not param_text:
                param_text = self.tr("[keine]")
            
            msg_1 = self.tr("Tool-Aufruf:")
            msg_2 = self.tr("Parameter:")
            msg_3 = self.tr("Ausführen?")
            msg = f"{msg_1} {tool_name}\n\n{msg_2}\n{param_text}\n\n{msg_3}"
            result = QMessageBox.question(
                self,
                self.tr("Tool-Aufruf bestätigen"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if result != QMessageBox.StandardButton.Yes:
                return False        

        # Reinen Klartext für History-Log erzeugen
        tool_msg = f"Tool: {tool_name}\n"
        if parameters:
            for param in parameters:
                for key, value in param.items():
                    tool_msg += f"  - {key}: {value}\n"

        self.chat_history.add_entry(role="tool", name=tool_name, content=tool_msg.strip(), metadata={
            #"tool_name": tool_name,
            "parameters": parameters,
            "requires_confirmation": requires_confirmation
        })

        '''
        self.chatmemory.add_entry(
            role="assistent",
            content=tool_msg.strip()            
        )  
        '''      

        self.append_message("tool", tool_name, tool_msg.strip(), parameters=parameters)        
        self.scroll_down()
        
        return True
    
    def login(self):
        self.login_action.setEnabled(False)
        self.show_status(self.tr("Anmelden... (ESC zum Abbrechen)"))        
        get_graph_client().login_async(self.loginFinished.emit)

    def on_login_finished(self, ok, user):
        # wieder im GUI-Thread ausführen!
        if ok and user:
            self.update_auth_buttons(True)
            self.show_status_connection(True)
            name = user.get("displayName", self.tr("Unbekannt"))
            email = user.get("userPrincipalName", "")
            self.show_status_user(f"{name} ({email})")
            self.user_name = name
            self.agent.update_settings()

            # Next Line: ERROR: no running event loop
            asyncio.create_task(self.handle_input("system", self.tr("Der Benutzer hat sich bei Outlook angemeldet.")))            
        else:
            self.update_auth_buttons(False)
            self.show_status_connection(False)
            self.show_status_user()
            QMessageBox.critical(
                self,
                self.tr("Anmeldung fehlgeschlagen"),
                self.tr("Anmeldung wurde abgebrochen oder ist fehlgeschlagen.")
            )
        self.show_status("")

    def logout(self):
        self.show_status(self.tr("Abmelden..."))
        get_graph_client().logout(clear_cache=False)
        self.show_status_connection(False)
        self.show_status_user()        
        if self.agent:
            self.agent.update_settings()
        self.user_name = None
        self.update_auth_buttons(False)
        self.show_status()

    def update_auth_buttons(self, connected: bool):
        self.login_action.setEnabled(not connected)
        self.logout_action.setEnabled(connected)
    
    def save_window_state(self):
        settings = settings_manager.load_settings()

        if self.isMaximized():
            settings["window_maximized"] = True
        else:
            settings["window_maximized"] = False
            settings["window_width"] = max(400, self.width())
            settings["window_height"] = max(300, self.height())
            settings["window_x"] = max(0, self.x())
            settings["window_y"] = max(0, self.y())

        # Splitter hat eine Liste von Größen (in Pixeln)  
        sizes = self.splitter.sizes()          # z. B. [400, 200]  
        # Speichern als string, damit es in die Json/INI passt  
        settings["splitter_sizes"] = ",".join(map(str, sizes))

        settings_manager.save_settings(settings)

    def restore_window_state(self):
        settings = settings_manager.load_settings()

        max_width = 4096
        max_height = 2160
        max_x = 8192
        max_y = 8192

        width = int(settings.get("window_width", 900))
        height = int(settings.get("window_height", 600))
        x = int(settings.get("window_x", 100))
        y = int(settings.get("window_y", 100))
        maximized = settings.get("window_maximized", False)

        # Plausibilitätsprüfung
        if 200 <= width <= max_width and 200 <= height <= max_height:
            self.resize(width, height)
        if 0 <= x <= max_x and 0 <= y <= max_y:
            self.move(x, y)

        if maximized:
            self.showMaximized()        

    def bring_to_front(self):
        self.raise_()
        self.activateWindow()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)

    def closeEvent(self, event):
        get_graph_client().logout(clear_cache=False)
        self.save_window_state()
        super().closeEvent(event)
        #event.accept()


    def on_trace_complete(self, processor: LocalTraceProcessor):
        #print("📣 Trace-Ende empfangen im MainWindow.")
        processor.force_flush()
        self.render_trace_from_spans(processor.spans)                
    
    def render_trace_from_spans(self, spans: List[Span]):
        #print("render_trace_from_spans")
        if not spans:
            self.trace_box.setPlainText(self.tr("⚠️ Keine Spans vorhanden."))
            return
        
        lines = ["<h3>🔍 Trace-Spans</h3>"]

        for span in spans:
            try:
                span_data = span.export()
                inner = span_data.get("span_data", {})
            except Exception as e:
                lines.append(f"<div class='block error'>" + self.tr("❌ Fehler beim Exportieren eines Spans:") + f" {e}</div>")
                continue

            span_type = inner.get("type", "unknown")
            name = inner.get("name") or span_type or span.__class__.__name__
            error = span_data.get("error")

            span_class = "block"
            if error:
                span_class += " error"
            elif span_type == "tool":
                span_class += " tool"
            elif span_type == "agent":
                span_class += " agent"
            elif span_type == "generation":
                span_class += " llm"

            lines.append(f"<div class='{span_class}'>🧩 <span>{name}</span>")

            if inner.get("inputs"):
                inp = json.dumps(inner["inputs"], indent=2, ensure_ascii=False)
                lines.append(f"<div class='label'>📥 Inputs:</div><pre>{inp}</pre>")

            if inner.get("output") or inner.get("outputs"):
                out = inner.get("output") or inner.get("outputs")
                out_str = json.dumps(out, indent=2, ensure_ascii=False)
                lines.append(f"<div class='label'>📤 Outputs:</div><pre>{out_str}</pre>")

            if span_type == "generation" and isinstance(out, list):
                for o in out:
                    content = o.get("content")
                    if content and content.strip():
                        lines.append(f"<div class='thinking'>💭 {content.strip()}</div>")

            if error:
                lines.append(f"<div class='label'>❌ Error:</div><pre>{error}</pre>")

            lines.append("</div>")  # block

        html = "\n".join(lines)
        self.last_trace_box_html = html
        self.set_trace_box_content(html)                

    def set_trace_box_content(self, html: str):
        if not html:
            self.trace_box.setText("")
            return

        theme_colors = {
            "text": self.theme["Base2"],
            "agent": self.theme["Base2"],
            "tool": self.theme["Base2"],
            "llm": self.theme["Base2"],
            "error": self.theme["Red"]
        }

        css = f"""
        <style>
            body {{ color: {theme_colors['text']};}}
            .agent   {{ color: {theme_colors['agent']};}}
            .tool    {{ color: {theme_colors['tool']};}}
            .llm     {{ color: {theme_colors['llm']};}}
            .error   {{ color: {theme_colors['error']};}}
            pre      {{ white-space: pre-wrap; font-family: monospace; }}
            .block   {{ margin-bottom: 1em; }}
            .label   {{ font-weight: bold; }}
            .thinking {{ margin: 0.5em 0; }}
        </style>
        """

        self.trace_box.setHtml(css + "\n" + html)

    def render_trace_to_gui(self, processor: LocalTraceProcessor):
        trace = processor.trace
        if not trace:
            self.trace_box.setPlainText(self.tr("⚠️ Keine Traces gefunden."))
            return

        tracedict = trace.export()
        print()
        print(tracedict)
        print()

        #trace = traces[-1]
        lines = [f"<h2>Trace: {trace.name}</h2>"]

        tracedict = trace.export()

        for call in tracedict.get["calls"]:
            lines.append(f"<h3>🔄 Call: {call['name']}</h3>")

            if "inputs" in call:
                inp = json.dumps(call["inputs"], indent=2, ensure_ascii=False)
                lines.append(f"<b>📥 Inputs:</b><pre>{inp}</pre>")

            if "outputs" in call:
                out = json.dumps(call["outputs"], indent=2, ensure_ascii=False)
                lines.append(f"<b>📤 Outputs:</b><pre>{out}</pre>")

            for step in call.get("children", []):
                lines.append(f"<h4>🧩 Step: {step.get('name', '???')}</h4>")
                if "inputs" in step:
                    i = json.dumps(step["inputs"], indent=2, ensure_ascii=False)
                    lines.append(f"<b>Inputs:</b><pre>{i}</pre>")
                if "outputs" in step:
                    o = json.dumps(step["outputs"], indent=2, ensure_ascii=False)
                    style = "color:red" if "error" in o.lower() else "color:green"
                    lines.append(f"<b>Outputs:</b><pre style='{style}'>{o}</pre>")

        #self.trace_box.setHtml("\n".join(lines))
        self.trace_box.append("\n".join(lines))
        cursor = self.trace_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.trace_box.setTextCursor(cursor)
        self.trace_box.ensureCursorVisible()
