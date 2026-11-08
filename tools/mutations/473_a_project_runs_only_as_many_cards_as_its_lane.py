"""A project runs only as many cards at once as its lane allows (#473), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
          tools/mutations/473_a_project_runs_only_as_many_cards_as_its_lane.py

The floor is shared by every project and the poller takes TO-DO cards in board order until it is
full, so one project could take every slot and its dependent cards started together. The claims,
each a row:

  1. `scan_todo` answers through the lane;
  2. the lane counts only this project's running jobs, by the longest registered name;
  3. the room is the lane minus what runs, never below none, cut in board order;
  4. no lane (unset, blank, `0`, below `0`, not a number) is the floor alone, and a value that is
     not a number is said in the log;
  5. the configuration reference lists the variable with its default, read from the code.
  6. the panel's "Scan TO-DO now" button makes the same cut, counting this project's jobs as
     the poller does, and says when the lane is what held the queue (#480).
"""

TEST = "tests/test_a_project_runs_only_as_many_cards_as_its_lane.py"
DOCS = "tests/test_the_floor_the_limits_and_the_state_directory_are_documented.py"

ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
FLOOR = "beeverforge/runtime/temporal/__init__.py"
REFERENCE = "docs/reference/configuration.md"
SCAN = "beeverforge/actions/catalog.py"

MUTATIONS = [
    # 1. the poller's read goes through the lane
    ("TODAY'S DEFECT: scan_todo answers every admitted card", ACTIVITIES,
     "    return await _within_the_projects_lane(inp.project, admitted)\n",
     "    return admitted\n"),

    # 2. whose jobs count
    ("every running job takes this project's lane", ACTIVITIES,
     "        if parse_job_id(wf.id, known_projects=names)[0] == project_name:\n",
     "        if True:\n"),
    ("a job is read without the registered names (its last hyphen decides)", ACTIVITIES,
     "        if parse_job_id(wf.id, known_projects=names)[0] == project_name:\n",
     "        if parse_job_id(wf.id, known_projects=[])[0] == project_name:\n"),

    # 3. the room
    ("running jobs do not reduce the room", ACTIVITIES,
     "    room = max(0, lane - running)\n",
     "    room = lane\n"),
    ("the lane is one wider than it says", ACTIVITIES,
     "    room = max(0, lane - running)\n",
     "    room = max(0, lane + 1 - running)\n"),
    ("the cut takes the last cards, not the first", ACTIVITIES,
     "    return admitted[:room]\n",
     "    return admitted[len(admitted) - room:]\n"),

    # 4. no lane
    ("no lane cuts everything", ACTIVITIES,
     "    if lane <= 0 or not admitted:\n        return admitted\n",
     "    if not admitted:\n        return admitted\n"),
    ("a negative lane is a lane", FLOOR,
     "        return max(0, int(raw))\n",
     "        return int(raw)\n"),
    ("a value that is not a number is read as one job", FLOOR,
     "            raw)\n        return 0\n",
     "            raw)\n        return 1\n"),
    ("a value that is not a number is not said", FLOOR,
     '        logging.getLogger("beeverforge.runtime.temporal").warning(\n',
     '        (lambda *a: None)(\n'),
    ("the lane is read from another variable", FLOOR,
     '    raw = (os.environ.get("BEEVERFORGE_JOBS_PER_PROJECT") or "").strip()\n',
     '    raw = (os.environ.get("BEEVERFORGE_JOBS_PER_REPO") or "").strip()\n'),

    # 5. the reference
    ("the reference drops the lane's row", REFERENCE,
     "| `BEEVERFORGE_JOBS_PER_PROJECT` | the lane:",
     "| JOBS_PER_PROJECT | the lane:",
     DOCS),
    ("the reference says a default the code does not have", REFERENCE,
     "| `0` (no lane: the floor alone decides) |",
     "| `1` (no lane: the floor alone decides) |",
     DOCS),

    # 6. the scan button (#480)
    ("TODAY'S DEFECT (#480): the scan button counts the floor alone", SCAN,
     "        slots = min(slots, max(0, lane - mine))\n",
     "        pass\n"),
    ("the button counts every running job as this project's", SCAN,
     "                   if tv.parse_job_id(wf_id, known_projects=names)[0] == proj.name)\n",
     "                   if True)\n"),
    ("the button reads a job without the registered names", SCAN,
     "                   if tv.parse_job_id(wf_id, known_projects=names)[0] == proj.name)\n",
     "                   if tv.parse_job_id(wf_id, known_projects=[])[0] == proj.name)\n"),
    ("the button's lane is one wider than it says", SCAN,
     "        slots = min(slots, max(0, lane - mine))\n",
     "        slots = min(slots, max(0, lane + 1 - mine))\n"),
    ("the button blames the floor when the lane held the queue", SCAN,
     "                if lane > 0 and mine >= lane else",
     "                if False else"),
]
