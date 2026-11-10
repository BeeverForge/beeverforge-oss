"""#264: an evidence pack or a thresholds file OpenFactory 0.7 wrote is still read, until 1.1.

`certify verify` refused a `pack.json` saying `openfactory.certify/1` and a `--thresholds` file
saying `openfactory.certify.thresholds/1`, the names 0.7 wrote the same shapes under. Both are
read now: the published schema lists the former id beside the current one, the thresholds loader
takes either, and the schema line says when a pack used the former name, with the release the
deprecation register names. Each row reads one of them no more, reads more than them, or says
nothing of it.
"""

TEST = "tests/test_an_openfactory_0_7_certify_document_is_read_until_1_1.py"
SCHEMA_JSON = "beeverforge/certify/pack.schema.json"
SCHEMA = "beeverforge/certify/schema.py"
VERIFY = "beeverforge/certify/verify.py"
REGISTER = "beeverforge/deprecations.py"

MUTATIONS = [
    ("the published schema reads the current id only", SCHEMA_JSON,
     '''    "schema": {"enum": ["beeverforge.certify/1", "openfactory.certify/1"]},''',
     '''    "schema": {"const": "beeverforge.certify/1"},'''),

    ("the published schema reads any id", SCHEMA_JSON,
     '''    "schema": {"enum": ["beeverforge.certify/1", "openfactory.certify/1"]},''',
     '''    "schema": {"type": "string"},'''),

    ("a thresholds file is read under the current name only", VERIFY,
     '''    if not isinstance(data, dict) or data.get("schema") not in (THRESHOLDS_SCHEMA,
                                                                 FORMER_THRESHOLDS_SCHEMA):''',
     '''    if not isinstance(data, dict) or data.get("schema") not in (THRESHOLDS_SCHEMA,):'''),

    ("a thresholds file is read under any name", VERIFY,
     '''    if not isinstance(data, dict) or data.get("schema") not in (THRESHOLDS_SCHEMA,
                                                                 FORMER_THRESHOLDS_SCHEMA):''',
     '''    if not isinstance(data, dict):'''),

    ("the schema line does not say the pack used the former name", VERIFY,
     '''    if bundle.document.get("schema") == FORMER_PACK_SCHEMA:''',
     '''    if False:'''),

    ("the schema line says the former name of every pack", VERIFY,
     '''    if bundle.document.get("schema") == FORMER_PACK_SCHEMA:''',
     '''    if True:'''),

    # review of #522: the former name gates nothing else
    ("a pack under the former name skips its checksums", VERIFY,
     "    out = [*_contents(bundle), *_schema(bundle), *_checksums(bundle),",
     "    former = bundle.document.get(\"schema\") == \"openfactory.certify/1\"\n"
     "    out = [*_contents(bundle), *_schema(bundle), *([] if former else _checksums(bundle)),"),

    ("a pack under the former name skips its signature", VERIFY,
     "           *_signature(bundle, allow_unsigned)]",
     "           *_signature(bundle, allow_unsigned or bundle.document.get(\"schema\") == "
     "\"openfactory.certify/1\")]"),

    ("the register keeps the documents a release longer", REGISTER,
     '''    Removal("openfactory-documents", "1.1",''',
     '''    Removal("openfactory-documents", "1.2",'''),

    ("the release the schema line names is spelled again", SCHEMA,
     '''FORMER_READ_UNTIL = removed_in("openfactory-documents")''',
     '''FORMER_READ_UNTIL = "1.2"'''),

    ("the former pack id is misspelled", SCHEMA,
     '''FORMER_PACK_SCHEMA = "openfactory.certify/1"''',
     '''FORMER_PACK_SCHEMA = "openfactory.certify/2"'''),
]
