"""An evidence pack or a thresholds file OpenFactory 0.7 wrote is still read, until 1.1 (#264).

BeeverForge writes its documents as `beeverforge.<kind>/N`; OpenFactory 0.7 wrote the same shapes
as `openfactory.<kind>/N` (its `pack.schema.json` at v0.7.0 differs from this one in the names
only). Of those documents, two are READ back by the platform, both by `beeverforge certify
verify`: the evidence pack's `pack.json` (`openfactory.certify/1`) and a `--thresholds` file
(`openfactory.certify.thresholds/1`). A pack a partner made with 0.7, or a thresholds file the
program published for it, was refused as "must be 'beeverforge.certify/1'". Both are read now,
under the release the deprecation register names, and the schema line says which name it read.
The others (`doctor/1`, `preflight/1`, `box-status/1`, `certify.redactions/1`) are written only.
"""

from __future__ import annotations

import json

import pytest

from beeverforge import deprecations
from beeverforge.certify import schema
from beeverforge.certify import verify as v
from tests import test_certify_verify_holds_a_pack_to_its_thresholds as bed
from tests.test_certify_verify_holds_a_pack_to_its_thresholds import (
    _cli,
    _lines,
    _members,
    _sealed,
    _tar,
)

#: the certify bed's fixtures: the pack `certify deployment` writes, and that pack passing
written, good = bed.written, bed.good

FORMER_PACK = "openfactory.certify/1"
FORMER_THRESHOLDS = "openfactory.certify.thresholds/1"


def _as(good_pack, tmp_path, schema_id: str):
    files = _members(good_pack)
    document = json.loads(files["pack.json"])
    document["schema"] = schema_id
    files["pack.json"] = json.dumps(document).encode()
    return _tar(tmp_path / "as.tgz", _sealed(files))


def test_a_pack_openfactory_0_7_wrote_is_verified_and_says_which_name_it_read(good, tmp_path):
    result = _cli("verify", str(_as(good, tmp_path, FORMER_PACK)), "--allow-unsigned")

    assert result.exit_code == 0, result.output
    [said] = [m for mark, i, m in _lines(result.output) if i == "schema"]
    assert FORMER_PACK in said and "OpenFactory 0.7" in said, said
    assert f"until BeeverForge {deprecations.removed_in('openfactory-documents')}" in said, said


def test_a_pack_written_under_the_current_name_says_nothing_of_the_former(good):
    result = _cli("verify", str(good), "--allow-unsigned")

    [said] = [m for mark, i, m in _lines(result.output) if i == "schema"]
    assert said == f"pack.json matches {schema.PACK_SCHEMA}", said


@pytest.mark.parametrize("schema_id", ["openfactory.certify/2", "beeverforge.certify/2",
                                       "openfactory.certify", "OPENFACTORY.certify/1"])
def test_no_other_name_or_version_is_read(good, tmp_path, schema_id):
    result = _cli("verify", str(_as(good, tmp_path, schema_id)), "--allow-unsigned")

    assert result.exit_code == 1, result.output
    assert any(mark == "✗" and i == "schema" and schema_id in m
               for mark, i, m in _lines(result.output)), result.output


def test_a_thresholds_file_openfactory_0_7_wrote_holds_the_same_thresholds(tmp_path):
    shipped = v.THRESHOLDS_FILE.read_text(encoding="utf-8")
    assert f"schema: {v.THRESHOLDS_SCHEMA}\n" in shipped
    former = tmp_path / "thresholds.yaml"
    former.write_text(shipped.replace(f"schema: {v.THRESHOLDS_SCHEMA}\n",
                                      f"schema: {FORMER_THRESHOLDS}\n"), encoding="utf-8")

    assert v.load_thresholds(former) == v.load_thresholds()


@pytest.mark.parametrize("schema_id", ["openfactory.certify.thresholds/2",
                                       "beeverforge.certify.thresholds/2", FORMER_PACK])
def test_a_thresholds_file_under_any_other_name_is_refused(tmp_path, schema_id):
    other = tmp_path / "thresholds.yaml"
    other.write_text(f"schema: {schema_id}\nthresholds:\n"
                     "  - {id: T-JOBS, check: min_jobs, min: 1}\n", encoding="utf-8")

    with pytest.raises(v.ThresholdsError, match=f"schema: {v.THRESHOLDS_SCHEMA}"):
        v.load_thresholds(other)


def test_the_former_names_are_registered_and_read_from_the_register():
    assert deprecations.removed_in("openfactory-documents") == "1.1"
    assert schema.FORMER_PACK_SCHEMA == FORMER_PACK
    assert v.FORMER_THRESHOLDS_SCHEMA == FORMER_THRESHOLDS
    assert schema.FORMER_READ_UNTIL == deprecations.removed_in("openfactory-documents")


def test_the_published_schema_names_the_current_id_and_the_former_one_only():
    published = schema.pack_schema()

    assert published["$id"] == schema.PACK_SCHEMA
    assert published["properties"]["schema"] == {
        "enum": [schema.PACK_SCHEMA, schema.FORMER_PACK_SCHEMA]}
