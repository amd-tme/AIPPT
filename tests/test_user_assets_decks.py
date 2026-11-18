"""The user's own icons and co-brand logo in generated decks (step 5d)."""
import io
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from aippt import icons, user_assets

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            b'<path d="M1 1H9V9Z" fill="#000000"/></svg>')


def _png(size=(40, 10), color="#00C2DE"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


# ── icon matching ───────────────────────────────────────────────────────

def test_user_icons_are_found_only_inside_the_context(tmp_path):
    entries = [{"name": "Partner Cloud", "tags": ["burst"], "path": "/x/a.svg"},
               {"name": "Partner Cloud", "tags": [], "path": "/x/b.svg"}]
    with icons.user_icons(entries) as mine:
        assert [i["id"] for i in mine] == ["my-partner-cloud", "my-partner-cloud-2"]
        assert icons.user_icon_paths() == {"my-partner-cloud": "/x/a.svg",
                                           "my-partner-cloud-2": "/x/b.svg"}
        assert icons.resolve("Partner Cloud") == "my-partner-cloud"
        assert icons.resolve("my-partner-cloud-2") == "my-partner-cloud-2"
        assert "my-partner-cloud" in icons.search("burst capacity")
        assert icons.best_match("capacity", heading="Burst") == "my-partner-cloud"
        assert "my-partner-cloud — your icon: Partner Cloud (burst)" in icons.catalogue_lines(
            ["my-partner-cloud"])
    assert icons.resolve("Partner Cloud") is None
    assert icons.user_icon_paths() == {}
    assert "my-partner-cloud" not in icons.search("burst capacity")


def test_brand_picks_are_unchanged_without_user_icons():
    before = (icons.search("secure data protection"), icons.best_match("faster results", heading="Speed"))
    with icons.user_icons([{"name": "Unrelated", "tags": [], "path": "/x.svg"}]):
        during = (icons.search("secure data protection"), icons.best_match("faster results", heading="Speed"))
    assert before == during


def test_user_icon_wins_a_tie_with_the_bank():
    scored = [(5, "gpu"), (5, "my-gpu"), (6, "cpu"), (2, "my-x")]
    assert sorted(scored, key=icons._rank) == [(6, "cpu"), (5, "my-gpu"), (5, "gpu"), (2, "my-x")]


def test_image_size(tmp_path):
    svg = tmp_path / "a.svg"
    svg.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 100"/>')
    assert user_assets.image_size(str(svg)) == (300.0, 100.0)
    svg.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg" width="40px" height="20"/>')
    assert user_assets.image_size(str(svg)) == (40.0, 20.0)
    png = tmp_path / "a.png"
    png.write_bytes(_png((40, 10)))
    assert user_assets.image_size(str(png)) == (40, 10)


# ── route ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path):
    from aippt.web.app import create_app
    app = create_app(db_path=str(tmp_path / "slides.db"), uploads_dir=str(tmp_path / "uploads"),
                     images_dir=str(tmp_path / "images"), view_only=False)
    return TestClient(app)


def _create(client, ntid, cobrand):
    headers = {"Authorization": "Bearer tok"}
    if ntid:
        headers["X-AIPPT-NTID"] = ntid
    return client.post("/api/decks/create", headers=headers, data={
        "outline_text": "# A\n", "engine": "pptxgenjs-direct", "cobrand_logo": cobrand})


def test_cobrand_needs_an_ntid(client):
    resp = _create(client, None, "0123456789")
    assert resp.status_code == 400 and "NTID" in resp.json()["error"]


def test_cobrand_must_be_one_of_your_logos(client):
    icon = client.post("/api/assets", headers={"X-AIPPT-NTID": "alice"}, data={"kind": "icon"},
                       files={"file": ("cloud.svg", ICON_SVG)}).json()["asset"]
    logo = client.post("/api/assets", headers={"X-AIPPT-NTID": "alice"}, data={"kind": "logo"},
                       files={"file": ("acme.png", _png())}).json()["asset"]
    for ntid, asset_id in (("alice", icon["id"]), ("alice", "0123456789"), ("bob", logo["id"])):
        resp = _create(client, ntid, asset_id)
        assert resp.status_code == 400, (ntid, asset_id)
        assert "Co-brand logo not found" in resp.json()["error"]


# ── render ──────────────────────────────────────────────────────────────

OUTLINE = """# Better Together
Partner briefing

# Why us
- **Partner Cloud** — burst capacity on demand
- **Security** — protect data at every layer
- **Speed** — faster time to results

# Thank you
"""


def _render(tmp_path, cobrand):
    from aippt.pptxgenjs_direct import generate_script
    from aippt.preview import Renderer
    from aippt.web.routes import _stage_render_workspace

    if not shutil.which("node") or Renderer(project_root=str(PROJECT_ROOT))._find_node_modules() is None:
        pytest.skip("node / node_modules not available")
    # Same layout as the app: uploads/ inside the project root (gitignored)
    uploads = PROJECT_ROOT / "uploads"
    job_id = f"pytest-cobrand-{tmp_path.name}-{int(cobrand)}"
    folder = uploads / "assets" / "users" / job_id
    try:
        user_assets.add_asset(str(folder), "icon", "cloud.svg", ICON_SVG, name="Partner Cloud")
        logo = user_assets.add_asset(str(folder), "logo", "acme.png", _png())
        script, out = _stage_render_workspace(str(uploads), job_id, "deck", str(PROJECT_ROOT))
        with icons.user_icons(user_assets.icon_entries(str(folder))):
            user_assets.write_sidecar(str(Path(script).parent), icons.user_icon_paths(),
                                      user_assets.cobrand_logo(str(folder), logo["id"]) if cobrand else None)
            # A corp theme, where the no-LLM engine picks the icon grid itself
            text = generate_script(outline_text=OUTLINE, output_script_path=script, theme="corp_black")
        result = Renderer(project_root=str(PROJECT_ROOT)).render(script, out)
        assert result.success, result.stderr_tail
        with zipfile.ZipFile(result.pptx_path) as z:
            media = {n: z.read(n) for n in z.namelist() if n.startswith("ppt/media/")}
            rels = {n: z.read(n).decode() for n in z.namelist()
                    if re.match(r"ppt/slides/_rels/slide\d+\.xml\.rels$", n)}
    finally:
        shutil.rmtree(uploads / job_id, ignore_errors=True)
        shutil.rmtree(folder, ignore_errors=True)
    return text, media, rels


def _slide_media(media, rels, n):
    names = re.findall(r'Target="\.\./media/([^"]+)"', rels[f"ppt/slides/_rels/slide{n}.xml.rels"])
    return [media[f"ppt/media/{name}"] for name in names]


def test_user_icon_and_cobrand_render(tmp_path):
    text, media, rels = _render(tmp_path, cobrand=True)
    assert "my-partner-cloud" in text and "addIconFeatureGrid" in text
    # The user's SVG went in, recoloured off black
    svgs = [d.decode() for d in media.values() if d.lstrip().startswith(b"<")]
    mine = [s for s in svgs if 'd="M1 1H9V9Z"' in s]
    assert mine and all("#000000" not in s for s in mine)
    # Partner logo on the title slide and the closing slide only
    last = len(rels)
    assert _png() in _slide_media(media, rels, 1)
    assert _png() in _slide_media(media, rels, last)
    for n in range(2, last):
        assert _png() not in _slide_media(media, rels, n)


def test_no_cobrand_unless_asked(tmp_path):
    _, media, rels = _render(tmp_path, cobrand=False)
    assert all(_png() not in _slide_media(media, rels, n) for n in range(1, len(rels) + 1))
