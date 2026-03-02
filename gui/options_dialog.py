# gui/options_dialog.py

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QProxyStyle, QScrollArea,
    QRadioButton, QLineEdit, QComboBox, QPushButton, QLabel, QGroupBox, QButtonGroup, 
    QStyleFactory, QFontComboBox, QSpinBox, QCheckBox, QFileDialog, QSizePolicy,
    QDialogButtonBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette  # Add this import

from PySide6.QtCore import QCoreApplication

from core.model_provider import list_tool_capable_ollama_models, list_openai_models
from gui.theme_loader import theme_choices
from gui.qt_extensions import NoScrollComboBox

class OptionsDialog(QDialog):
    def __init__(self, parent=None, settings: dict = None):
        super().__init__(parent)        

        self.settings = settings if settings else {}
                
        self.setWindowTitle(self.tr("Optionen"))
        self.setModal(True)        

        self.setFixedSize(480, 420)

        #Test
        # Windows-ähnliches Style aktivieren        
        self.setStyle(QStyleFactory.create("Fusion"))

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self._create_model_tab()
        self._create_view_tab()
        self._create_security_tab()
        self._create_directories_tab()
        layout.addWidget(self.tabs)

        # ButtonBox mit OK + Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )        

        # Signale verbinden
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)

        self._load_settings()

        self._update_enabled_fields()
    
    def _create_model_tab(self):
        # === Scrollbarer Tab ===
        model_scroll_area = QScrollArea()
        model_scroll_area.setWidgetResizable(True)  # wichtig: Inhalt anpassen

        model_tab = QWidget()
        tab_layout = QVBoxLayout(model_tab)

        # OpenAI Auswahl
        self.openai_radio = QRadioButton("OpenAI")
        self.openai_key_edit = QLineEdit()
        self.openai_key_edit.setPlaceholderText(self.tr("API-Key eingeben"))
        self.openai_model_combo = NoScrollComboBox()
        models = list_openai_models()
        self.openai_model_combo.addItems(models)

        # Ollama Auswahl
        self.ollama_radio = QRadioButton(self.tr("Lokales Modell (Ollama)"))
        self.ollama_model_combo = NoScrollComboBox()

        # Generic Auswahl        
        self.generic_radio = QRadioButton(self.tr("Generische OpenAI kompatible API"))
        self.generic_endpoint = QLineEdit()
        self.generic_key_edit = QLineEdit()
        self.generic_model = QLineEdit()
        self.generic_num_ctx = QSpinBox()
        self.generic_num_ctx.setRange(2048, 100_000_000)
        self.generic_num_ctx.setValue(4096)        

        # Modelle abrufen
        try:            
            model_list = list_tool_capable_ollama_models()            
            self.ollama_model_combo.addItems(model_list)

            #model_list = get_tool_capable_models()
            #self.ollama_model_combo.addItems([m["name"] for m in model_list])
        except Exception as e:
            #self.ollama_model_combo.addItem("(Fehler beim Laden)")        
            pass

        # Gruppe OpenAI
        openai_group = QGroupBox()
        openai_layout = QVBoxLayout(openai_group)
        openai_layout.addWidget(self.openai_radio)
        self.label_openai_apikey = QLabel("API-Key:")
        openai_layout.addWidget(self.label_openai_apikey)
        openai_layout.addWidget(self.openai_key_edit)
        self.label_openai_model = QLabel(self.tr("OpenAI Modell auswählen:"))
        openai_layout.addWidget(self.label_openai_model)
        openai_layout.addWidget(self.openai_model_combo)

        # Gruppe Ollama
        ollama_group = QGroupBox()
        ollama_layout = QVBoxLayout(ollama_group)
        ollama_layout.addWidget(self.ollama_radio)
        self.label_ollama_model = QLabel(self.tr("Modell auswählen:"))
        ollama_layout.addWidget(self.label_ollama_model)
        ollama_layout.addWidget(self.ollama_model_combo)

        # Gruppe Generic
        generic_group = QGroupBox()
        generic_layout = QVBoxLayout(generic_group)
        generic_layout.addWidget(self.generic_radio)
        self.label_generic_endpoint = QLabel("API Endpoint (URL):")
        generic_layout.addWidget(self.label_generic_endpoint)
        generic_layout.addWidget(self.generic_endpoint)
        self.label_generic_apikey = QLabel("API-Key:")
        generic_layout.addWidget(self.label_generic_apikey)
        generic_layout.addWidget(self.generic_key_edit)

        hbox = QHBoxLayout()
        hbox.setContentsMargins(0, 0, 0, 0)   # außen
        hbox.setSpacing(10)

        # === Feld 1 ===
        generic_name_widget = QWidget()
        generic_name_layout = QVBoxLayout(generic_name_widget)
        generic_name_layout.setContentsMargins(0, 0, 0, 0)   # außen
        #generic_name_layout.setSpacing(0)
        self.label_generic_model = QLabel(self.tr("Modell Name:"))
        generic_name_layout.addWidget(self.label_generic_model)
        generic_name_layout.addWidget(self.generic_model)

        # === Feld 2 ===
        generic_ctx_widget = QWidget()
        generic_ctx_layout = QVBoxLayout(generic_ctx_widget)
        generic_ctx_layout.setContentsMargins(0, 0, 0, 0)   # außen
        #generic_ctx_layout.setSpacing(0)
        self.label_generic_num_ctx = QLabel("Num CTX:")
        generic_ctx_layout.addWidget(self.label_generic_num_ctx)
        generic_ctx_layout.addWidget(self.generic_num_ctx)

        # === In die horizontale Reihe packen ===
        hbox.addWidget(generic_name_widget)
        hbox.addWidget(generic_ctx_widget)

        generic_layout.addLayout(hbox)

        # In Layout einfügen
        tab_layout.addWidget(openai_group)
        tab_layout.addWidget(ollama_group)
        tab_layout.addWidget(generic_group)
        tab_layout.addStretch()

        model_scroll_area.setWidget(model_tab)

        self.tabs.addTab(model_scroll_area, self.tr("Modell"))

        # Button-Gruppe erzeugen
        self.model_group = QButtonGroup(self)
        self.model_group.addButton(self.openai_radio)
        self.model_group.addButton(self.ollama_radio)        
        self.model_group.addButton(self.generic_radio)
        
        # Standardauswahl
        self.openai_radio.setChecked(True)

        self.model_group.buttonClicked.connect(
            lambda _: self._update_enabled_fields()
        )

        """
        self.openai_radio.toggled.connect(
            lambda checked: self._update_enabled_fields())        
        """

    def _create_view_tab(self):
        view_tab = QWidget()
        view_layout = QVBoxLayout(view_tab)

        # Thema
        self.theme_combo = QComboBox()        
        for filename, label in theme_choices.items():
            self.theme_combo.addItem(label, filename)        
        view_layout.addWidget(QLabel(self.tr("Thema:")))
        view_layout.addWidget(self.theme_combo)

        # Schrift
        self.font_combo = QFontComboBox()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 36)
        self.font_size_spin.setValue(12)
        view_layout.addWidget(QLabel(self.tr("Schriftart:")))
        view_layout.addWidget(self.font_combo)
        view_layout.addWidget(QLabel(self.tr("Schriftgröße:")))
        view_layout.addWidget(self.font_size_spin)

        # Darstellung
        self.render_style_combo = QComboBox()        
        self.render_style_combo.addItem(self.tr("Standard"), "standard")
        self.render_style_combo.addItem(self.tr("Kompakt"), "compact")
        view_layout.addWidget(QLabel(self.tr("Darstellung:")))
        view_layout.addWidget(self.render_style_combo)

        # Checkboxen
        self.show_thinking_check = QCheckBox(self.tr("Thinking anzeigen"))
        self.show_tools_check = QCheckBox(self.tr("Tool-Aufrufe anzeigen"))
        view_layout.addWidget(self.show_thinking_check)
        view_layout.addWidget(self.show_tools_check)

        view_layout.addStretch()
        self.tabs.addTab(view_tab, self.tr("Ansicht"))

    def _create_security_tab(self):
        sec_tab = QWidget()
        sec_layout = QVBoxLayout(sec_tab)        

        # Checkbox Tool-Aufrufe
        self.confirm_tools_check = QCheckBox(self.tr("Jeden Tool-Aufruf bestätigen"))
        sec_layout.addWidget(self.confirm_tools_check)
        
        sec_layout.addStretch()
        self.tabs.addTab(sec_tab, self.tr("Sicherheit"))

    def _create_directories_tab(self):
        dir_tab = QWidget()
        dir_layout = QVBoxLayout(dir_tab)
        
        # Label oben
        self.workspace_label = QLabel(self.tr("Arbeitsbereich"))
        dir_layout.addWidget(self.workspace_label)

        # Zeile mit Textfeld + Button
        hbox = QHBoxLayout()
        self.workspace_dir = QLineEdit()
        self.workspace_button = QPushButton("...")

        # Button auf minimale Breite shrinken
        #self.workspace_button.setMinimumWidth(16)
        self.workspace_button.setMaximumWidth(24)
        self.workspace_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        #self.workspace_button.setFixedWidth(self.workspace_button.sizeHint().width())

        hbox.addWidget(self.workspace_dir)
        hbox.addWidget(self.workspace_button)
        hbox.setStretch(1, 0)

        dir_layout.addLayout(hbox)

        # Aktion: Ordnerdialog
        self.workspace_button.clicked.connect(self.select_directory)

        dir_layout.addStretch()
        self.tabs.addTab(dir_tab, self.tr("Verzeichnisse"))

    def select_directory(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Arbeitsbereich auswählen"), options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            self.workspace_dir.setText(path)
            self.workspace_dir.setSelection(0, 0)

    def _update_enabled_fields(self):        
        idx = 0
        if self.ollama_radio.isChecked():
            idx = 1
        elif self.generic_radio.isChecked():
            idx = 2

        self.openai_key_edit.setEnabled(idx==0)
        self.openai_model_combo.setEnabled(idx==0)
        self.label_openai_apikey.setEnabled(idx==0)
        self.label_openai_model.setEnabled(idx==0)

        self.label_ollama_model.setEnabled(idx==1)
        self.ollama_model_combo.setEnabled(idx==1)        

        self.label_generic_endpoint.setEnabled(idx==2)
        self.generic_endpoint.setEnabled(idx==2)
        self.label_generic_apikey.setEnabled(idx==2)
        self.generic_key_edit.setEnabled(idx==2)
        self.label_generic_model.setEnabled(idx==2)
        self.generic_model.setEnabled(idx==2)
        self.label_generic_num_ctx.setEnabled(idx==2)
        self.generic_num_ctx.setEnabled(idx==2)

    def _load_settings(self):
        if not self.settings:
            return
        s = self.settings

        current_theme = s.get("theme_file", "solarized_dark.json")
        index = self.theme_combo.findData(current_theme)
        if index != -1:
            self.theme_combo.setCurrentIndex(index)
        
        self.font_combo.setCurrentText(s.get("font_family", "DejaVu Sans Mono"))
        self.font_size_spin.setValue(s.get("font_size", 12))

        key = s.get("render_style", "standard")
        index = self.render_style_combo.findData(key)
        if index != -1:
            self.render_style_combo.setCurrentIndex(index)
        
        self.show_thinking_check.setChecked(s.get("show_thinking", True))
        self.show_tools_check.setChecked(s.get("show_tools", True))
        self.confirm_tools_check.setChecked(s.get("confirm_tool_calls", True))
        
        # Model
        provider = s.get("provider", "openai")
        if provider == "openai":
            self.openai_radio.setChecked(True)
        elif provider == "ollama":
            self.ollama_radio.setChecked(True)
        else:
            self.generic_radio.setChecked(True)
        self.ollama_model_combo.setCurrentText(s.get("ollama_model"))
        self.openai_model_combo.setCurrentText(s.get("openai_model"))        
        self.openai_key_edit.setText(s.get("openai_api_key"))
        self.openai_key_edit.setSelection(0, 0)
        self.generic_endpoint.setText(s.get("generic_endpoint"))
        self.generic_key_edit.setText(s.get("generic_api_key"))
        self.generic_key_edit.setSelection(0, 0)
        self.generic_model.setText(s.get("generic_model"))
        self.generic_num_ctx.setValue(s.get("generic_num_ctx", 32_000))

        # Verzeichnisse
        self.workspace_dir.setText(s.get("workspace_dir"))
        self.workspace_dir.setSelection(0, 0)

    def get_values(self):        
        if self.openai_radio.isChecked():
            provider = "openai"
        elif self.ollama_radio.isChecked():
            provider = "ollama"
        else:
            provider = "generic"

        options = {
            # Modellseite
            "openai_api_key": self.openai_key_edit.text().strip(),
            "openai_model": self.openai_model_combo.currentText(),
            "ollama_model": self.ollama_model_combo.currentText(),
            "generic_endpoint": self.generic_endpoint.text().strip(),
            "generic_api_key": self.generic_key_edit.text().strip(),
            "generic_model":  self.generic_model.text().strip(),
            "generic_num_ctx": self.generic_num_ctx.value(),
            "provider": provider,

            # Ansicht
            "theme_file": self.theme_combo.currentData(),
            "font_family": self.font_combo.currentText(),
            "font_size": self.font_size_spin.value(),
            "render_style": self.render_style_combo.currentData(),            
            "show_thinking": self.show_thinking_check.isChecked(),
            "show_tools": self.show_tools_check.isChecked(),

            # Sicherheit
            "confirm_tool_calls": self.confirm_tools_check.isChecked(),

            # Verzeichnisse
            "workspace_dir": self.workspace_dir.text().strip(),
        }
        return options
