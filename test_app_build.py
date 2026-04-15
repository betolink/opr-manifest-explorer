import sys

sys.path.insert(0, ".")

from explorer import create_app
import panel as pn

pn.extension()

print("Building app...")
app = create_app()
print("App built successfully")
print(f"App type: {type(app)}")
print(f"File selector: {app[1][0][1]}")  # navigate structure maybe
