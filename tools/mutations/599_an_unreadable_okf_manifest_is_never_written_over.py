"""A knowledge-bundle manifest that exists but cannot be read is never written over.

`read_manifest` reads every failure as "no manifest", and three writers built a fresh manifest on
that `None` and wrote it over the file — losing the answered questions it held. The writers now
read through `load_manifest`, which raises `ManifestUnreadable` for a file that is there and
cannot be read, and each stops before its first write; the refresh activity names the refusal
and leaves the requests pending.

Each row below drops one writer's check — the renewal folds the refusal into a fresh manifest,
the recording and the covering go back to the lenient reader, the activity marks the requests
taken anyway — or folds "cannot be read" back into `None` in the reader itself. The guard must
go red on each.
"""

TEST = "tests/test_an_unreadable_okf_manifest_is_never_written_over.py"

_OKF = "beeverforge/knowledge/okf.py"
_RENEW = "beeverforge/onboarding/renew.py"
_GAPS = "beeverforge/knowledge/gaps.py"
_COVER = "beeverforge/onboarding/cover.py"
_ACTIVITY = "beeverforge/runtime/temporal/activities.py"

MUTATIONS = [
    ("the strict reader reads a manifest that is not UTF-8 as no manifest",
     _OKF,
     "    if text is None:\n        raise ManifestUnreadable(path, unread)\n",
     "    if text is None:\n        return None\n"),

    ("the strict reader reads a manifest that is not YAML as no manifest",
     _OKF,
     "    except yaml.YAMLError as exc:\n"
     "        raise ManifestUnreadable(path, f\"it is not YAML: {exc}\") from exc\n",
     "    except yaml.YAMLError:\n        return None\n"),

    ("the renewal folds an unreadable manifest into a fresh one and writes the round",
     _RENEW,
     "        return Renewal(len(existing), 0, 0, 0, MANIFEST_UNREADABLE, reason=str(exc))\n",
     "        previous = None\n"),

    ("the recording of requested gaps reads the manifest leniently again",
     _GAPS,
     "    manifest = load_manifest(bundle) or OkfManifest(",
     "    manifest = __import__(\"beeverforge.knowledge.okf\", fromlist=[\"x\"])"
     ".read_manifest(bundle) or OkfManifest("),

    ("the covering reads the manifest leniently again",
     _COVER,
     "        previous = load_manifest(bundle)\n",
     "        previous = __import__(\"beeverforge.knowledge.okf\", fromlist=[\"x\"])"
     ".read_manifest(bundle)\n"),

    ("the refresh marks the requests taken though the manifest could not record them",
     _ACTIVITY,
     "        recorded, wanted = [], []\n",
     "        recorded = []\n"),
]
