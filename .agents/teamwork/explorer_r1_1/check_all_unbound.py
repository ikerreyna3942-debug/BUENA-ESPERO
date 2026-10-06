import ast

with open("modules/prompt_studio_v4.py", "r", encoding="utf-8-sig", errors="ignore") as f:
    code = f.read()

tree = ast.parse(code, "modules/prompt_studio_v4.py")

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
        for arg in node.args.args:
            assigned.add(arg.arg)
        
        # Check standard builtins and module globals
        import builtins
        builtin_names = set(dir(builtins))
        
        # Find global names in module
        global_names = set()
        for mod_node in tree.body:
            if isinstance(mod_node, (ast.FunctionDef, ast.ClassDef)):
                global_names.add(mod_node.name)
            elif isinstance(mod_node, ast.Assign):
                for target in mod_node.targets:
                    if isinstance(target, ast.Name):
                        global_names.add(target.id)
            elif isinstance(mod_node, (ast.Import, ast.ImportFrom)):
                for alias in mod_node.names:
                    global_names.add(alias.asname or alias.name)
                    
        unbound = []
        for name, lineno in loaded:
            if name not in assigned and name not in global_names and name not in builtin_names:
                unbound.append((name, lineno))
        if unbound:
            print(f"Function {node.name}() has potential unbound names:")
            for name, lineno in unbound:
                print(f"  Line {lineno}: {name}")
