import panel as pn
from pathlib import Path

pn.extension()

# Create FileSelector
fs = pn.widgets.FileSelector(directory="./data", only_files=True)
print(f"Directory: {fs.directory}")
print(f"Absolute directory: {Path(fs.directory).absolute()}")
print(f"Initial value: {fs.value}")

# Simulate selecting a file (value is list of relative paths)
# Let's see what happens when we set value to a filename
fs.value = ["ATL10-01_20181014000347_02350101_007_02.h5"]
print(f"After setting value: {fs.value}")
print(f"Type of value: {type(fs.value)}")
print(f"First element: {fs.value[0]}")
print(f"Is absolute? {Path(fs.value[0]).is_absolute()}")

# Compute absolute path
abs_path = (Path(fs.directory) / fs.value[0]).absolute()
print(f"Absolute path: {abs_path}")

# Now test with a subdirectory maybe
fs2 = pn.widgets.FileSelector(directory=".", only_files=False)
print(f"\nFS2 directory: {fs2.directory}")
# Select a directory
fs2.value = ["data"]
print(f"FS2 value: {fs2.value}")
