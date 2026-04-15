import panel as pn

pn.extension()

# Test FileSelector
fs = pn.widgets.FileSelector(directory=".", only_files=True)
print(f"FileSelector type: {type(fs)}")
print(f"FileSelector params: {list(fs.param)}")
print(f"value: {fs.value}")
print(f"directory: {fs.directory}")
print(f"only_files: {fs.only_files}")
print(f"FileSelector attributes: {[a for a in dir(fs) if not a.startswith('_')]}")
