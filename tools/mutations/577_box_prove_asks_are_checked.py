"""#577 — `box prove` checks what it is asked, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/577_box_prove_asks_are_checked.py

SEVEN CUTS, each required to go red:

  1. The shell proves under the name it was given: compared with the project's own name only, a
     registry key that differs from it would start a proof on the worker from `box prove`.
  2. The CLI refuses a running answer: rendered as a verdict, a proof that has not ended would
     print "NOT PROVEN".
  3. A malformed repository is refused on the worker path before `_runner_view`: without it, a
     name that is not `owner/name` would be started as a proof of some other checkout.
  4. The repository bound is the bare repository's own: at the qualified form's 160, a
     repository whose `#0` ticket that form refuses would be started.
  5. The row's flight is keyed by the image asked: without it, an ask for another image would
     join the running proof of the default one.
  6. The row's flight is keyed by the box: without it, an ask in the `worktree` box would join
     the running `container` proof.
  7. The id itself hashes the image and the box: dropped from the hash, both asks above join.

The guard under test: `tests/test_box_prove_is_a_catalogue_row.py`.
"""

TEST = "tests/test_box_prove_is_a_catalogue_row.py"

CATALOG = "beeverforge/actions/catalog.py"
CLI = "beeverforge/cli.py"
BOX_PROVE = "beeverforge/box_prove.py"

MUTATIONS = [
    ("the shell compares the project's own name, not the name it was given", CATALOG,
     "    if shell is not None and (shell.name or getattr(shell.project, \"name\", None))"
     " == project:\n",
     "    if shell is not None and getattr(shell.project, \"name\", None) == project:\n",
     TEST + "::test_a_registry_key_that_differs_from_the_name_still_proves_in_place"),

    ("the CLI renders a running answer as a verdict", CLI,
     "    if data.get(\"state\") == RUNNING:\n",
     "    if False:\n",
     TEST + "::test_the_cli_refuses_a_running_answer_instead_of_rendering_a_verdict"),

    ("a malformed repository reaches `_runner_view`", CATALOG,
     "        if len(repo) > _REPO_MAX or not _REPO_RE.match(repo):\n",
     "        if len(repo) > _REPO_MAX:\n",
     TEST + "::test_a_malformed_repo_is_refused_on_the_worker_before_anything_starts"),

    ("a repository is bounded by the qualified form's bound", CATALOG,
     "        if len(repo) > _REPO_MAX or not _REPO_RE.match(repo):\n",
     "        if len(repo) > 160 or not _REPO_RE.match(repo):\n",
     TEST + "::test_a_repository_at_its_bound_starts_and_one_past_it_is_refused"),

    ("the row's flight is not keyed by the image asked", CATALOG,
     "    handle = box_prove.workflow_id(key, ref, image, box_kind)\n",
     "    handle = box_prove.workflow_id(key, ref, \"\", box_kind)\n",
     TEST + "::test_a_second_ask_with_another_image_or_box_has_its_own_flight"),

    ("the row's flight is not keyed by the box", CATALOG,
     "    handle = box_prove.workflow_id(key, ref, image, box_kind)\n",
     "    handle = box_prove.workflow_id(key, ref, image, \"container\")\n",
     TEST + "::test_a_second_ask_in_another_box_has_its_own_flight"),

    ("the id hashes neither the image nor the box", BOX_PROVE,
     "        f\"{key}\\n{ref}\\n{image}\\n{sandbox}\".encode()).hexdigest()\n",
     "        f\"{key}\\n{ref}\".encode()).hexdigest()\n"),
]
