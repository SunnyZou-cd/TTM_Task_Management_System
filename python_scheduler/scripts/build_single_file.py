"""Historical advanced-version builder, isolated from the course entry point."""

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / "python_scheduler" / "src" / "academic_scheduler"
ORDER = ("models", "availability", "strategies", "metrics", "engine", "validation",
         "workspace", "storage", "terminal", "cli", "demo_cases", "demo", "gui", "application")
HEADER = '"""\nDemo 1: graphical Python academic scheduling system.\nAuthor: Sunny Zou\nDate: 2026-11-13\n"""\n\nfrom __future__ import annotations\n\n'


def _defined_names(tree, module):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names = [node.target.id]
        else:
            names = []
        for name in names:
            if name.startswith("_") or (name == "main" and module != "application"):
                result[name] = f"_{module}_{name.lstrip('_')}"
    return result


class _Flatten(ast.NodeTransformer):
    """Resolve project imports and namespace private module implementation names."""

    def __init__(self, module, trees, renames):
        self.names = dict(renames[module])
        self.module_aliases = {}
        self.definitions = set(renames[module])
        self.all_renames = renames
        for node in ast.walk(trees[module]):
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            for alias in node.names:
                local = alias.asname or alias.name
                if node.module is None:
                    self.module_aliases[local] = alias.name
                else:
                    self.names[local] = renames[node.module].get(alias.name, alias.name)

    def visit_ImportFrom(self, node):
        if node.level or node.module == "__future__":
            return None
        return node

    def visit_Name(self, node):
        if node.id in self.names:
            node.id = self.names[node.id]
        return node

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id in self.module_aliases:
            module = self.module_aliases[node.value.id]
            name = self.all_renames[module].get(node.attr, node.attr)
            return ast.copy_location(ast.Name(id=name, ctx=node.ctx), node)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name in self.definitions:
            node.name = self.names[node.name]
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        if node.name in self.definitions:
            node.name = self.names[node.name]
        return self.generic_visit(node)


def build():
    trees = {name: ast.parse((MODULES / f"{name}.py").read_text(encoding="utf-8")) for name in ORDER}
    renames = {name: _defined_names(tree, name) for name, tree in trees.items()}
    sections = [HEADER]
    for name in ORDER:
        transformer = _Flatten(name, trees, renames)
        flattened = transformer.visit(trees[name])
        ast.fix_missing_locations(flattened)
        sections.append(f"\n# ==================== {name}.py ====================\n\n")
        if name == "gui":
            # Keep Tk imports, GUI classes and helpers in a function closure.
            # The standalone CLI can then run even when tkinter is unavailable.
            loader = ast.FunctionDef(
                name="_load_gui_runner",
                args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
                body=[*flattened.body, ast.Return(value=ast.Name(id="run_gui", ctx=ast.Load()))],
                decorator_list=[],
            )
            ast.fix_missing_locations(loader)
            sections.append(ast.unparse(loader) + "\n\n")
            sections.append("def run_gui(*args, **kwargs):\n    return _load_gui_runner()(*args, **kwargs)\n")
        else:
            sections.append(ast.unparse(flattened) + "\n")
    sections.append('\nif __name__ == "__main__":\n    raise SystemExit(main())\n')
    result = "".join(sections)
    ast.parse(result, feature_version=(3, 11))
    compile(result, "demo1.py", "exec")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "advanced-demo" / "demo1.py")
    args = parser.parse_args()
    target = args.output
    expected = build()
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            parser.exit(1, "demo1.py differs from modular sources; regenerate it\n")
        print("demo1.py is synchronized")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8", newline="\n")
        print(f"Generated {target}")


if __name__ == "__main__":
    main()
