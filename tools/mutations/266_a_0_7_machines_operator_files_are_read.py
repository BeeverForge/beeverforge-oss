"""#266: an OpenFactory 0.7 machine's operator files are read where 0.7 left them.

The defect was the rename's: only `~/.beeverforge/` and `.beeverforge-logs/` were read, so a 0.7
machine upgraded in place lost its registry, its `env` settings and its journals. Each row undoes
one part: the operator directory, its `env` file, certify's view of it, the redactor's word, and
the journals beside a checkout.
"""

NAMESPACE = "beeverforge/namespace.py"
CLI = "beeverforge/cli.py"
PACK = "beeverforge/certify/pack.py"
REDACT = "beeverforge/certify/redact.py"
PATHS = "beeverforge/paths.py"

TEST = "tests/test_a_0_7_machines_operator_files_are_read.py"
ONLY = TEST + "::test_a_machine_with_only_the_0_7_directory_is_read_there"
BOTH = TEST + "::test_the_current_directory_wins_and_the_0_7_one_is_then_stale"
ENV = TEST + "::test_the_0_7_env_file_is_loaded_by_every_command"
CERTIFY = TEST + "::test_certify_finds_the_0_7_env_file_and_names_it_without_its_path"
WORD = TEST + "::test_the_0_7_env_files_name_is_kept_by_the_redactor"
LOGS = TEST + "::test_a_0_7_checkouts_journals_are_read_where_0_7_wrote_them"
LOGS_WIN = TEST + "::test_once_the_current_journal_directory_exists_it_wins"

MUTATIONS = [
    ("THE FINDING: the operator directory is always `~/.beeverforge/`", NAMESPACE,
     "    return home / dir_in(home)\n", "    return home / DIR\n", ONLY),

    ("the 0.7 directory wins over the current one", NAMESPACE,
     "    return home / dir_in(home)\n",
     "    return home / (FORMER_DIR if (home / FORMER_DIR).is_dir() else DIR)\n", BOTH),

    ("both directories are not reported as stale", NAMESPACE,
     "    return stale_former_dir(Path.home())\n", "    return False\n", BOTH),

    ("the host env file is read only under `~/.beeverforge/`", CLI,
     "    load_dotenv(_host_env())\n", "    load_dotenv(Path(_HOST_ENV).expanduser())\n", ENV),

    ("certify looks for the env file only under `~/.beeverforge/`", PACK,
     '    host = namespace.operator_path("env")\n',
     '    host = Path("~/.beeverforge/env").expanduser()\n', CERTIFY),

    ("the redactor drops the 0.7 env file's name", REDACT,
     ' "~/.openfactory/env",\n', "\n", WORD),

    ("a 0.7 checkout's journals are not read", PATHS,
     "    if former.is_dir() and not current.is_dir():\n        return former\n", "", LOGS),

    ("the 0.7 journals win over the current ones", PATHS,
     "    if former.is_dir() and not current.is_dir():\n",
     "    if former.is_dir():\n", LOGS_WIN),
]
