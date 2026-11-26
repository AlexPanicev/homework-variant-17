"""Проверка применимых правил оформления из задания, страницы 5-7."""

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

from radon.complexity import cc_visit


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_LINES = 1000
MAX_PYTHON_WIDTH = 80
MAX_CODE_WIDTH = 120
MAX_FUNCTION_LINES = 40
MAX_ARGUMENTS = 7
MAX_COMPLEXITY = 10
TEST_CALLBACKS = {"setUp", "tearDown", "setUpClass", "tearDownClass",
                  "setUpModule", "tearDownModule"}
CODE_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml", ".lark", ".cfg"}
FORBIDDEN_SUFFIXES = {
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z", ".whl",
    ".pyc", ".pyo", ".log", ".pdf", ".png",
}
FORBIDDEN_PARTS = {
    "__pycache__", ".venv", ".pytest_cache", ".ruff_cache", ".idea",
    ".vscode", "build", "dist", "node_modules", ".DS_Store", ".coverage",
}


def repository_files() -> list[Path]:
    """Получить версионируемые и новые неигнорируемые файлы."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, text=True,
    )
    return [ROOT / name for name in sorted(set(output.splitlines()))]


def check_structure() -> list[str]:
    """Проверить обязательные документы, каталоги и скрипт запуска."""
    files = ("README.md", ".gitignore", "run.sh")
    errors = [f"С1-С5: отсутствует файл {name}" for name in files
              if not (ROOT / name).is_file()]
    errors.extend(f"С3-С4: отсутствует каталог {name}"
                  for name in ("src", "tests") if not (ROOT / name).is_dir())
    if not os.access(ROOT / "run.sh", os.X_OK):
        errors.append("С5: run.sh должен быть исполняемым")
    return errors


def check_commits() -> list[str]:
    """Проверить Conventional Commits и описание работы в каждом коммите."""
    result = subprocess.run(
        ["git", "log", "-z", "--format=%s%x00%b"], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    if result.returncode:
        return ["С6: отсутствует история коммитов"]
    pattern = r"^[a-z]+\([a-z0-9_-]+\)!?: .+"
    fields = result.stdout.removesuffix("\0").split("\0")
    errors = []
    for subject, description in zip(fields[::2], fields[1::2], strict=True):
        if not re.fullmatch(pattern, subject) or not description.strip():
            errors.append(f"С6: проверьте заголовок и описание {subject!r}")
    return errors


def check_file(path: Path) -> list[str]:
    """Отклонить артефакты, бинарные файлы и превышение длины строк."""
    name = path.relative_to(ROOT)
    if path.suffix in FORBIDDEN_SUFFIXES:
        return [f"Г1-Г5: запрещённый файл {name}"]
    if set(name.parts) & FORBIDDEN_PARTS:
        return [f"Г1-Г5: служебный файл {name}"]
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"Г2: двоичный файл {name}"]
    if "\0" in source:
        return [f"Г2: двоичный файл {name}"]
    errors = []
    lines = source.splitlines()
    if len(lines) > MAX_FILE_LINES:
        errors.append(f"Р1: {name}, {len(lines)} строк")
    if path.suffix not in CODE_SUFFIXES:
        return errors
    limit = MAX_PYTHON_WIDTH if path.suffix == ".py" else MAX_CODE_WIDTH
    for number, line in enumerate(lines, 1):
        if len(line) > limit:
            errors.append(f"Р2/Р6: {name}:{number}, {len(line)} символов")
    return errors


def check_function(node: ast.FunctionDef, name: Path) -> list[str]:
    """Проверить длину функции с декораторами и число аргументов."""
    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
    length = node.end_lineno - start + 1
    arguments = node.args
    count = len(arguments.posonlyargs + arguments.args + arguments.kwonlyargs)
    count += bool(arguments.vararg) + bool(arguments.kwarg)
    errors = []
    if length > MAX_FUNCTION_LINES:
        errors.append(f"Ф1: {name}:{start} {node.name}, {length} строк")
    if count > MAX_ARGUMENTS:
        errors.append(f"А1: {name}:{start} {node.name}, {count} аргументов")
    if not ast.get_docstring(node):
        errors.append(f"К1: {name}:{start} {node.name}, нет docstring")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", node.name):
        if name.parts[0] != "tests" or node.name not in TEST_CALLBACKS:
            errors.append(f"И1: {name}:{start} {node.name}, не snake_case")
    return errors


def check_comparisons(tree: ast.AST, name: Path) -> list[str]:
    """Отклонить числа в сравнениях, кроме обычных значений 0 и 1."""
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        for operand in [node.left] + node.comparators:
            if not isinstance(operand, ast.Constant):
                continue
            if type(operand.value) not in (int, float):
                continue
            if operand.value not in (0, 1):
                errors.append(f"М1: {name}:{node.lineno}, {operand.value}")
    return errors


def check_python(path: Path) -> list[str]:
    """Проверить функции, сравнения и сложность Python через Radon."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    name = path.relative_to(ROOT)
    errors = check_comparisons(tree, name)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            errors.extend(check_function(node, name))
    for block in cc_visit(source):
        for item in [block] + list(getattr(block, "methods", [])):
            if item.complexity > MAX_COMPLEXITY:
                errors.append(
                    f"Ц1: {name}:{item.lineno} {item.name}, "
                    f"сложность {item.complexity}"
                )
    return errors


def check_lint(paths: list[Path]) -> int:
    """Проверить ошибки Python, PEP8 имена и документацию через Ruff."""
    rules = "F,E501,N,PLR2004,D101,D102,D103,D107"
    return subprocess.call(
        [sys.executable, "-m", "ruff", "check", "--no-cache",
         "--line-length", str(MAX_PYTHON_WIDTH),
         "--select", rules, *map(str, paths)], cwd=ROOT,
    )


def main() -> int:
    """Завершиться с ошибкой при любом нарушении проверяемых правил."""
    paths = repository_files()
    errors = check_structure() + check_commits()
    python_paths = [path for path in paths if path.suffix == ".py"]
    for path in paths:
        errors.extend(check_file(path))
    for path in python_paths:
        errors.extend(check_python(path))
    lint_status = check_lint(python_paths)
    for error in errors:
        print(error)
    if errors or lint_status:
        return 1
    print("С1-С6, Г1-Г5, Р1/Р2/Р6, Ф1, А1, К1, Ц1, М1, И1: OK")
    print(f"Проверено {len(paths)} файлов, {len(python_paths)} Python-файлов")
    return 0


if __name__ == "__main__":
    sys.exit(main())
