"""
Reading the Mermaid diagrams in docs/, so tests can check them against the code and the running system.

Conventions the diagrams follow (docs/posix/README.md, "How the diagrams are checked"):
- Flowcharts: a plain solid arrow ``A --> B`` means "module A imports module B" in a module diagram.
  Other relationships use a labelled or dotted arrow and are not import claims.
- Sequence diagrams: a solid arrow ``A->>B: METHOD /path`` or ``A->>Helper: op`` is a claim the
  tests check against what the components log, in order. Dashed replies (``-->>``) and notes are
  explanation only.
- State diagrams: ``S1 --> S2`` is a transition the tests must observe, and no others may occur.
Only the diagram block with a ``%% check: <name>`` comment as its first line is checked, so a page
can hold explanatory diagrams too.
"""
import re
from dataclasses import dataclass
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"


def block(markdown_file: str, name: str) -> str:
    """The Mermaid block in ``docs/<markdown_file>`` whose first line is ``%% check: <name>``."""
    text = (DOCS / markdown_file).read_text()
    for body in re.findall(r"```mermaid\n(.*?)```", text, flags=re.S):
        lines = body.strip().splitlines()
        if lines and lines[0].strip() == f"%% check: {name}":
            return body
    raise LookupError(f"no mermaid block '%% check: {name}' in docs/{markdown_file}")


def _clean(line: str) -> str:
    return line.split("%%", 1)[0].strip()


def flowchart_imports(body: str) -> set[tuple[str, str]]:
    """Plain solid, unlabelled arrows ``A --> B`` (node ids), the diagram's import claims."""
    edges = set()
    for line in map(_clean, body.splitlines()):
        m = re.fullmatch(r"(\w+)(?:\[[^\]]*\]|\([^)]*\))?\s*-->\s*(\w+)(?:\[[^\]]*\]|\([^)]*\))?", line)
        if m:
            edges.add((m.group(1), m.group(2)))
    return edges


def flowchart_nodes(body: str) -> dict[str, str]:
    """Node id -> label, for nodes declared as ``id[label]`` or ``id(label)``."""
    nodes = {}
    for m in re.finditer(r"\b(\w+)(?:\[\"?([^\]\"]*)\"?\]|\(\"?([^)\"]*)\"?\))", body):
        nodes.setdefault(m.group(1), (m.group(2) or m.group(3) or "").strip())
    return nodes


@dataclass(frozen=True)
class Message:
    sender: str
    receiver: str
    text: str


def sequence_messages(body: str) -> list[Message]:
    """Solid arrows ``A->>B: text`` in order (the checked claims)."""
    messages = []
    for line in map(_clean, body.splitlines()):
        m = re.fullmatch(r"(\w+)\s*->>\s*\+?(\w+)\s*:\s*(.+)", line)
        if m:
            messages.append(Message(m.group(1), m.group(2), m.group(3).strip()))
    return messages


def state_transitions(body: str) -> set[tuple[str, str]]:
    """``S1 --> S2`` transitions, with ``[*]`` kept as is."""
    transitions = set()
    for line in map(_clean, body.splitlines()):
        m = re.fullmatch(r"(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)(?:\s*:.*)?", line)
        if m:
            transitions.add((m.group(1), m.group(2)))
    return transitions


# --- the code side ---

def module_path(component_root: Path, label: str) -> Path:
    """A module diagram's node label starts with the module's path relative to its component."""
    rel = label.split("<br/>")[0].strip()
    for candidate in (component_root / f"{rel}.py", component_root / rel / "__init__.py"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"diagram names {rel!r}, which isn't a module under {component_root}")


def _dotted(component_root: Path, path: Path) -> str:
    rel = path.relative_to(component_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def import_edges(component_root: Path, nodes: dict[str, str]) -> set[tuple[str, str]]:
    """Imports among the diagram's nodes, read from the source (absolute and relative imports)."""
    import ast

    paths = {node: module_path(component_root, label) for node, label in nodes.items()}
    dotted = {node: _dotted(component_root, p) for node, p in paths.items()}
    by_name = {name: node for node, name in dotted.items()}
    edges = set()
    for node, path in paths.items():
        package = dotted[node] if path.name == "__init__.py" else dotted[node].rpartition(".")[0]
        for stmt in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(stmt, ast.Import):
                names = [a.name for a in stmt.names]
            elif isinstance(stmt, ast.ImportFrom):
                base = stmt.module or ""
                if stmt.level:
                    anchor = package.split(".") if package else []
                    anchor = anchor[: len(anchor) - (stmt.level - 1)] if stmt.level > 1 else anchor
                    base = ".".join([*anchor, base] if base else anchor)
                names = [base] + [f"{base}.{a.name}" for a in stmt.names]
            for name in names:
                target = by_name.get(name)
                if target and target != node:
                    edges.add((node, target))
    return edges


# --- sequences against what components log ---

def completion_order(messages: list[Message]) -> list[Message]:
    """
    The order calls finish in, which is the order components log them (each logs a request when it's
    done). A message sent by a participant that is itself handling a call is nested in that call and
    finishes first: ``A->>B``, ``B->>C`` finishes C's call, then B's.
    """
    stack: list[Message] = []
    done: list[Message] = []
    for m in messages:
        while stack and stack[-1].receiver != m.sender:
            done.append(stack.pop())
        stack.append(m)
    while stack:
        done.append(stack.pop())
    return done


def message_pattern(text: str) -> tuple[str, re.Pattern | None, int | None]:
    """
    Split a checked message into (verb, path pattern, status). ``GET /v1/files/{path} → 206 (Range…)``
    gives ("GET", /v1/files/.+, 206); an operation name such as ``open`` gives ("open", None, None).
    Text in parentheses is explanation.
    """
    text = re.sub(r"\s*\(.*\)\s*$", "", text).strip()
    status = None
    m = re.search(r"\s*→\s*(\d{3})$", text)
    if m:
        status, text = int(m.group(1)), text[: m.start()].strip()
    verb, _, path = text.partition(" ")
    if not path:
        return verb, None, status
    regex = re.escape(path).replace(r"\{id\}", r"\d+").replace(r"\{path\}", r".+")
    return verb, re.compile(regex), status
