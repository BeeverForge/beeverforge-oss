"""#266: an upgrade in place over an OpenFactory 0.7 compose deployment keeps its data and settings.

The defects were the rename's: compose prefixes volumes with the project name, so the new stack
started on empty volumes; and `init --force` carried the 0.7 `.env.compose`'s rows under their old
names, which compose never interpolates. Each row undoes one part: deciding it is an upgrade,
refusing to write over a stack's data, stopping 0.7 first, the copy itself, compose's labels, the
stamp, the toolbox left behind, the installer's step and its order, the work directory, and the
rows carried under their new names.
"""

UP = "beeverforge/onboarding/upgrade_from_openfactory.py"
DEPLOY = "beeverforge/onboarding/deployment.py"
INSTALL = "install.sh"
CLI = "beeverforge/cli.py"

VOL = "tests/test_an_openfactory_stacks_volumes_are_carried.py"
COPIED = VOL + "::test_a_0_7_stacks_volumes_are_copied_into_beeverforges"
LABELS = VOL + "::test_the_targets_carry_composes_labels_so_compose_adopts_them"
TOOLBOX = VOL + "::test_the_toolbox_is_left_and_said"
STOPPED = VOL + "::test_only_the_0_7_stack_is_stopped_before_the_copy_and_nothing_is_removed"
COPY = VOL + "::test_the_copy_runs_as_root_reads_the_0_7_volume_read_only_and_stamps_last"
NOT_07 = VOL + "::test_a_file_that_is_not_0_7s_touches_nothing"
REFUSED = VOL + "::test_a_target_a_beeverforge_stack_already_keeps_is_refused_by_name"
AGAIN = VOL + "::test_a_second_run_leaves_what_was_carried"
UNFINISHED = VOL + "::test_a_copy_that_did_not_finish_is_refused_and_made_again_on_the_next_run"
IS_07 = VOL + "::test_a_0_7_file_is_one_that_sets_an_openfactory_row"
IMAGE = VOL + "::test_the_command_copies_with_this_releases_cli_image"
CMD_REFUSES = VOL + "::test_the_command_refuses_with_the_sentence_and_a_non_zero_exit"

ENV = "tests/test_an_openfactory_env_compose_is_carried_under_its_new_names.py"
RENAMED = ENV + "::test_a_0_7_row_is_carried_as_its_new_name"
NEW_WINS = ENV + "::test_the_new_name_the_file_already_holds_wins_over_the_0_7_one"
EMPTY = ENV + "::test_an_empty_new_name_does_not_hide_the_0_7_value"
PIN = ENV + "::test_the_0_7_pin_and_the_rows_the_caller_owns_are_not_carried"

TEST = VOL

INST = "tests/test_the_installer_builds_the_commands_it_says_it_does.py"
ORDER = INST + "::test_an_upgrade_carries_a_0_7_stack_before_init_rewrites_its_file"
FAILED = INST + "::test_a_failed_carry_stops_the_upgrade_before_init_and_says_so"
INIT_FAILS = INST + "::test_an_init_that_fails_after_the_carry_says_the_way_back_to_0_7"
NOT_FIRST = INST + "::test_an_upgrade_does_not_say_register_your_first_project"
LABEL_BLIND = VOL + "::test_a_label_check_that_fails_refuses_and_empties_nothing"
STAMP_BLIND = VOL + "::test_a_stamp_check_that_fails_refuses_and_empties_nothing"
ONE_MOMENT = VOL + "::test_a_retry_copies_every_volume_from_one_moment"
REMOVE = VOL + "::test_the_closing_sentence_names_every_0_7_volume_to_remove"
WORK = INST + "::test_a_0_7_files_work_directory_is_the_one_kept"

MUTATIONS = [
    # ── the volumes ──────────────────────────────────────────────────────────────────────────
    ("THE FINDING: nothing is copied, the new stack starts empty", UP,
     "    for source, target in plan:\n", "    for source, target in []:\n", COPIED),

    ("a file that is not 0.7's is read as an upgrade", UP,
     "    if not is_a_0_7_file(env_file):\n        return done\n", "", NOT_07),

    ("a commented-out 0.7 row makes a file 0.7's", UP,
     "    return any(line.lstrip().removeprefix(\"export \").lstrip().startswith(FORMER_PREFIX)",
     "    return any(FORMER_PREFIX in line", IS_07),

    ("a target a BeeverForge stack already keeps is written over", UP,
     "        elif label != source:\n",
     "        elif False:\n", REFUSED),

    ("a finished copy is copied again over what the new stack wrote", UP,
     "        elif _has_stamp(docker, target, image):\n",
     "        elif False:\n", AGAIN),

    ("an unfinished copy is taken as finished", UP,
     # RE-PINNED 2026-11-10 (review of #514: the former volumes are recorded before the return)
     "        else:\n            plan.append((source, target))\n\n    done.former",
     "        else:\n            done.already.append((source, target))\n\n    done.former",
     UNFINISHED),

    ("the 0.7 stack is not stopped before the copy", UP,
     "    if running:\n        _ok(docker, [\"stop\", *running], \"stop the OpenFactory 0.7 containers\")\n",
     "    if False:\n        pass\n", STOPPED),

    ("the toolbox is carried with the rest", UP,
     '    "openfactory_logs": "beeverforge_logs",\n',
     '    "openfactory_logs": "beeverforge_logs",\n    "openfactory_toolbox": "beeverforge_toolbox",\n',
     TOOLBOX),

    ("the target has no compose project label, so compose does not adopt it", UP,
     '                         "--label", f"com.docker.compose.project={PROJECT}",\n', "", LABELS),

    ("the copy does not run as root, so the database's owner is lost", UP,
     '        _ok(docker, ["run", "--rm", "--user", "0", "--entrypoint", "sh",',
     '        _ok(docker, ["run", "--rm", "--entrypoint", "sh",', COPY),

    ("the 0.7 volume is mounted writable", UP,
     '                     "-v", f"{source}:/from:ro", "-v", f"{target}:/to", image, "-c",',
     '                     "-v", f"{source}:/from", "-v", f"{target}:/to", image, "-c",', COPY),

    ("the stamp is written before the copy", UP,
     '                     f"set -e; find /to -mindepth 1 -delete; cp -a /from/. /to/; "\n'
     '                     f"touch /to/{STAMP}"],',
     '                     f"set -e; touch /to/{STAMP}; find /to -mindepth 1 -delete; "\n'
     '                     f"cp -a /from/. /to/"],', COPY),

    ("the command copies with no image", CLI,
     '    chosen = image or (f"ghcr.io/beeverforge/beeverforge-cli:{version}" if version else "")',
     '    chosen = image', IMAGE),

    ("a refusal exits zero", CLI,
     '        typer.echo(f"✗ {exc}")\n        raise typer.Exit(1) from exc\n    for line in up.report(done):',
     '        typer.echo(f"✗ {exc}")\n        return\n    for line in up.report(done):', CMD_REFUSES),

    # ── the env file ─────────────────────────────────────────────────────────────────────────
    ("THE FINDING: 0.7 rows are carried under their old names", DEPLOY,
     "            name, into = PREFIX + name[len(FORMER_PREFIX):], former\n",
     "            into = held\n", RENAMED),

    ("the 0.7 value wins over the new name the file holds", DEPLOY,
     "        if not held.get(name, \"\").strip():\n            held[name] = value\n",
     "        held[name] = value\n", NEW_WINS),

    ("an empty new name hides the 0.7 value", DEPLOY,
     "        if not held.get(name, \"\").strip():\n            held[name] = value\n",
     "        if name not in held:\n            held[name] = value\n", EMPTY),

    ("0.7's pin is carried as this release's", DEPLOY,
     "        if name not in never:\n            into[name] = row.group(2)\n",
     "        into[name] = row.group(2)\n", PIN),

    # ── the installer ────────────────────────────────────────────────────────────────────────
    ("the installer never carries a 0.7 stack", INSTALL,
     "    run_preflight\n    carry_a_0_7_stack\n    run_init\n",
     "    run_preflight\n    run_init\n", ORDER),

    ("the carry runs after init rewrote the file", INSTALL,
     "    run_preflight\n    carry_a_0_7_stack\n    run_init\n",
     "    run_preflight\n    run_init\n    carry_a_0_7_stack\n", ORDER),

    ("a failed carry does not stop the upgrade", INSTALL,
     "    in_the_cli upgrade-from-openfactory --env-file /out/.env.compose \\\n        || die",
     "    in_the_cli upgrade-from-openfactory --env-file /out/.env.compose \\\n        || true || die",
     FAILED),

    ("0.7's work directory is not kept", INSTALL,
     "        if [ -z \"$kept_work_dir\" ]; then\n            kept_work_dir=$(grep '^OPENFACTORY_WORK_DIR='",
     "        if false; then\n            kept_work_dir=$(grep '^OPENFACTORY_WORK_DIR='", WORK),

    # review of #514: a check that cannot see is never "nothing there"
    ("a label check that fails reads as no such volume", UP,
     '        if "no such volume" in out.lower():\n            return None\n',
     "        return None\n", LABEL_BLIND),

    ("a stamp check that fails reads as no stamp", UP,
     "    if rc in (0, 1):\n        return rc == 0\n", "    return rc == 0\n", STAMP_BLIND),

    ("a retry copies only what is left, from a later moment", UP,
     "    plan = sorted(plan + done.already)\n    done.already = []\n", "", ONE_MOMENT),

    ("the closing sentence goes back to `compose down -v`", UP,
     "`docker volume rm {' '.join(done.former)}`",
     "`docker compose -p {FORMER_PROJECT} down -v`", REMOVE),

    ("a failed carry does not say the way back to 0.7", INSTALL,
     ' To go back to 0.7 meanwhile: ${BACK_TO_0_7}"\n', '"\n', FAILED),

    ("a failed init after a carry does not say the way back", INSTALL,
     '    [ "$CARRIED" -eq 1 ] || return 0\n', "    return 0\n", INIT_FAILS),

    ("an upgrade still says register your first project", INSTALL,
     '    if [ "$FORCE" -eq 1 ]; then\n        # AN UPGRADE KEEPS',
     '    if false; then\n        # AN UPGRADE KEEPS', NOT_FIRST),
]
