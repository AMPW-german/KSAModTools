import csv
import io
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock
import xml.etree.ElementTree as ET

from scripts import update_ksa_dlls


class UpdateKsaDllsTests(unittest.TestCase):
    def test_exact_nuget_version_is_returned(self) -> None:
        with mock.patch.object(
            update_ksa_dlls.urllib.request,
            "urlopen",
            return_value=io.BytesIO(b'{"versions": ["1.0.0", "1.2.0"]}'),
        ):
            self.assertEqual(
                update_ksa_dlls.resolve_nuget_version("Package", "1.0.0"),
                "1.0.0",
            )

    def test_unpublished_exact_version_returns_none_instead_of_nearest(self) -> None:
        with mock.patch.object(
            update_ksa_dlls.urllib.request,
            "urlopen",
            return_value=io.BytesIO(b'{"versions": ["1.0.0", "1.2.0"]}'),
        ):
            self.assertIsNone(
                update_ksa_dlls.resolve_nuget_version("Package", "1.1.0")
            )

    def test_missing_nuget_package_returns_none_on_404(self) -> None:
        error = urllib.error.HTTPError("url", 404, "Not Found", None, io.BytesIO())
        with mock.patch.object(
            update_ksa_dlls.urllib.request, "urlopen", side_effect=error
        ):
            self.assertIsNone(
                update_ksa_dlls.resolve_nuget_version("Missing.Package", "1.0.0")
            )

    def test_non_404_nuget_error_is_raised(self) -> None:
        error = urllib.error.HTTPError("url", 503, "Unavailable", None, io.BytesIO())
        with mock.patch.object(
            update_ksa_dlls.urllib.request, "urlopen", side_effect=error
        ):
            with self.assertRaises(urllib.error.HTTPError):
                update_ksa_dlls.resolve_nuget_version("Package", "1.0.0")

    def test_empty_nuget_version_list_returns_none(self) -> None:
        with mock.patch.object(
            update_ksa_dlls.urllib.request,
            "urlopen",
            return_value=io.BytesIO(b'{"versions": []}'),
        ):
            self.assertIsNone(
                update_ksa_dlls.resolve_nuget_version("Missing.Package", "1.0.0")
            )

    def test_update_keeps_unpublished_dependency_as_local_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            ksa_dir = root / "ksa"
            repo_dir = root / "dlls"
            ksa_dir.mkdir()
            repo_dir.mkdir()
            dll_names = (
                *update_ksa_dlls.CORE_DLLS,
                "Brutal.Buffers.dll",
                "BepuPhysics.dll",
                "BepuUtilities.dll",
                "Tomlet.dll",
            )
            for name in dll_names:
                (ksa_dir / name).write_bytes(b"")

            def resolve(package_id: str, dll_version: str) -> str | None:
                return None if package_id == "Ahwoo.BRUTAL.Buffers" else "1.0.0"

            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "update_ksa_dlls.py",
                        "--dll-repo-dir",
                        str(repo_dir),
                        "--ksa-dir",
                        str(ksa_dir),
                        "--no-git",
                        "--no-wait",
                    ],
                ),
                mock.patch.object(
                    update_ksa_dlls,
                    "get_file_version",
                    return_value="2026.11.10.5801",
                ),
                mock.patch.object(
                    update_ksa_dlls, "get_product_semver", return_value="1.0.0"
                ),
                mock.patch.object(
                    update_ksa_dlls,
                    "fetch_starmap_harmony_version",
                    return_value="2.4.3",
                ),
                mock.patch.object(
                    update_ksa_dlls, "resolve_nuget_version", side_effect=resolve
                ),
            ):
                update_ksa_dlls.main()

            self.assertTrue((repo_dir / "Brutal.Buffers.dll").is_file())
            with (repo_dir / "ksa-versions.csv").open(
                encoding="utf-8", newline=""
            ) as csv_file:
                rows = list(csv.DictReader(csv_file))
            buffers = next(row for row in rows if row["name"] == "Brutal.Buffers")
            self.assertEqual(buffers["is_nuget"], "false")
            self.assertEqual(buffers["package_id"], "")
            props = (repo_dir / "KsaNuGet.props").read_text(encoding="utf-8")
            ET.parse(repo_dir / "KsaNuGet.props")
            self.assertIn('<Reference Include="Brutal.Buffers">', props)
            self.assertIn("$(MSBuildThisFileDirectory)Brutal.Buffers.dll", props)


if __name__ == "__main__":
    unittest.main()
