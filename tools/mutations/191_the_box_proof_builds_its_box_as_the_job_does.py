"""The box proof builds its box with the same knobs as the job's box (#191).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/191_the_box_proof_builds_its_box_as_the_job_does.py

Row 1 is the defect as it shipped: the proof's box is built without the image's pull credential the
job's box gets. Row 2 builds the job's box from somewhere else than the shared function. Row 3 drops
the pull credential from the shared function, so neither box pulls with it.
"""

TEST = "tests/test_the_box_proof_builds_its_box_as_the_job_does.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the proof's box has no pull credential", "beeverforge/box_prove.py",
     "        knobs = box_knobs(project)\n",
     '        knobs = {k: v for k, v in box_knobs(project).items() if k != "pull_credential"}\n'),

    ("the job's box is built without the shared function", "beeverforge/factory.py",
     "    knobs = box_knobs(project)\n",
     "    knobs = {}\n"),

    ("the shared function drops the pull credential", "beeverforge/factory.py",
     '        knobs["pull_credential"] = pull\n',
     "        pass\n"),
]
