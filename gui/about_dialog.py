# about_dialog.py

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox, QTextBrowser, QFrame, QStyleFactory
)
from PySide6.QtGui import QPixmap, QFont, QCursor
from PySide6.QtCore import Qt, QUrl
import webbrowser

APP_VERSION = "0.8.0 beta"
INFO_URL = "https://github.com/kroll-software/AI-Outlook-Manager"

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Über Outlook-Manager"))
        self.setModal(True)
        self.setFixedWidth(500)

        self.setStyle(QStyleFactory.create("Fusion"))        

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Logo
        pixmap = QPixmap(os.path.join("assets", "kroll-software-logo.png"))
        logo_label = QLabel()
        logo_label.setPixmap(pixmap.scaledToWidth(150, Qt.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setMargin(8)
        layout.addWidget(logo_label)

        # Titel
        title = QLabel("<b>AI Outlook-Manager</b>")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # Version
        version = QLabel(self.tr("Version") + f": {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        # Info-Text
        info = QLabel(self.tr("Aktuelle Version und Infos finden Sie unter:"))
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)

        # Info-Link
        link = QLabel(f'<a href="{INFO_URL}">View on GitHub</a>')
        link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        layout.addWidget(link)

        # Trenner oder Abstand
        layout.addSpacing(10)

        # Lizenztext in Box
        license_box = QTextBrowser()
        license_box.setHtml(
            '<div align="center" style="font-size: 10pt;">'
            '<p><b>Released under the MIT License</b></p>'
            '<p>Copyright © 2025-2026 Detlef Kroll / Kroll Software-Entwicklung.</p>'
            '<p style="color: #666;">Permission is granted to use, copy, modify, and distribute '
            'this software freely, provided the original license and copyright notice are included.</p>'
            '<p><b>Disclaimer:</b> Provided "as is" without any warranty. Use at your own risk!</p>'
            '</div>'
        )
        license_box.setReadOnly(True)
        license_box.setFrameShape(QFrame.NoFrame)
        license_box.setStyleSheet("background: transparent;")
        license_box.setMaximumHeight(180)
        layout.addWidget(license_box)

        # OK-Button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)
