from markdown_it import MarkdownIt
from abc import ABC, abstractmethod
import html
import re
#from gui.translations import tr

def strip_p_tags(text: str) -> str:
  """Entfernt führende und endende <p> Tags aus einem String.

  Args:
    text: Der String, aus dem die Tags entfernt werden sollen.

  Returns:
    Der String ohne führende und endende <p> Tags.
  """
  text = re.sub(r'^<p>|</p>$', '', text)  # Entfernt <p> am Anfang und </p> am Ende
  text = text.strip() # Entfernt Whitespace am Anfang und Ende.
  return text

def tabs_to_spaces(text: str, n_spaces: int = 4) -> str:  
        """  
        Ersetzt jedes Tab-Zeichen (`\t`) im Text durch `n_spaces` Leerzeichen.  
        """  
        return text.expandtabs(n_spaces)          # gleichbedeutend mit text.replace('\t', ' ' * n_spaces)  

def leading_spaces_to_nbsp(text: str) -> str:  
    """  
    Ersetzt **alle führenden** Leerzeichen in jeder Zeile von *text* durch  
    das HTML‑Entität `&nbsp;`.    
    Tabs bleiben unberührt – falls du sie ebenfalls in HTML‑Entitäten  
    umwandeln willst, musst du vorher `expandtabs` aufrufen.  
  
    Parameters  
    ----------  
    text : str  
        Der Eingabetext (kann mehrere Zeilen enthalten).  
  
    Returns  
    -------  
    str  
        Der Text mit ersetzt führende Leerzeichen.  
    """  
    # Der Regex findet die führenden Leerzeichen einer Zeile  
    return re.sub(r'^( +)', lambda m: '&nbsp;' * len(m.group()), text, flags=re.MULTILINE)  


def pre_wrap_html(text: str) -> str:
    if not text:
        return ""
    safe = html.escape(text)    
    safe = safe.expandtabs(4)
    safe = safe.replace("  ", "&nbsp;&nbsp;")  # Doppelte Leerzeichen
    
    lines = []
    for line in safe.split("\n"):
        if line.startswith(" "):  # einzelnes führendes Leerzeichen
            line = "&nbsp;" + line[1:]        
        lines.append(line)    
    return "<br>\n".join(lines)


class BaseMessageRenderer(ABC):
    def __init__(self, theme: dict):
        self.theme = theme    
        self.md = MarkdownIt("commonmark")

    def set_theme(self, theme: dict):
        self.theme = theme

    @abstractmethod
    def should_line_break(self) -> bool:
        pass

    @abstractmethod
    def render_userinput(self, name: str, content: str) -> str:
        pass

    @abstractmethod
    def render_thinking(self, name: str, content: str) -> str:
        pass

    @abstractmethod
    def render_agentresponse(self, name: str, content: str) -> str:
        pass

    @abstractmethod
    def render_tool_call(self, tool_name: str, parameters: list[dict[str, str]]) -> str:
        pass    
    

class DefaultMessageRenderer(BaseMessageRenderer):
    def should_line_break(self) -> bool:
        return False

    def render_userinput(self, name: str, content: str) -> str:
        color = self.theme.get("Base3", "#eee")
        gray = self.theme.get("Base00", "#999")        
        rendered = pre_wrap_html(content)
        return f"""
        <div style="color:{color};">
            <b style="color:{gray};">👤 {name}:</b><p>{rendered}</p>
        </div><div></div>
        """

    def render_thinking(self, name: str, content: str) -> str:
        if isinstance(content, list):
            content = "\n".join(content)

        color = self.theme.get("Base00", "#999")        
        rendered = self.md.render(content.replace("\n", "  \n")).strip()        
        #rendered = "<br>" + strip_p_tags(rendered) + "</br>"
        return f"""
        <div style="color:{color};">
            <b style="color:{color};">🤖 {name} thinking:</b> {rendered}
        </div><div></div>
        """

    def render_agentresponse(self, name: str, content: str) -> str:
        color = self.theme.get("Base3", "#eee")
        gray = self.theme.get("Base00", "#999")
        rendered = self.md.render(content.replace("\n", "  \n")).strip()        
        #rendered = "<br>" + strip_p_tags(rendered) + "</br>"
        return f"""
        <div style="color:{color};">
            <b style="color:{gray};">🤖 {name}:</b> {rendered}
        </div><div></div>
        """

    def render_tool_call(self, tool_name: str, parameters: list[dict[str, str]]) -> str:
        color = self.theme.get("Base00", "#999")
        name_color = self.theme.get("Base1", "#aaa")
        if parameters:
            param_list = "\n".join(
                f"<li><b>{p['name']}:</b> {p['value']}</li>" for p in parameters
            )
        else:
            param_list = ""
        return f"""        
        <div style="color:{color};">
            <b style="color:{name_color}">🛠 Tool:</b> {tool_name}
            <ul>{param_list}</ul>
        </div><div></div>
        """

class CompactMessageRenderer(BaseMessageRenderer):
    def should_line_break(self) -> bool:
        return False
    
    def render_userinput(self, name: str, content: str) -> str:
        #color = self.theme.get("Base1", "#ccc")
        color = self.theme.get("Base3", "#fff")        
        rendered = pre_wrap_html(content)
        return f'<div style="color:{color};">👤: {rendered}</div><div></div>'

    def render_thinking(self, name: str, content: str) -> str:
        if isinstance(content, list):
            content = "\n".join(content)
        color = self.theme.get("Base00", "#888")
        rendered = self.md.render(content.replace("\n", "  \n")).strip()
        rendered = strip_p_tags(rendered)
        return f"<div style='color:{color};'>💭: {rendered}</div><div></div>"

    def render_agentresponse(self, name: str, content: str) -> str:
        color = self.theme.get("Base3", "#fff")
        rendered = self.md.render(content.replace("\n", "  \n")).strip()
        rendered = strip_p_tags(rendered)
        return f"<div style='color:{color};'>🤖: {rendered}</div><div></div>"

    def render_tool_call(self, tool_name: str, parameters: list[dict[str, str]]) -> str:
        color = self.theme.get("Base00", "#999")
        if parameters:
            param_list = " ".join(f"{p['name']}={p['value']}" for p in parameters)
        else:
            param_list = ""
        return f"<div style='color:{color};'><b>🛠 {tool_name}</b>: {param_list}</div><div></div>"
