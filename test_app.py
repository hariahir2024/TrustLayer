import ast
import sys
import logging
logging.disable(logging.CRITICAL)  # suppress startup logs

# 1. Syntax check
with open("app.py", "r", encoding="utf-8") as f:
    source = f.read()
try:
    ast.parse(source)
    print("Syntax check    : PASS")
except SyntaxError as e:
    print(f"Syntax error    : {e}")
    sys.exit(1)

# 2. Import check
import app
print("Import check    : PASS")

# 3. Route inventory
routes = [r for r in app.app.routes if hasattr(r, "path")]
print(f"Routes total    : {len(routes)}")
for r in routes:
    methods = getattr(r, "methods", None)
    method  = list(methods)[0] if methods else "WS/MOUNT"
    print(f"  {method:<8} {r.path}")

print("\napp.py ready.")
