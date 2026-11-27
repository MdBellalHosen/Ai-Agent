"""Exact math with sympy: solve, simplify, factor, expand, diff, integrate, limit, evaluate.

Runs as its own small process (see tools.math_solve) so a very hard problem
can be stopped after a few seconds instead of freezing Mira.
This file imports nothing from the agent package on purpose.
"""
import json
import re
import sys

TASKS = ("solve", "simplify", "factor", "expand", "diff", "integrate", "limit", "evaluate")
FUNCTIONS = ("sin", "cos", "tan", "cot", "sec", "csc", "asin", "acos", "atan", "acot",
             "sinh", "cosh", "tanh", "sqrt", "cbrt", "root", "log", "exp", "Abs",
             "factorial", "floor", "ceiling", "gcd", "lcm", "binomial", "Max", "Min",
             "pi", "E", "I", "oo", "Symbol", "Integer", "Float", "Rational", "Function")
ALLOWED = re.compile(r"^[A-Za-z0-9_+\-*/^().,=;! \t]*$")
MAX_POWER = 10000
MAX_FACTORIAL = 2000


def check(text, field="expression"):
    """Only plain math may reach sympy's parser."""
    text = str(text or "").strip().replace("**", "^").replace("×", "*").replace("÷", "/").replace("−", "-")
    if not text:
        raise ValueError(f"{field} is empty")
    if len(text) > 500 or not ALLOWED.match(text) or "__" in text or re.search(r"\.\s*[A-Za-z_]", text):
        raise ValueError(f"{field} has characters that are not plain math")
    for name in re.findall(r"[A-Za-z_]\w*", text):
        if len(name) > 12:
            raise ValueError(f"unknown name {name}")
    return text


def parse(text, field="expression"):
    import sympy
    from sympy.parsing.sympy_parser import (convert_xor, factorial_notation,
                                            implicit_multiplication_application, parse_expr,
                                            standard_transformations)
    names = {n: getattr(sympy, n) for n in FUNCTIONS}
    names.update(ln=sympy.log, abs=sympy.Abs, e=sympy.E, inf=sympy.oo, __builtins__={})
    steps = standard_transformations + (implicit_multiplication_application, convert_xor,
                                        factorial_notation)
    text = check(text, field)

    def one(part):
        raw = parse_expr(part, local_dict={}, global_dict=dict(names), transformations=steps,
                         evaluate=False)
        for node in sympy.preorder_traversal(raw):  # refuse numbers too big to compute
            if isinstance(node, sympy.Pow) and node.exp.is_number and not node.exp.free_symbols:
                if abs(sympy.N(node.exp)) > MAX_POWER and node.base.is_number and abs(sympy.N(node.base)) != 1:
                    raise ValueError("power too large")
            if isinstance(node, sympy.factorial) and node.args[0].is_number:
                if abs(sympy.N(node.args[0])) > MAX_FACTORIAL:
                    raise ValueError("factorial too large")
        return parse_expr(part, local_dict={}, global_dict=dict(names), transformations=steps)

    if "=" in text:
        left, _, right = text.partition("=")
        return sympy.Eq(one(left), one(right))
    return one(text)


def approx(value):
    import sympy
    try:
        if value.is_number and value.is_finite:
            number = sympy.N(value, 10)
            if number != value:
                return f" (≈ {number})"
    except Exception:
        pass
    return ""


def show(value):
    import sympy
    return str(value).replace("**", "^") + (approx(value) if isinstance(value, sympy.Basic) else "")


def pick_variable(expr, variable):
    import sympy
    if variable:
        return sympy.Symbol(check(variable, "variable"))
    free = sorted(expr.free_symbols, key=str)
    if not free:
        raise ValueError("no variable in the expression")
    for name in ("x", "y", "t", "n"):
        for s in free:
            if s.name == name:
                return s
    return free[0]


def run(request):
    import sympy
    task = str(request.get("task", "")).lower()
    if task not in TASKS:
        raise ValueError(f"task must be one of {', '.join(TASKS)}")
    text = request.get("expression", "")
    if task == "solve":
        parts = [p for p in check(text).split(";") if p.strip()]
        equations = [parse(p) for p in parts]
        exprs = [e.lhs - e.rhs if isinstance(e, sympy.Equality) else e for e in equations]
        if request.get("variable"):
            symbols = [sympy.Symbol(check(v, "variable")) for v in str(request["variable"]).split(",")]
        else:
            symbols = sorted(set().union(*(e.free_symbols for e in exprs)), key=str)
        if not symbols:
            raise ValueError("no variable to solve for")
        found = sympy.solve(exprs, symbols, dict=True)
        if not found:
            return "No solution found"
        return "; ".join(", ".join(f"{k} = {show(v)}" for k, v in sol.items()) for sol in found)

    expr = parse(text)
    if isinstance(expr, sympy.Equality):
        expr = expr.lhs - expr.rhs
    if task == "simplify":
        return show(sympy.simplify(expr))
    if task == "factor":
        return show(sympy.factor(expr))
    if task == "expand":
        return show(sympy.expand(expr))
    if task == "evaluate":
        return show(expr.doit())
    var = pick_variable(expr, request.get("variable"))
    if task == "diff":
        order = max(1, min(int(request.get("order") or 1), 10))
        return show(sympy.diff(expr, var, order))
    if task == "integrate":
        if request.get("lower") not in (None, "") and request.get("upper") not in (None, ""):
            lower, upper = parse(request["lower"], "lower"), parse(request["upper"], "upper")
            return show(sympy.integrate(expr, (var, lower, upper)))
        return show(sympy.integrate(expr, var)) + " + C"
    if task == "limit":
        point = parse(request.get("point", "0"), "point")
        direction = request.get("direction") if request.get("direction") in ("+", "-") else "+-"
        if point in (sympy.oo, -sympy.oo):
            direction = "+" if point == -sympy.oo else "-"
        return show(sympy.limit(expr, var, point, dir=direction))
    raise ValueError("unknown task")


def main():
    try:
        print(json.dumps({"result": run(json.loads(sys.stdin.read()))}, ensure_ascii=False))
    except Exception as err:
        print(json.dumps({"error": f"{type(err).__name__}: {err}"[:300]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
