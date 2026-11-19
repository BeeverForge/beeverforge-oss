"""A test that walks the repository's tree carries `whole_tree`, proven by taking the label off.

Run:  .venv/bin/python tools/mutate.py tools/mutations/545_a_whole_tree_test_carries_its_marker.py

Each row breaks one end of the label and the guard must go red:

  1. A module whose tests all walk the tree loses its `pytestmark`: a tree-walking test is
     unmarked, and the guard names the file and the call.
  2. A test that walks the tree loses its decorator: the same, for the other way to carry it.
  3. A test that walks nothing gains the marker: a small box would drop it for nothing.
  4. The detector stops seeing `rglob`: every marked test of that shape now "walks nothing".
"""

TEST = "tests/test_a_whole_tree_test_carries_its_marker.py"
UNMARKED = TEST + "::test_a_test_that_walks_the_tree_carries_the_marker"
UNNEEDED = TEST + "::test_a_test_that_carries_the_marker_walks_the_tree"

MUTATIONS = [
    ("a module of tree-walking tests drops its module-level marker",
     "tests/test_the_app_permission_table_has_one_home.py",
     "pytestmark = pytest.mark.whole_tree\n", "", UNMARKED),
    ("a tree-walking test drops its decorator",
     "tests/test_board_read_cost.py",
     "@pytest.mark.whole_tree\ndef test_only_the_documented_fallback_may_use_the_per_card_CLI(",
     "def test_only_the_documented_fallback_may_use_the_per_card_CLI(", UNMARKED),
    ("a test that walks nothing is marked",
     "tests/test_board_read_cost.py",
     "def test_the_pickup_queue_reads_through_the_cheap_path(",
     "@pytest.mark.whole_tree\ndef test_the_pickup_queue_reads_through_the_cheap_path(", UNNEEDED),
    ("the detector no longer sees an rglob",
     "tests/whole_tree_walks.py",
     'if isinstance(func, ast.Attribute) and func.attr == "rglob":',
     'if isinstance(func, ast.Attribute) and func.attr == "rglob_is_not_seen":', UNNEEDED),
]
