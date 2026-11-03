"""#209, proven by breaking it — the cost dashboard's selector lists only keys of the kinds it reads.

The people store keeps its `person` and invitation rows under `_deployment_`. `dashboard` listed
every row's key, so the selector read `['_deployment_', 'books']` and the dashboard opened on
`_deployment_`, showing nothing spent beside the project that did.

ONE CLAIM: the selector, and so the default view, holds only keys with an `agent_run` or `job`
row (`DASHBOARD_KINDS`).

The guard is `tests/test_the_cost_dashboard_lists_only_what_it_reads.py`.
"""

TEST = "tests/test_the_cost_dashboard_lists_only_what_it_reads.py"

VIEW = "beeverforge/api/metrics_view.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: the selector lists every row's key, so `_deployment_` is the default view",
     VIEW,
     '                       if (r.get("pk") or r.get("project"))\n'
     '                       and r.get("kind") in DASHBOARD_KINDS})\n',
     '                       if (r.get("pk") or r.get("project"))})\n'),

    ("a key holding only `job` rows drops out of the selector", VIEW,
     'DASHBOARD_KINDS = ("agent_run", "job")\n',
     'DASHBOARD_KINDS = ("agent_run",)\n'),

    ("a key holding only `agent_run` rows drops out of the selector", VIEW,
     'DASHBOARD_KINDS = ("agent_run", "job")\n',
     'DASHBOARD_KINDS = ("job",)\n'),

    ("the default view is not the first listed project", VIEW,
     '    project = project or (projects[0] if projects else "")\n',
     '    project = project or (projects[-1] if projects else "")\n'),
]
