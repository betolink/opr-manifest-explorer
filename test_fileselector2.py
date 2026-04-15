import panel as pn

pn.extension()

fs = pn.widgets.FileSelector(directory=".", only_files=True)
print(fs.__doc__)
print("\n---\n")
print(fs.param.__doc__)
print("\n---\n")
print(fs.param.directory.__doc__)
print(fs.param.value.__doc__)
