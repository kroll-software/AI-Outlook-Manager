# gui/theme_loader.py
import json
from PySide6.QtCore import QCoreApplication

# themes/solarized.json

theme_choices = {}

def init_themes():    
    theme_choices.clear()
    theme_choices.update({
        "solarized_dark.json": QCoreApplication.translate("theme_loader", "Solarized (dunkel)"),
        "solarized_light.json": QCoreApplication.translate("theme_loader", "Solarized (hell)"),
        "monokai_dark.json": QCoreApplication.translate("theme_loader", "Monokai (dunkel)"),
        "monokai_light.json": QCoreApplication.translate("theme_loader", "Monokai (hell)")
    })

fallback_color = """
{
  "Base03": "#002B36",
  "Base02": "#073642",
  "Base01": "#586E75",
  "Base00": "#657B83",
  "Base0": "#839496",
  "Base1": "#93A1A1",
  "Base2": "#EEE8D5",
  "Base3": "#FDF6E3",

  "Yellow": "#B58900",
  "Orange": "#CB4B16",
  "Red": "#DC322F",
  "Magenta": "#D33682",
  "Violet": "#6C71C4",
  "Blue": "#268BD2",
  "Cyan": "#2AA198",
  "Green": "#859900",

  "White": "#FFFFFF",
  "Black": "#000000",
  "Silver": "#CED4DF",

  "GrayButton": "#CED4DF",
  "LightGrayButton": "#EDEFF3",

  "HighLightButton": "#FFECB5",
  "LightHighLightButton": "#FFF AED",
  "HighLightButtonBorder": "#E5C365",

  "HighLightYellow": "#F1F3F8",
  "HighLightBlue": "#268BD2",
  "HighLightBlueTransparent": "#64268BD2"
}
"""

def validate_colors(colors: dict) -> bool:
    if not colors:
        return False
    default = json.loads(fallback_color)
    a = list(default.keys())
    b = list(colors.keys())
    for key in b:
        if not key in a:
            return False
    return True

def load_theme_colors(json_path):
    try:
        with open(json_path, "r") as f:
            colors = json.load(f)
        if not validate_colors(colors):
            raise
    except:
        colors = json.loads(fallback_color)
    return colors
