"""Safe calculator used for math answers."""
import ast
import math
import operator

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
       ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
FUNCS = {n: getattr(math, n) for n in
         ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "radians", "degrees")}


def calculate(expression):
    """Safe calculator: walks the syntax tree, never uses eval."""
    def ev(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
                raise ValueError("power too large")
            return OPS[type(node.op)](a, b)
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in ("pi", "e"):
            return getattr(math, node.id)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in FUNCS and not node.keywords):
            return FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError("unsupported expression")

    return str(ev(ast.parse(expression.replace("^", "**"), mode="eval").body))
