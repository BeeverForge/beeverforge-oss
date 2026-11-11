"""#519: a workspace made in the shared work dir lets the box daemon's ACL principal in.

The reverses matter as much as the forwards: a workspace opened to "other" lets every uid on the
host into a client's checkout, and one opened without a shared work dir opens the system temp
directory's clone to the core's group for nothing.
"""

TEST = "tests/test_a_box_running_as_another_uid_can_enter_its_workspace.py"
BOX = "beeverforge/adapters/sandbox/container.py"

MUTATIONS = [
    ("the workspace stays 0700 — the inherited ACL entry is masked and the box exits 126", BOX,
     "            os.chmod(host_clone, _SHARED_WORKSPACE_MODE | (host_clone.stat().st_mode & 0o2000))\n",
     "            pass\n"),

    ("…and the reverse: the workspace is opened to every uid on the host", BOX,
     "_SHARED_WORKSPACE_MODE = 0o770\n", "_SHARED_WORKSPACE_MODE = 0o777\n"),

    ("the group may read but not enter — the box still cannot chdir into /workspace", BOX,
     "_SHARED_WORKSPACE_MODE = 0o770\n", "_SHARED_WORKSPACE_MODE = 0o760\n"),

    ("the workspace is opened even with no shared work dir", BOX,
     "        if work_dir:\n            # THE BOX MAY NOT BE THE CORE'S UID (#519).",
     "        if True:\n            # THE BOX MAY NOT BE THE CORE'S UID (#519)."),
]
