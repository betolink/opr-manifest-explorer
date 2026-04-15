"""Test FileInput widget behavior"""

import panel as pn
import tempfile
from pathlib import Path

pn.extension()

# Create widgets
fi = pn.widgets.FileInput(accept=".h5,.mat,.nc", name="Upload File")
btn = pn.widgets.Button(name="Test", button_type="primary", disabled=True)
output = pn.pane.Markdown(f"Value: {fi.value}\nFilename: {fi.filename}")


def check_state(*events):
    has_data = fi.value is not None or fi.filename
    btn.disabled = not has_data
    output.object = f"Value: {fi.value is not None}\nFilename: {fi.filename}\nButton enabled: {not btn.disabled}"


fi.param.watch(check_state, ["value", "filename"])

# Initialize
check_state()

app = pn.Column(
    pn.pane.Markdown("# FileInput Test"),
    fi,
    btn,
    output,
    pn.pane.Markdown("Click 'Upload File' and select a file to test."),
)

app.servable()
