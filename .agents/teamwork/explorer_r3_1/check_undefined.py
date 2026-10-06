import ast
import sys
import glob
import builtins

builtin_names = set(dir(builtins))

class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.defs = set()

    def add(self, name):
        self.defs.add(name)

    def is_defined(self, name):
        if name in self.defs:
            return True
        if self.parent:
            return self.parent.is_defined(name)
        return False

class NameFinder(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.current_scope = Scope()
        self.undefined = []

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.current_scope.add(name)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.current_scope.add(name)

    def visit_FunctionDef(self, node):
        self.current_scope.add(node.name)
        func_scope = Scope(self.current_scope)
        # Arguments
        for a in node.args.args + node.args.kwonlyargs:
            func_scope.add(a.arg)
        if node.args.vararg:
            func_scope.add(node.args.vararg.arg)
        if node.args.kwarg:
            func_scope.add(node.args.kwarg.arg)
        
        old_scope = self.current_scope
        self.current_scope = func_scope
        for stmt in node.body:
            self.visit(stmt)
        self.current_scope = old_scope

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        self.current_scope.add(node.name)
        class_scope = Scope(self.current_scope)
        old_scope = self.current_scope
        self.current_scope = class_scope
        for stmt in node.body:
            self.visit(stmt)
        self.current_scope = old_scope

    def _extract_targets(self, target):
        if isinstance(target, ast.Name):
            self.current_scope.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._extract_targets(elt)
        elif isinstance(target, ast.Starred):
            self._extract_targets(target.value)

    def visit_Assign(self, node):
        self.visit(node.value)
        for t in node.targets:
            self._extract_targets(t)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        self.visit(node.target)

    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
        self._extract_targets(node.target)

    def visit_For(self, node):
        self.visit(node.iter)
        self._extract_targets(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._extract_targets(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.current_scope.add(node.name)
        if node.type:
            self.visit(node.type)
        for stmt in node.body:
            self.visit(stmt)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            vname = node.id
            if vname in builtin_names:
                return
            if not self.current_scope.is_defined(vname):
                self.undefined.append((self.filename, node.lineno, vname))

    def visit_FormattedValue(self, node):
        self.visit(node.value)

print("Starting scan...")
for f in sorted(glob.glob("**/*.py", recursive=True)):
    if ".agents" in f:
        continue
    with open(f, "r", encoding="utf-8-sig", errors="ignore") as fp:
        try:
            tree = ast.parse(fp.read(), filename=f)
            finder = NameFinder(f)
            finder.visit(tree)
            if finder.undefined:
                print(f"=== {f} ===")
                for path, line, vname in finder.undefined:
                    print(f"  Line {line}: undefined variable '{vname}'")
        except Exception as e:
            print(f"Error parsing {f}: {e}")
print("Scan complete.")
