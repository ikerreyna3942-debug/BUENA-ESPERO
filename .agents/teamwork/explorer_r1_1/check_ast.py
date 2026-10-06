import ast
import sys

def check_file(filename):
    print(f"=== Checking {filename} ===")
    with open(filename, "r", encoding="utf-8-sig", errors="ignore") as f:
        code = f.read()
    try:
        tree = ast.parse(code, filename)
        print("AST parsing: SUCCESS")
    except SyntaxError as e:
        print(f"SyntaxError: {e}")
        return

    # Check unbound names inside functions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            assigned = set()
            loaded = []
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    if isinstance(child.ctx, ast.Store):
                        assigned.add(child.id)
                    elif isinstance(child.ctx, ast.Load):
                        loaded.append((child.id, child.lineno))
            # Parameters
            for arg in node.args.args:
                assigned.add(arg.arg)
            # Find names loaded before assigned, or not assigned
            for target in ['medidas_usuario', 'lugar_casa_usuario', 'tipo_mueble_usuario', 'notas_vistas_usuario']:
                loads = [lineno for name, lineno in loaded if name == target]
                stores = target in assigned
                print(f"  Var '{target}' in {node.name}(): assigned={stores}, used_at_lines={loads}")

check_file("main.py")
check_file("modules/prompt_studio_v4.py")
