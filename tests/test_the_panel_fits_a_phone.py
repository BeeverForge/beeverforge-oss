"""The served panel's controls and grid fit phone viewports, measured in a real browser.

At 375px the unwrapped header made the page 592px wide (Chromium 156, 2026-10-24).
Chrome clamps a headless window to 500px, so an iframe supplies the narrower viewport.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

WIDTHS = (320, 360, 375, 390, 414)
CONTROLS = ("live", "theme", "costs", "board", "who")

_PROBE = """<!doctype html><body style="margin:0">
<iframe id="f" src="panel.html" style="width:%(w)dpx;height:700px;border:0"></iframe>
<script>
document.getElementById("f").addEventListener("load", () => setTimeout(() => {
  const d = document.getElementById("f").contentDocument, out = {};
  for (const id of ["live", "who"]) { const e = d.getElementById(id); e.style.display = "";
    e.textContent = id === "who" ? "alexandra.carvalho@example-company.com.br · Sign out" : "live"; }
  const wrap = d.createElement("div"); wrap.className = "wrap";
  wrap.innerHTML = '<div class="grid"><div class="proj">p</div><div class="proj">q</div></div>';
  d.body.appendChild(wrap);
  out.viewport = d.documentElement.clientWidth;
  out.page = d.documentElement.scrollWidth;
  out.controls = Object.fromEntries(%(controls)s.map(id => {
    const r = d.getElementById(id).getBoundingClientRect(); return [id, [r.left, r.right]]; }));
  out.cards = [...wrap.querySelectorAll(".proj")].map(e => e.getBoundingClientRect().right);
  const p = document.createElement("pre"); p.id = "measured"; p.textContent = JSON.stringify(out);
  document.body.appendChild(p);
}, 500));
</script></body>"""


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    pytest.skip("no Chrome or Chromium on PATH: phone layout requires a real browser")


@pytest.fixture(scope="module")
def served_page() -> str:
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    page = TestClient(app).get("/")
    assert page.status_code == 200, page.text
    return page.text


@pytest.mark.parametrize("width", WIDTHS)
def test_every_header_control_and_the_project_grid_fit_a_phone(served_page, tmp_path, width):
    chrome = _chrome()
    (tmp_path / "panel.html").write_text(served_page, encoding="utf-8")
    (tmp_path / "probe.html").write_text(
        _PROBE % {"w": width, "controls": json.dumps(CONTROLS)}, encoding="utf-8")
    run = subprocess.run(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
         f"--user-data-dir={tmp_path / 'profile'}", "--allow-file-access-from-files",
         "--window-size=800,800", "--virtual-time-budget=5000",
         "--dump-dom", (tmp_path / "probe.html").as_uri()],
        capture_output=True, text=True, timeout=120)
    found = re.search(r'<pre id="measured">([^<]*)</pre>', run.stdout)
    assert found, f"the probe never measured the page (exit {run.returncode}): {run.stderr[-800:]}"
    measured = json.loads(found.group(1))
    assert measured["page"] <= measured["viewport"], (
        f"at {width}px the page is {measured['page']}px wide and requires horizontal scrolling")
    outside = {c: [round(x) for x in lr] for c, lr in measured["controls"].items()
               if lr[0] < 0 or lr[1] > measured["viewport"]}
    assert not outside, f"at {width}px these controls leave the viewport: {outside}"
    assert max(measured["cards"]) <= measured["viewport"], (
        f"at {width}px a project card ends past the {measured['viewport']}px viewport")
