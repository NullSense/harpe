import json

from harpe import installhost


def test_chrome_manifest_has_extension_origin():
    m = installhost._chrome_manifest("/launch", [installhost.EXTENSION_ID, "other"])
    assert m["name"] == installhost.HOST_NAME
    assert m["path"] == "/launch"
    assert m["allowed_origins"] == [
        f"chrome-extension://{installhost.EXTENSION_ID}/", "chrome-extension://other/"]


def test_firefox_manifest_has_gecko_id():
    m = installhost._firefox_manifest("/launch", [installhost.GECKO_ID])
    assert m["allowed_extensions"] == [installhost.GECKO_ID]
    assert m["type"] == "stdio"


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(installhost, "_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(installhost, "_state_dir", lambda: tmp_path / "state")
    chrome = tmp_path / "chrome"
    ff = tmp_path / "ff"
    chrome.mkdir(); ff.mkdir()
    monkeypatch.setattr(installhost, "_browser_dirs",
                        lambda: ([chrome], [ff], "NMH", "nmh"))
    return chrome, ff


def test_write_launcher_runs_native_host(monkeypatch, tmp_path):
    monkeypatch.setattr(installhost, "_data_dir", lambda: tmp_path / "data")
    p = installhost.write_launcher()
    body = open(p).read()
    assert "--native-host" in body
    import os
    assert os.access(p, os.X_OK)


def test_install_writes_manifests_and_uninstall_removes(monkeypatch, tmp_path):
    if installhost.os.name == "nt":
        return  # registry path covered separately
    chrome, ff = _redirect(monkeypatch, tmp_path)
    written = installhost.install()
    cm = chrome / "NMH" / f"{installhost.HOST_NAME}.json"
    fm = ff / "nmh" / f"{installhost.HOST_NAME}.json"
    assert cm.exists() and fm.exists()
    assert json.loads(cm.read_text())["allowed_origins"][0].startswith("chrome-extension://")
    assert json.loads(fm.read_text())["allowed_extensions"] == [installhost.GECKO_ID]
    assert installhost.is_installed()
    assert set(written) >= {str(cm), str(fm)}

    removed = installhost.uninstall()
    assert not cm.exists() and not fm.exists()
    assert not installhost.is_installed()
    assert set(removed) == {str(cm), str(fm)}


def test_install_skips_absent_browsers_unless_all(monkeypatch, tmp_path):
    if installhost.os.name == "nt":
        return
    monkeypatch.setattr(installhost, "_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(installhost, "_state_dir", lambda: tmp_path / "state")
    absent = tmp_path / "nope"
    monkeypatch.setattr(installhost, "_browser_dirs",
                        lambda: ([absent], [], "NMH", "nmh"))
    assert installhost.install() == []                 # not detected → skipped
    assert installhost.install(all_browsers=True)      # forced → written
