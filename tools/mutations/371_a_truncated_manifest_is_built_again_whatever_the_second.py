"""A shape behind a truncated manifest is built again, and the rebuilt manifest is read by the next
worker, whichever second each build lands in (#371): the test ran its two builds on the clock and
compared their commits, so two builds a second apart failed it. It now pins two different dates
and compares the trees; each row cuts one of the two things it still has to prove.

ROW 1 is the rebuild: the truncated manifest's template is read as it lies, so nothing is built
again. ROW 2 is the next worker: the rebuilt manifest never replaces the truncated one, so the
third ask builds a third time.

NO ROW PUTS THE OLD COMMIT COMPARISON BACK: that would cut the guard, not the code it guards. The
old dependence was measured once instead, on the two pinned dates: `rev-parse HEAD` of the two
builds differs on every run, so the old assertion fails every time.
"""

TEST = ("tests/test_a_test_gets_its_repository_from_the_bed.py"
        "::test_a_manifest_that_does_not_parse_is_built_again_not_refused_forever")

BED = "tests/the_git_bed.py"

#: The except clause that sends a truncated manifest to a rebuild, split to fit the line.
REBUILD = ("        except (ValueError, KeyError, TypeError):"
           "  # truncated or not the shape's: build it again\n")

#: From the read of the manifest to the write of the rebuilt one, as `_template` holds it.
READ_TO_WRITE = (
    "            template = self._read(manifest, where)\n"
    "            if template is None:\n"
    "                template = self._build(name, build, home, where)\n"
    "                # WRITTEN WHOLE OR NOT AT ALL: beside itself, then moved into place in one"
    " step,\n"
    "                # so a worker killed mid-write leaves no manifest and the next ask builds"
    " again.\n"
    '                part = home / "manifest.json.part"\n'
    '                part.write_text(json.dumps({"name": name, "print": template.print_,\n'
    '                                            "texts": template.texts}), encoding="utf-8")\n'
    "                os.replace(part, manifest)\n"
)

MUTATIONS = [
    ("the shape behind a truncated manifest is not built again: its old template is read", BED,
     REBUILD + "            return None\n",
     REBUILD + "            return _Template(root=where, print_=_fingerprint(where), texts=[])\n"),

    # Whether a manifest lay there is taken before the read: `_build` empties the shape's home
    # first, so a test of `manifest.exists()` at the write would never see the truncated one.
    ("the rebuilt manifest never replaces the truncated one, so the next worker builds again", BED,
     READ_TO_WRITE,
     "            stale = manifest.exists()\n"
     + READ_TO_WRITE.replace("os.replace(part, manifest)\n",
                             "part.unlink() if stale else os.replace(part, manifest)\n")),
]
