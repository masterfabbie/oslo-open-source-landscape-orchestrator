"""The OSLO operations bundle: building, signing, checking (bundle.py), the shell scripts that
run on the hosts, the API (Administration → OSLO operations), the download of the hosts and
the update operation against the simulated landscape (bundles.py)."""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import httpx
import pytest

import test_mass
from conftest import make_user
from oslo import bundle
from oslo.bundle import BundleError
from test_mass import client

pytestmark = pytest.mark.anyio

app, api, transport = test_mass.app, test_mass.api, test_mass.transport

KEY, PUBLIC = bundle.generate_key()
OTHER_KEY, OTHER_PUBLIC = bundle.generate_key()


def make_bundle(version: str, key: bytes = KEY) -> bytes:
    payload = bundle.build_payload(version)
    return bundle.pack(payload, bundle.sign(payload, key))


def tar_with(members: list[tuple[str, bytes | None, bytes]]) -> bytes:
    """A tar.gz from (name, link target or None, data)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as archive:
        for name, link, data in members:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type, info.linkname = tarfile.SYMTYPE, link.decode()
            else:
                info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return raw.getvalue()


# --- the bundle file ----------------------------------------------------------------------


def test_build_sign_and_check():
    payload = bundle.build_payload("1.0.0")
    assert payload == bundle.build_payload("1.0.0")  # reproducible
    signature = bundle.sign(payload, KEY)
    data = bundle.pack(payload, signature)
    _, _, manifest = bundle.check_bundle(data, PUBLIC.decode())
    assert manifest.version == "1.0.0"
    assert {"oslo_version.conf", "oslo_update.conf", "oslo/oslo_update.sh"} <= set(manifest.files)
    assert "oslo/bundle_key.pem" not in manifest.files  # comes with the bootstrap package

    with pytest.raises(BundleError, match="signature"):
        bundle.check_bundle(data, OTHER_PUBLIC.decode())
    tampered = bundle.pack(bundle.build_payload("6.6.6"), signature)
    with pytest.raises(BundleError, match="signature"):
        bundle.check_bundle(tampered, PUBLIC.decode())
    for text, message in (("nonsense", "PEM"), (PUBLIC.decode() + "x", "")):
        if message:
            with pytest.raises(BundleError, match=message):
                bundle.public_key(text)
    with pytest.raises(BundleError, match="not an OSLO"):
        bundle.unpack(b"not a tar")
    with pytest.raises(BundleError, match="version"):
        bundle.build_payload("1.0 beta")


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ([("oslo/../../etc/passwd", None, b"x")], "Unexpected file"),
        ([("/etc/cron.d/x", None, b"x")], "Unexpected file"),
        ([("oslo/link", b"/etc/shadow", b"")], "link"),
        ([("other.conf", None, b"x")], "Unexpected file"),
        ([("oslo_version.conf", None, b"x")], "VERSION or SHA256SUMS"),
    ],
)
def test_bad_payloads_are_refused(members, message):
    with pytest.raises(BundleError, match=message):
        bundle.read_manifest(tar_with(members))


def test_bootstrap_package_and_output():
    payload = bundle.build_payload("1.0.0")
    data = bundle.bootstrap_archive(
        payload, bundle.sign(payload, KEY), PUBLIC.decode(), "https://oslo.example:8443/"
    )
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        names = set(archive.getnames())
        config = archive.extractfile("oslo-bootstrap/oslo.cfg").read().decode()
    assert {
        "oslo-bootstrap/install.sh",
        "oslo-bootstrap/payload.tar.gz",
        "oslo-bootstrap/payload.sig",
        "oslo-bootstrap/bundle_key.pem",
    } <= names
    assert "OSLO_URL=https://oslo.example:8443\n" in config
    assert bundle.parse_output(
        ["Info: OSLO operations: version: oslo_bundle version=1.0.0", "oslo_bundle integrity=ok"]
    ) == {"version": "1.0.0", "integrity": "ok"}


def test_command_line(tmp_path, capsys):
    bundle.main(["keygen", "--out", str(tmp_path)])
    private = tmp_path / "oslo-bundle-private.pem"
    assert private.stat().st_mode & 0o777 == 0o600
    out = tmp_path / "b.oslobundle"
    bundle.main(["build", "--version", "2.0.0", "--key", str(private), "--out", str(out)])
    bundle.main(["verify", str(out), "--key", str(tmp_path / "oslo-bundle-public.pem")])
    assert "Valid bundle 2.0.0" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="exists already"):
        bundle.main(["keygen", "--out", str(tmp_path)])


# --- the scripts on a host -------------------------------------------------------------------

TOOLS = ("sh", "openssl", "tar", "sha256sum", "mktemp")


@pytest.mark.skipif(not all(shutil.which(t) for t in TOOLS), reason="needs a Unix shell")
def test_scripts_install_check_and_update(tmp_path):
    ops = tmp_path / "operations.d"
    files = tmp_path / "files"
    files.mkdir()
    key = files / "bundle_key.pem"
    key.write_bytes(PUBLIC)

    def write(version: str, signing_key: bytes = KEY) -> tuple[Path, Path]:
        payload = bundle.build_payload(version)
        (files / "payload.tar.gz").write_bytes(payload)
        (files / "payload.sig").write_bytes(bundle.sign(payload, signing_key))
        return files / "payload.tar.gz", files / "payload.sig"

    def update(payload: Path, sig: Path, target: Path = ops) -> subprocess.CompletedProcess:
        script = bundle.source_dir() / "oslo" / "oslo_update.sh"
        command = ["sh", str(script), "--local", str(payload), str(sig), str(key), str(target)]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def version() -> str:
        script = ops / "oslo" / "oslo_version.sh"
        return subprocess.run(["sh", str(script)], capture_output=True, text=True).stdout

    first = update(*write("1.0.0"))
    assert first.returncode == 0, first.stdout + first.stderr
    assert "oslo_bundle installed=1.0.0" in first.stdout
    assert version() == "oslo_bundle version=1.0.0\noslo_bundle integrity=ok\n"
    assert os.access(ops / "oslo" / "oslo_update.sh", os.X_OK)

    # Files of the customer and the files of the bootstrap package stay; old OSLO files go.
    (ops / "customer.conf").write_text("Name: customer\n")
    (ops / "oslo" / "oslo.cfg").write_text("OSLO_URL=https://oslo.example\n")
    (ops / "oslo" / "retired.sh").write_text("old\n")
    (ops / "oslo" / "oslo_version.sh").write_text((ops / "oslo" / "oslo_version.sh").read_text())
    second = update(*write("1.1.0"))
    assert second.returncode == 0, second.stdout
    assert (ops / "customer.conf").exists() and (ops / "oslo" / "oslo.cfg").exists()
    assert not (ops / "oslo" / "retired.sh").exists()
    assert "version=1.1.0" in version() and "integrity=ok" in version()

    # A changed file shows; a bundle signed with another key is refused and changes nothing.
    with (ops / "oslo" / "oslo_version.sh").open("a") as script:
        script.write("# changed by hand\n")
    assert "integrity=modified" in version()
    refused = update(*write("6.6.6", OTHER_KEY))
    assert refused.returncode == 1 and "signature of the bundle is not valid" in refused.stdout
    assert "version=1.1.0" in version()

    # Without the configuration of the bootstrap package, the update says what is missing.
    (ops / "oslo" / "oslo.cfg").unlink()
    plain = subprocess.run(
        ["sh", str(ops / "oslo" / "oslo_update.sh")], capture_output=True, text=True
    )
    assert plain.returncode == 1 and "install the bootstrap package first" in plain.stdout


# --- the API --------------------------------------------------------------------------------


async def configure(api, public: bytes = PUBLIC) -> None:
    body = {"public_key": public.decode(), "base_url": "https://oslo.example:8443/"}
    response = await api.put("/api/bundles/settings", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["base_url"] == "https://oslo.example:8443"


async def upload(api, data: bytes) -> httpx.Response:
    return await api.post("/api/bundles", json={"data": base64.b64encode(data).decode()})


async def test_upload_download_and_bootstrap(app, api):
    assert (await upload(api, make_bundle("1.0.0"))).status_code == 422  # no key yet
    for body, message in (
        ({"public_key": "nonsense"}, "PEM"),
        ({"public_key": PUBLIC.decode(), "base_url": "http://oslo.example"}, "https://"),
        ({"public_key": PUBLIC.decode(), "ca_path": "relative/ca.pem"}, "absolute"),
    ):
        refused = await api.put("/api/bundles/settings", json=body)
        assert refused.status_code == 422 and message in refused.text
    await configure(api)
    assert (await api.get("/api/bundles/bootstrap")).status_code == 409  # no bundle yet
    other = await upload(api, make_bundle("6.6.6", OTHER_KEY))
    assert other.status_code == 422 and "signature" in other.text

    first = await upload(api, make_bundle("1.0.0"))
    assert first.status_code == 201, first.text
    assert first.json()["active"] and "oslo/oslo_update.sh" in first.json()["files"]
    second = (await upload(api, make_bundle("1.1.0"))).json()
    listed = (await api.get("/api/bundles")).json()
    assert [(b["version"], b["active"]) for b in listed["bundles"]] == [
        ("1.1.0", True),
        ("1.0.0", False),
    ]
    assert (await api.get("/api/bundle-status")).json() == {"active_version": "1.1.0"}

    # Hosts download without signing in.
    async with client(app) as anonymous:
        payload = await anonymous.get("/bundle/payload.tar.gz")
        signature = await anonymous.get("/bundle/payload.sig")
        assert payload.status_code == 200 and payload.headers["x-oslo-bundle-version"] == "1.1.0"
        bundle.verify(payload.content, signature.content, PUBLIC.decode())
        assert (await anonymous.get("/bundle/other")).status_code == 404
        assert (await anonymous.get("/api/bundles")).status_code == 401

    # Going back to the earlier bundle.
    back = await api.post(f"/api/bundles/{first.json()['id']}/activate")
    assert back.status_code == 200 and back.json()["active"]
    assert (await api.get("/api/bundle-status")).json()["active_version"] == "1.0.0"
    assert (await api.post("/api/bundles/99/activate")).status_code == 404
    assert second["id"] != first.json()["id"]

    boot = await api.get("/api/bundles/bootstrap")
    assert (
        boot.status_code == 200
        and "oslo-bootstrap-1.0.0.tar.gz" in boot.headers["content-disposition"]
    )
    with tarfile.open(fileobj=io.BytesIO(boot.content), mode="r:gz") as archive:
        assert "oslo-bootstrap/install.sh" in archive.getnames()

    # Only admins manage bundles; everybody sees the active version.
    async with client(app, await make_user(app, "conf", "configurator")) as conf:
        assert (await conf.get("/api/bundles")).status_code == 403
        assert (await upload(conf, make_bundle("2.0.0"))).status_code == 403
        assert (await conf.get("/api/bundle-status")).status_code == 200
    changes = (await api.get("/api/config-changes", params={"object_type": "bundle"})).json()
    assert {c["object_name"] for c in changes} >= {"1.0.0", "1.1.0"}


async def discover(api, host_id: int = 1) -> dict:
    response = await api.post(f"/api/hosts/{host_id}/discover")
    assert response.status_code == 200, response.text
    return (await api.get(f"/api/hosts/{host_id}")).json()


async def update(app, api, host_ids: list[int]) -> dict:
    body = {"operation": "update_bundle", "target_type": "HOST", "target_ids": host_ids}
    response = await api.post("/api/mass-operations", json=body)
    assert response.status_code == 202, response.text
    await app.state.runner.wait(response.json()["id"])
    return (await api.get(f"/api/activities/{response.json()['id']}")).json()


async def attention(api) -> list[dict]:
    return [
        i
        for i in (await api.get("/api/overview")).json()["attention"]
        if i["rule"] == "bundle_outdated"
    ]


async def test_version_check_and_update(app, api, landscape):
    landscape.bundle_source = app.state.bundles.files
    sapapp1, sapdb1 = landscape.host("sapapp1"), landscape.host("sapdb1")
    sapapp1.bundle_version, sapapp1.bundle_key = "0.9.0", PUBLIC.decode()

    host = await discover(api)
    assert host["bundle_version"] == "0.9.0" and host["bundle_integrity"] == "ok"
    missing = await discover(api, 2)  # sapdb1: not installed
    assert missing["bundle_version"] == "none" and missing["bundle_checked_at"]
    # Nothing to compare with yet: no attention.
    assert await attention(api) == []

    await configure(api)
    assert (await upload(api, make_bundle("1.0.0"))).status_code == 201
    keys = {i["key"] for i in await attention(api)}
    assert keys == {"att.bundle_outdated", "att.bundle_missing"}

    result = await update(app, api, [1, 2])
    assert result["status"] == "PARTIAL", result
    done, failed = sorted(result["children"], key=lambda c: c["target_label"])
    assert done["status"] == "SUCCEEDED" and failed["status"] == "FAILED"
    assert "bootstrap" in (failed["error"] or "")
    log = [e["message"] for e in (await api.get(f"/api/activities/{done['id']}")).json()["entries"]]
    assert any("oslo_bundle installed=1.0.0" in m for m in log)
    assert sapapp1.bundle_version == "1.0.0"
    assert (await api.get("/api/hosts/1")).json()["bundle_version"] == "1.0.0"
    assert {i["key"] for i in await attention(api)} == {"att.bundle_missing"}

    # A file changed by hand shows at the next discovery; an update repairs it.
    sapapp1.bundle_modified = True
    assert (await discover(api))["bundle_integrity"] == "modified"
    assert (await update(app, api, [1]))["status"] == "SUCCEEDED"

    # A host that trusts another key refuses the bundle.
    sapapp1.bundle_key = OTHER_PUBLIC.decode()
    assert (await upload(api, make_bundle("1.1.0"))).status_code == 201
    refused = await update(app, api, [1])
    assert refused["status"] == "FAILED"
    child = (await api.get(f"/api/activities/{refused['children'][0]['id']}")).json()
    assert any("signature" in e["message"] for e in child["entries"])
    assert sapapp1.bundle_version == "1.0.0" and sapdb1.bundle_version is None


async def test_update_needs_an_active_bundle_and_an_admin(app, api, landscape):
    landscape.host("sapapp1").bundle_version = "0.9.0"
    result = await update(app, api, [1])
    child = (await api.get(f"/api/activities/{result['children'][0]['id']}")).json()
    assert child["status"] == "FAILED" and "No OSLO operations bundle" in child["error"]
    async with client(app, await make_user(app, "conf", "configurator")) as conf:
        body = {"operation": "update_bundle", "target_type": "HOST", "target_ids": [1]}
        assert (await conf.post("/api/mass-operations", json=body)).status_code == 403
