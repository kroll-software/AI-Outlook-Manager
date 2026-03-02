# math_agent.py

import io
import contextlib
import ast
import asyncio
import textwrap
from typing import List, Dict
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
import textwrap

from PySide6.QtCore import QCoreApplication
# tr_context = "math_agent"

class MathAgent(BaseAgent):
    def get_name(self) -> str:
        return "Math and Python-Coding Agent"
    
    def get_handoff_description(self):
        return "Can run python code to answer any math question correctly."
    
    def get_system_prompt(self) -> str:
        return """
        You're a math expert and a good programmer.
        For difficult tasks, you write and execute Python code.
        
        Don't just think, always give an answer!
        """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [
            run_safe_python_code,
            list_installed_python_libraries,
            get_user_info, 
            get_system_time
        ]

@function_tool
async def run_safe_python_code(code: str) -> str:
    """
    Executes Python code and returns the output from stdout.
    """

    if code:
        code = code.replace("\\n", "\n")

    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "code", "value": code})

    if not confirm_tools_call(QCoreApplication.translate("math_agent", "Code ausführen"), parameters, True):
        return cancelled_by_user_message()

    return await run_sandboxed_python(code, timeout=10.0)

# Modul-Importe, die erlaubt sind (kannst du erweitern)
ALLOWED_IMPORTS = {
    "math",
    "random",
    "datetime",
    "decimal",
    "fractions"
}

# Verbotene Funktionsnamen (Aufruf über Name)
FORBIDDEN_CALLS = {
    "eval", "exec", "open", "__import__", "compile", "globals", "locals", "vars", "input", "exit", "quit"
}

SAFE_BUILTINS = {
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "round": round,
    "sorted": sorted,
    "range": range,
    "all": all,
    "any": any,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "print": print,
}

SAFE_BUILTINS = {}

def is_safe_code(code: str) -> bool:
    """
    Checks whether the passed Python code is safe.

    Allows:
    - only imports from ALLOWED_IMPORTS
    - no dangerous calls (eval, exec, open, __import__, etc.)
    - no access to __builtins__.__dict__

    Returns True if safe; otherwise, an exception with the error reason is thrown.
    """
    try:
        tree = ast.parse(code, mode="exec")

        for node in ast.walk(tree):

            # ⛔ Import-Statement: Nur erlaubte Module zulassen
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod not in ALLOWED_IMPORTS:
                        raise ValueError(f"Import of '{mod}' is not allowed.")

            # ⛔ from x import y
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import of '{mod}' is not allowed.")

            # ⛔ Verbotene Funktionsaufrufe wie eval(), open(), etc.
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    # Blacklist
                    if isinstance(node.func, ast.Name) and func_name in FORBIDDEN_CALLS:
                        raise ValueError(f"Forbidden function call: '{func_name}()' is not allowed.")
                    if len(SAFE_BUILTINS) > 0 and func_name not in SAFE_BUILTINS:
                        raise ValueError(f"Forbidden function call: '{func_name}()' is not allowed.")
                elif isinstance(node.func, ast.Attribute):
                    # Optional: Warnung bei Dingen wie __builtins__.__dict__
                    full_attr = ast.unparse(node.func)
                    if "builtins" in full_attr and "__" in full_attr:
                        raise ValueError(f"Access to '{full_attr}' is not allowed.")

            # ⛔ Verbotene Attribute wie __builtins__.__dict__
            elif isinstance(node, ast.Attribute):
                full_attr = ast.unparse(node)
                if "builtins" in full_attr and "__" in full_attr:
                    raise ValueError(f"Access to '{full_attr}' is not allowed.")

        return True

    except SyntaxError as e:
        raise ValueError(f"Syntax error in code: {e.msg} (line {e.lineno})") from e

    except Exception as e:
        # Alle anderen Fehler (z. B. ValueError aus Checks)
        raise e


async def run_sandboxed_python(code: str, timeout: float | None = 2.0) -> str:
    print("Using sandboxed Python execution")    

    if not code:
        return "code is empty."
    code = code.replace("\\n", "\n")
    #code = textwrap.dedent(code.strip())

    try:
        is_safe_code(code)        
    except Exception as e:
        print(str(e))
        return str(e)

    output = io.StringIO()
    
    # Lokaler Snapshot der aktuellen Umgebung (möglichst minimal gehalten)
    safe_globals = globals().copy()    

    # Manuell kritische Keys entfernen – nur zur Sicherheit
    for key in ("os", "sys", "io", "subprocess", "contextlib", "builtins"):
        safe_globals.pop(key, None)    

    try:
        compiled = compile(code, filename="<sandbox>", mode="exec")
        
        def exec_sync():
            with contextlib.redirect_stdout(output):
                exec(compiled, safe_globals)        

        if timeout is not None and timeout > 0:
            await asyncio.wait_for(asyncio.to_thread(exec_sync), timeout=timeout)
        else:
            await asyncio.to_thread(exec_sync)

    except asyncio.TimeoutError:
        print("Timeout Error")
        return "⏱ Error: Execution took too long (timeout)."
    except Exception as e:
        print(str(e))
        return f"❌ Error during execution: {e}"

    result_string = output.getvalue().strip()
    if result_string:
        return result_string
            
    try:
        tree = ast.parse(code, mode="exec")
        last_node = tree.body[-1]
        if isinstance(last_node, ast.Expr):
            expr = ast.Expression(last_node.value)
            value = eval(compile(expr, "<expr>", mode="eval"), safe_globals)
            result = f"{ast.unparse(last_node.value)} = {value!r}"
        else:
            result = "✅ Code executed (no custom output)"
    except Exception as e:
        print(str(e))
        result = f"❌ Error evaluating the last expression: {e}"
    return result
    

@function_tool
def list_installed_python_libraries() -> str:    
    ''' List all available python libs '''    
    import pkg_resources
    print("Using list_installed_python_libraries")
    installed_packages = pkg_resources.working_set
    installed_packages_list = sorted(["%s==%s" % (i.key, i.version) for i in installed_packages])
    return "\n".join(installed_packages_list)
