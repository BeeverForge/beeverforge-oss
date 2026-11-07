"""#265 (GitHub, BeeverForge/beeverforge-oss): the core reads `.beeverforge/` and `.openfactory/`.

Each row takes one piece away: the answer of which folder a repository uses, a reader or a writer
that takes it, or one of the two names from a guard that must hold for both. Every row must turn
`tests/test_the_core_reads_beeverforge_beside_openfactory.py` red — or the certify test, where the
row says so.
"""

TEST = "tests/test_the_core_reads_beeverforge_beside_openfactory.py"

NS = "beeverforge/namespace.py"
WRITES = "beeverforge/policy/context_writes.py"
ASSEMBLE = "beeverforge/preview/assemble.py"
FLOOR = "beeverforge/org_defaults/floor.yaml"
CONTROLS = "beeverforge/certify/controls.py"
MACHINE = "beeverforge/orchestrator/machine.py"
INFER = "beeverforge/onboarding/preview_infer.py"
PROPOSE = "beeverforge/onboarding/preview_propose.py"
MODULE = "beeverforge/product/module.py"
IMPORTING = "beeverforge/product/importing.py"
INGEST = "beeverforge/product/documents/ingest.py"
DOCTOR = "beeverforge/doctor.py"
CATALOG = "beeverforge/actions/catalog.py"
PROFILES = "beeverforge/policy/profiles.py"
PRODUCT = "beeverforge/preview/product.py"
CERTIFY_TEST = "tests/test_certify_controls_answer_from_what_was_read.py"

MUTATIONS = [
    # ── which folder a repository uses ──
    ("a repository that keeps only `.openfactory/` is read as a new one", NS,
     "    if (Path(root) / FORMER_DIR).is_dir() and not (Path(root) / DIR).is_dir():",
     "    if False:"),
    ("with both folders, the stale one wins", NS,
     "    if (Path(root) / FORMER_DIR).is_dir() and not (Path(root) / DIR).is_dir():",
     "    if (Path(root) / FORMER_DIR).is_dir():"),
    ("the one reader ignores the folder the repository keeps", NS,
     "    new = root / in_repo(root, relative)\n",
     "    new = root / relative\n"),
    ("an explicit path is moved under the folder like a default one", NS,
     "    if rel == DIR or rel.startswith(f\"{DIR}/\"):\n        return dir_in(root) + rel[len(DIR):]"
     "\n    return str(relative)",
     "    if rel == DIR or rel.startswith(f\"{DIR}/\"):\n        return dir_in(root) + rel[len(DIR):]"
     "\n    return dir_in(root) + \"/\" + rel"),

    # ── the guards' one tuple, without either name ──
    ("every guard forgets the former name", NS,
     "DIRS = (DIR, FORMER_DIR)",
     "DIRS = (DIR,)"),
    ("every guard forgets the current name", NS,
     "DIRS = (DIR, FORMER_DIR)",
     "DIRS = (FORMER_DIR,)"),

    # ── the context-write policy ──
    ("a writer may land anything under the former name", WRITES,
     "        if (not norm or namespace.is_ours(norm)",
     "        if (not norm or norm.startswith(PLATFORM_DIR) or norm + \"/\" == PLATFORM_DIR"),
    ("an import's own record is refused under the former name", WRITES,
     "    records = tuple(r for r in (import_record(import_id, d) for d in namespace.DIRS) if r)",
     "    records = tuple(r for r in (import_record(import_id),) if r)"),
    ("an import's record is admitted under any folder at all", WRITES,
     "    if folder not in namespace.DIRS or not _IMPORT_ID.match(ident):",
     "    if not _IMPORT_ID.match(ident):"),

    # ── the preview's shape ──
    ("a shape file under the former name is not the shape", ASSEMBLE,
     "SHAPE_FILES = tuple(f\"{d}/{name}\" for d in namespace.DIRS",
     "SHAPE_FILES = tuple(f\"{d}/{name}\" for d in (namespace.DIR,)"),
    ("a drafted file under the former name's `preview/` is not the shape", ASSEMBLE,
     "SHAPE_DIRS = tuple(f\"{d}/preview/\" for d in namespace.DIRS)",
     "SHAPE_DIRS = (f\"{namespace.DIR}/preview/\",)"),
    ("the manifest under the former name is not the shape", ASSEMBLE,
     "    fixed = {*(posixpath.normpath(m) for m in namespace.spellings(manifest_path)), "
     "*SHAPE_FILES}",
     "    fixed = {posixpath.normpath(manifest_path), *SHAPE_FILES}"),
    ("the pull request shows no shape edited under the former name", MACHINE,
     "        if not any(h in self._SHAPE_NAMES or namespace.is_ours(h) for h in hits):",
     "        if not any(h in self._SHAPE_NAMES or h.startswith(\".beeverforge/\") for h in hits):"),
    ("the pull request lists the drafted files of the current name only", MACHINE,
     "        folder = namespace.dir_in(root)\n",
     "        folder = namespace.DIR\n"),
    ("the pull request reads the shape's manifest under the current name only", MACHINE,
     "        manifest_rel = namespace.in_repo(root, namespace.MANIFEST)\n        try:",
     "        manifest_rel = namespace.MANIFEST\n        try:"),

    # ── the floor and the control that certifies it ──
    ("the floor stops protecting the manifest under the former name", FLOOR,
     "  - \".openfactory/**\"\n",
     ""),
    ("the floor stops protecting the manifest under the current name", FLOOR,
     "  - \".beeverforge/**\"\n  # …AND",
     "  # …AND"),
    ("the certify control passes a floor that protects the current name only", CONTROLS,
     "    wanted = [f\"{d}/**\" for d in namespace.DIRS]",
     "    wanted = [f\"{namespace.DIR}/**\"]", CERTIFY_TEST),
    ("the certify control passes a floor that protects the former name only", CONTROLS,
     "    wanted = [f\"{d}/**\" for d in namespace.DIRS]",
     "    wanted = [f\"{namespace.FORMER_DIR}/**\"]", CERTIFY_TEST),

    # ── what is never read as the repository's own ──
    ("a Dockerfile drafted under the former name is read as the repository's", INFER,
     "                   if _is_dockerfile(Path(rel).name) and not namespace.is_ours(rel)",
     "                   if _is_dockerfile(Path(rel).name) and not rel.startswith(\".beeverforge/\")"),
    ("an import's record under the former name goes to the documents' pass", MODULE,
     "    return [p for p in landed if not namespace.is_ours(p)]",
     "    return [p for p in landed if not p.startswith(\".beeverforge/\")]"),
    ("an imported folder lands the former folder", IMPORTING,
     "            if folder.startswith(\".\"):\n                budget.leave(",
     "            if folder in (\".git\", \".beeverforge\"):\n                budget.leave("),
    ("an imported archive lands the former folder", IMPORTING,
     "def _hidden(path: str) -> bool:\n    return any(part.startswith(\".\") for part in "
     "PurePosixPath(path).parts)",
     "def _hidden(path: str) -> bool:\n    return any(part in (\".git\", \".beeverforge\") for "
     "part in PurePosixPath(path).parts)"),
    ("the documents' walk reads the former folder", INGEST,
     "            if folder.startswith(\".\"):\n                continue",
     "            if folder in (\".git\", \".beeverforge\"):\n                continue"),
    ("a document event may name a file under the former folder", INGEST,
     "def _hidden(path: PurePosixPath) -> bool:\n    return any(part.startswith(\".\") for part "
     "in path.parts)",
     "def _hidden(path: PurePosixPath) -> bool:\n    return any(part in (\".git\", "
     "\".beeverforge\") for part in path.parts)"),

    # ── the readers and the writers ──
    ("a client's profiles are read under the current name only", PROFILES,
     "    return project_dir / namespace.in_repo(project_dir, PROJECT_PROFILES_SUBDIR.as_posix())",
     "    return project_dir / PROJECT_PROFILES_SUBDIR"),
    ("a preview reads the product's declaration under the current name only", PRODUCT,
     "    rel = namespace.in_repo(Path(root), PRODUCT_YAML)\n",
     "    rel = PRODUCT_YAML\n"),
    ("a preview reads the manifest under the current name only", INFER,
     "    text = _read_in(root, namespace.in_repo(root, namespace.MANIFEST))",
     "    text = _read_in(root, namespace.MANIFEST)"),
    ("an import's record is looked for under the current name only", IMPORTING,
     "    where = import_record(ident, namespace.dir_in(root))",
     "    where = import_record(ident)"),
    ("env apply writes a second manifest under the current name", CATALOG,
     "    in_repo = namespace.in_repo(checkout, str(found.manifest_path))",
     "    in_repo = str(found.manifest_path)"),
    ("a drafted preview lands under the current name beside the client's folder", PROPOSE,
     "    folder = namespace.dir_in(checkout)\n    out = relocated(",
     "    folder = namespace.DIR\n    out = relocated("),
    ("moving a draft rewrites the operator's own `~/.beeverforge/` too", PROPOSE,
     "_OUR_FOLDER = re.compile(r\"(?<![\\w~/.-])\" + re.escape(namespace.DIR) + r\"/\")",
     "_OUR_FOLDER = re.compile(re.escape(namespace.DIR) + r\"/\")"),

    # ── doctor ──
    ("doctor never names the stale folder", DOCTOR,
     "    if checkout is None or not namespace.stale_former_dir(checkout):",
     "    if True:"),
    ("doctor calls a lone folder stale", NS,
     "    return (Path(root) / DIR).is_dir() and (Path(root) / FORMER_DIR).is_dir()",
     "    return (Path(root) / DIR).is_dir() or (Path(root) / FORMER_DIR).is_dir()"),
    ("doctor prints an empty folder line for every healthy repository", DOCTOR,
     "    if stale is not None and stale.message:",
     "    if stale is not None:"),
]
