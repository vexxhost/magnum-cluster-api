# SPDX-FileCopyrightText: © 2025 VEXXHOST, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Go text/template implementation for Python.

This module provides a Python implementation of Go's text/template functionality,
including conditional logic, variable substitution, and function calls.  The
primary purpose of it is for testing `enabledIf` conditions directly in the
unit tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, Union

import semver
from lark import Lark, Token, Transformer

TemplateFunction = Callable[["Evaluator", List["ASTNode"]], Any]
FunctionInfo = Dict[str, Union[TemplateFunction, int]]


class Evaluator(Protocol):
    """Protocol for evaluator objects passed to template functions."""

    def evaluate(self, node: "ASTNode") -> Any:
        """Evaluate an AST node and return its value."""

    def is_truthy(self, value: Any) -> bool:
        """Check if a value is truthy in Go template sense."""


# AST Node types
@dataclass
class ASTNode:
    """Base class for AST nodes."""


@dataclass
class TextNode(ASTNode):
    """Represents plain text in the template."""

    text: str


@dataclass
class VariableNode(ASTNode):
    """Represents a variable reference like .foo or .foo.bar"""

    path: str


@dataclass
class LiteralNode(ASTNode):
    """Represents a literal value (string, number, boolean)."""

    value: Union[str, int, float, bool]


@dataclass
class FunctionCallNode(ASTNode):
    """Represents a function call like 'eq x y' or 'and a b'."""

    function: str
    args: List[ASTNode]


@dataclass
class IfNode(ASTNode):
    """Represents an if block."""

    condition: ASTNode
    body: List[ASTNode]


@dataclass
class TemplateNode(ASTNode):
    """Root node containing all template elements."""

    children: List[ASTNode]


# Function registry system
class FunctionRegistry:
    """Registry for template functions."""

    _functions: Dict[str, FunctionInfo] = {}

    @classmethod
    def register(
        cls, name: str, arity: int = -1
    ) -> Callable[[TemplateFunction], TemplateFunction]:
        """
        Decorator to register a template function.

        Args:
            name: The name of the function in templates
            arity: Number of arguments (-1 for variable)
        """

        def decorator(func: TemplateFunction) -> TemplateFunction:
            # Store the function with its metadata
            cls._functions[name] = {"function": func, "arity": arity}
            return func

        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[FunctionInfo]:
        """Get a function by name."""
        return cls._functions.get(name)

    @classmethod
    def get_names(cls) -> List[str]:
        """Get all registered function names."""
        return list(cls._functions)

    @classmethod
    def get_grammar_names(cls) -> str:
        """Get function names formatted for Lark grammar."""
        return " | ".join(f'"{name}"' for name in cls._functions)


# Register built-in functions
@FunctionRegistry.register("eq", arity=2)
def eq_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test equality of two values."""
    values = [evaluator.evaluate(arg) for arg in args]
    return values[0] == values[1] if len(values) == 2 else False


@FunctionRegistry.register("ne", arity=2)
def ne_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test inequality of two values."""
    values = [evaluator.evaluate(arg) for arg in args]
    return values[0] != values[1] if len(values) == 2 else False


@FunctionRegistry.register("gt", arity=2)
def gt_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test if first value is greater than second."""
    values = [evaluator.evaluate(arg) for arg in args]
    try:
        return float(values[0]) > float(values[1]) if len(values) == 2 else False
    except (TypeError, ValueError):
        return False


@FunctionRegistry.register("ge", arity=2)
def ge_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test if first value is greater than or equal to second."""
    values = [evaluator.evaluate(arg) for arg in args]
    try:
        return float(values[0]) >= float(values[1]) if len(values) == 2 else False
    except (TypeError, ValueError):
        return False


@FunctionRegistry.register("lt", arity=2)
def lt_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test if first value is less than second."""
    values = [evaluator.evaluate(arg) for arg in args]
    try:
        return float(values[0]) < float(values[1]) if len(values) == 2 else False
    except (TypeError, ValueError):
        return False


@FunctionRegistry.register("le", arity=2)
def le_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Test if first value is less than or equal to second."""
    values = [evaluator.evaluate(arg) for arg in args]
    try:
        return float(values[0]) <= float(values[1]) if len(values) == 2 else False
    except (TypeError, ValueError):
        return False


@FunctionRegistry.register("and", arity=-1)
def and_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Logical AND of all arguments."""
    values = [evaluator.evaluate(arg) for arg in args]
    return all(evaluator.is_truthy(v) for v in values)


@FunctionRegistry.register("or", arity=-1)
def or_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Logical OR of all arguments."""
    values = [evaluator.evaluate(arg) for arg in args]
    return any(evaluator.is_truthy(v) for v in values)


@FunctionRegistry.register("not", arity=1)
def not_function(evaluator: Evaluator, args: List[ASTNode]) -> bool:
    """Logical NOT of argument."""
    values = [evaluator.evaluate(arg) for arg in args]
    return not evaluator.is_truthy(values[0]) if values else False


@FunctionRegistry.register("index", arity=2)
def index_function(evaluator: Evaluator, args: List[ASTNode]) -> Any:
    """Get element from list/dict by index/key."""
    values = [evaluator.evaluate(arg) for arg in args]
    if len(values) != 2:
        return None

    container = values[0]
    key = values[1]

    if container is None:
        return None

    # Handle list indexing
    if isinstance(container, (list, tuple)):
        try:
            idx = int(key)
            if 0 <= idx < len(container):
                return container[idx]
        except (ValueError, TypeError, IndexError):
            pass
        return None

    # Handle dict access
    if isinstance(container, dict):
        return container.get(str(key))

    return None


@FunctionRegistry.register("semverCompare", arity=2)
def semver_compare_function(evaluator: Evaluator, args: List[ASTNode]) -> str:
    """Compare semantic versions using the semver package."""
    values = [evaluator.evaluate(arg) for arg in args]
    if len(values) != 2:
        return "false"

    constraint_str = str(values[0])
    version_str = str(values[1])

    # Parse the constraint (e.g., "<1.33.0", ">=1.20.0")
    match = re.match(r"([<>=]+)\s*(.+)", constraint_str.strip())
    if not match:
        return "false"

    op_str, constraint_version = match.groups()

    # Clean version strings (remove 'v' prefix if present)
    if version_str.startswith("v"):
        version_str = version_str[1:]
    if constraint_version.startswith("v"):
        constraint_version = constraint_version[1:]

    try:
        # Parse versions using semver
        version = semver.Version.parse(version_str)
        constraint = semver.Version.parse(constraint_version)

        # Apply the operator
        if op_str == "<":
            return "true" if version < constraint else "false"
        if op_str == "<=":
            return "true" if version <= constraint else "false"
        if op_str == ">":
            return "true" if version > constraint else "false"
        if op_str == ">=":
            return "true" if version >= constraint else "false"
        if op_str in ("==", "="):
            return "true" if version == constraint else "false"
        if op_str == "!=":
            return "true" if version != constraint else "false"
        return "false"

    except (ValueError, AttributeError, TypeError):  # semver raises various exceptions
        # If parsing fails, return false
        return "false"


def get_grammar() -> str:
    """Generate the grammar with registered functions."""
    func_names = FunctionRegistry.get_grammar_names()

    return f"""
    // Expression grammar
    ?expr: func_call
         | atom

    func_call: FUNC_NAME expr+

    ?atom: "(" expr ")"
         | variable
         | string
         | number
         | boolean

    variable: /\\.[a-zA-Z_][a-zA-Z0-9_.]*/

    string: ESCAPED_STRING

    number: SIGNED_NUMBER

    boolean: "true" -> true
           | "false" -> false

    FUNC_NAME: {func_names}

    %import common.ESCAPED_STRING
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS
    """


class GoTemplateTransformer(Transformer[Token, ASTNode]):
    """Transform Lark parse tree into our AST nodes."""

    def func_call(self, items: List[Any]) -> FunctionCallNode:
        """Transform a function call."""
        func_name = str(items[0])
        args = list(items[1:]) if len(items) > 1 else []
        return FunctionCallNode(func_name, args)

    def variable(self, items: List[Token]) -> VariableNode:
        """Transform a variable reference."""
        path = str(items[0])
        # Remove leading dot if present
        return VariableNode(path[1:] if path.startswith(".") else path)

    def string(self, items: List[Token]) -> LiteralNode:
        """Transform a string literal."""
        # Remove quotes
        string_value = str(items[0])[1:-1]
        return LiteralNode(string_value)

    def number(self, items: List[Token]) -> LiteralNode:
        """Transform a number literal."""
        return LiteralNode(float(items[0]))

    def true(self, _: List[Any]) -> LiteralNode:
        """Transform a true literal."""
        return LiteralNode(True)

    def false(self, _: List[Any]) -> LiteralNode:
        """Transform a false literal."""
        return LiteralNode(False)


class GoTemplateLarkParser:
    """Parser using Lark."""

    def __init__(self) -> None:
        grammar = get_grammar()
        self.parser = Lark(grammar, start="expr")
        self.transformer = GoTemplateTransformer()

    def parse_expression(self, expr_str: str) -> ASTNode:
        """Parse a single expression."""
        tree = self.parser.parse(expr_str)
        transformed = self.transformer.transform(tree)
        assert isinstance(transformed, ASTNode)
        return transformed

    def parse_template(self, tmpl_str: str) -> TemplateNode:
        """Parse a complete template string."""
        children: List[ASTNode] = []
        pos = 0

        while pos < len(tmpl_str):
            # Find next template expression
            match = re.search(r"\{\{(.+?)\}\}", tmpl_str[pos:], re.DOTALL)

            if not match:
                # No more expressions, add remaining text
                if pos < len(tmpl_str):
                    text = tmpl_str[pos:]
                    if text:
                        children.append(TextNode(text))
                break

            # Add text before this expression
            if match.start() > 0:
                text = tmpl_str[pos : pos + match.start()]
                if text:
                    children.append(TextNode(text))

            expr = match.group(1).strip()
            expr_end = pos + match.end()

            # Handle if statements
            if expr.startswith("if "):
                # Find matching end tag, accounting for nested ifs
                depth = 1
                search_pos = expr_end
                end_match: Optional[re.Match[str]] = None

                while depth > 0 and search_pos < len(tmpl_str):
                    next_if = re.search(r"\{\{\s*if\s+", tmpl_str[search_pos:])
                    next_end = re.search(
                        r"\{\{\s*end\s*\}\}", tmpl_str[search_pos:]
                    )

                    if next_end:
                        if next_if and next_if.start() < next_end.start():
                            # Found another if before the next end
                            depth += 1
                            search_pos += next_if.end()
                        else:
                            # Found an end
                            depth -= 1
                            if depth == 0:
                                end_match = next_end
                                end_pos = search_pos + next_end.start()
                            else:
                                search_pos += next_end.end()
                    else:
                        break

                if end_match:
                    # Get body between if and end
                    body_str = tmpl_str[expr_end:end_pos]
                    body = self.parse_template(body_str)

                    # Parse condition
                    condition_str = expr[3:].strip()
                    condition = self.parse_expression(condition_str)

                    children.append(IfNode(condition, body.children))
                    pos = search_pos + end_match.end()
                    continue

            elif expr == "end":
                # This shouldn't happen in a well-formed template at top level
                # Skip it
                pos = expr_end
                continue

            else:
                # Variable substitution or expression
                node = self.parse_expression(expr)
                children.append(node)

            pos = expr_end

        return TemplateNode(children)


class EvaluatorImpl:
    """Evaluate Go template AST with data."""

    def __init__(self, context_data: Dict[str, Any]) -> None:
        self.data = context_data

    def evaluate(self, node: ASTNode) -> Any:
        """Evaluate an AST node."""
        if isinstance(node, TextNode):
            return node.text

        if isinstance(node, TemplateNode):
            results: List[str] = []
            for child in node.children:
                value = self.evaluate(child)
                if value is not None:
                    results.append(str(value))
            return "".join(results)

        if isinstance(node, IfNode):
            condition_result = self.evaluate(node.condition)
            if self.is_truthy(condition_result):
                body_results: List[str] = []
                for child in node.body:
                    value = self.evaluate(child)
                    if value is not None:
                        body_results.append(str(value))
                return "".join(body_results)
            return ""

        if isinstance(node, VariableNode):
            return self._get_variable(node.path)

        if isinstance(node, LiteralNode):
            return node.value

        if isinstance(node, FunctionCallNode):
            return self._evaluate_function(node)

        return None

    def _get_variable(self, path: str) -> Any:
        """Get a variable value from the data."""
        if not path:
            return self.data

        parts = path.split(".")
        current: Any = self.data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None

        return current

    def is_truthy(self, value: Any) -> bool:
        """Check if a value is truthy in Go template sense."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value != ""
        if isinstance(value, (list, dict, tuple)):
            return len(value) > 0
        return bool(value)

    def _evaluate_function(self, node: FunctionCallNode) -> Any:
        """Evaluate a function call."""
        func_name = node.function

        # Look up the function in the registry
        func_info = FunctionRegistry.get(func_name)
        if func_info:
            # Call the registered function
            # Pass the raw args so the function can evaluate them as needed
            func = func_info.get("function")
            if callable(func):
                return func(self, node.args)

        # Unknown function - return None
        return None


class Template:
    """Go text/template using Lark."""

    def __init__(self, tmpl_str: str) -> None:
        self.parser = GoTemplateLarkParser()
        self.ast = self.parser.parse_template(tmpl_str)

    def render(self, context: Dict[str, Any]) -> str:
        """Render the template with data."""
        evaluator = EvaluatorImpl(context)
        rendered = evaluator.evaluate(self.ast)
        return str(rendered) if rendered is not None else ""


def render(tmpl_str: str, context: Dict[str, Any]) -> str:
    """Convenience function to render a Go template."""
    template = Template(tmpl_str)
    return template.render(context)


# Quick test
if __name__ == "__main__":
    # Test a few patterns
    tests: List[tuple[str, Dict[str, Any], str]] = [
        ('{{ if eq .status "active" }}running{{end}}', {"status": "active"}, "running"),
        ("{{ if and .a (not .b) }}yes{{end}}", {"a": True, "b": False}, "yes"),
        ("Hello {{ .name }}!", {"name": "World"}, "Hello World!"),
        ('{{ if ne .value "" }}has value{{end}}', {"value": "test"}, "has value"),
    ]

    for tmpl, ctx, expected in tests:
        output = render(tmpl, ctx)
        check_status = "✓" if output == expected else "✗"
        print(f"{check_status} {tmpl[:40]:40} => {output}")
