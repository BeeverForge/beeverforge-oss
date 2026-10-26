"""P0.4 — the job workspace leaves `/var/lib`, and every way that can go wrong is red.

Run:  .venv/bin/python tools/mutate.py tools/mutations/installer_work_dir_needs_no_root.py

Nine cuts across three files, because this change has three halves that can rot independently: the
compose file's interpolation (does an OLD install still resolve the old path?), the generator's
chosen default (is it absolute, tilde-free and owned by the user?), and the command that has to
CREATE it (a row nobody makes is the original defect wearing a better address).

The first two cuts are the ones worth reading. `${VAR:-d}` and `${VAR-d}` differ by one character,
both look correct in review, and only the first treats an EMPTY row as absent — which is the state
`.env.compose.example` ships. A change from one to the other would move the job workspaces of a
running deployment without anybody noticing until a box mounted an empty directory.
"""

TEST = "tests/test_an_environment_written_before_this_change_still_resolves_the_old_path.py"

COMPOSE = "docker-compose.yml"
GENERATOR = "beeverforge/onboarding/deployment.py"
CLI = "beeverforge/cli.py"

_BOTH_SIDES = ("      - ${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-work}:"
               "${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-work}")
_CHOSEN = '    return str((root / "beeverforge" / "work").expanduser().resolve())'

MUTATIONS = [
    # ── the compatibility guarantee: an install written before this change ──────────────────────
    ("the default is dropped, so an .env.compose with no row resolves to nothing",
     COMPOSE,
     "      BEEVERFORGE_WORK_DIR: ${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-work}",
     "      BEEVERFORGE_WORK_DIR: ${BEEVERFORGE_WORK_DIR}"),

    ("the colon is dropped — an EMPTY row stops falling back, which is what the template ships",
     COMPOSE,
     "      BEEVERFORGE_WORK_DIR: ${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-work}",
     "      BEEVERFORGE_WORK_DIR: ${BEEVERFORGE_WORK_DIR-/var/lib/beeverforge-work}"),

    # ── the two occurrences that are connected by nothing but agreement ─────────────────────────
    ("the bind's source and target default to different paths — the box mounts an empty directory",
     COMPOSE,
     _BOTH_SIDES,
     "      - ${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-workspaces}:"
     "${BEEVERFORGE_WORK_DIR:-/var/lib/beeverforge-work}",
     "tests/test_two_projects_do_not_share_a_box.py"),

    ("the bind stops following the variable at all, so a configured work dir is silently ignored",
     COMPOSE,
     _BOTH_SIDES,
     "      - /var/lib/beeverforge-work:/var/lib/beeverforge-work",
     "tests/test_two_projects_do_not_share_a_box.py"),

    # ── the path the generator chooses ──────────────────────────────────────────────────────────
    ("the chosen directory is written with a `~`, which compose does not expand in a bind source",
     GENERATOR, _CHOSEN, '    return "~/.local/share/beeverforge/work"',
     "tests/test_the_generated_environment_names_a_work_directory_that_needs_no_root.py"),

    ("the chosen directory is relative, so every workspace lands inside whatever ran `up`",
     GENERATOR, _CHOSEN, '    return "beeverforge/work"',
     "tests/test_the_generated_environment_names_a_work_directory_that_needs_no_root.py"),

    ("the generator goes back to the path that needs root",
     GENERATOR, _CHOSEN, '    return "/var/lib/beeverforge-work"',
     "tests/test_the_generated_environment_names_a_work_directory_that_needs_no_root.py"),

    ("the row is commented out, so the compose default applies and the sudo path is back",
     GENERATOR,
     "BEEVERFORGE_WORK_DIR={work_dir}",
     "# BEEVERFORGE_WORK_DIR={work_dir}",
     "tests/test_the_generated_environment_names_a_work_directory_that_needs_no_root.py"),

    # ── the row is only half the change: something has to MAKE the directory ────────────────────
    ("init names the directory and does not create it — Docker will, owned by root",
     CLI,
     "        Path(work_dir).mkdir(parents=True, exist_ok=True)",
     "        pass",
     "tests/test_the_generated_environment_names_a_work_directory_that_needs_no_root.py"),
]
