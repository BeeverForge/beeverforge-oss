"""#266: the OpenFactory 0.7 upgrade guide states what the code does.

Each row changes a fact in the code the guide restates, as a later change might, and the guide's
test must notice.
"""

TEST = "tests/test_the_upgrade_guide_says_what_the_code_does.py"

MUTATIONS = [
    ("the command alias is kept a release longer", "beeverforge/deprecations.py",
     '    Removal("openfactory-command", "1.1",', '    Removal("openfactory-command", "1.2",',
     TEST),

    ("the former Temporal names are dropped later", "beeverforge/deprecations.py",
     '    Removal("openfactory-temporal-names", "1.0",',
     '    Removal("openfactory-temporal-names", "1.1",', TEST),

    ("the compose file runs an image the guide does not name", "docker-compose.yml",
     "    image: ghcr.io/beeverforge/beeverforge-cli:${BEEVERFORGE_VERSION:-main}\n",
     "    image: ghcr.io/beeverforge/beeverforge-shell:${BEEVERFORGE_VERSION:-main}\n", TEST),

    ("the installer prints another way back", "install.sh",
     "BACK_TO_0_7='docker start $(docker ps -aq --filter "
     "label=com.docker.compose.project=openfactory)'\n",
     "BACK_TO_0_7='docker compose -p openfactory start'\n", TEST),

    ("the index no longer links the guide", "docs/README.md",
     "| [upgrading-from-openfactory.md](upgrading-from-openfactory.md) |", "| upgrading |", TEST),
]
