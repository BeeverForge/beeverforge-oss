# Upgrading from OpenFactory 0.7

BeeverForge is OpenFactory under a new name. A deployment running OpenFactory 0.7 upgrades in
place: its data, its settings, its projects and the cards it has in flight carry over, and every
name 0.7 used keeps working for a while. This page says what changes, what keeps working and until
when, and the steps for each kind of deployment.

## What keeps working, and until when

Each former name below is still read. `beeverforge doctor <project>` lists every one a deployment
still uses on its `former_names` line, each with the name to use instead.

| OpenFactory 0.7 | BeeverForge | Read until |
|---|---|---|
| `OPENFACTORY_*` variables | `BEEVERFORGE_*`, the same suffix | 1.1 |
| `~/.openfactory/` (registry, approver store, resume handles, gate key, board database, box proofs, `env`) | `~/.beeverforge/` | no end set |
| a repository's `.openfactory/` folder | `.beeverforge/` | no end set |
| journals in `.openfactory-logs/` beside a checkout | `.beeverforge-logs/` | no end set |
| add-on entry points under `openfactory.adapters` | `beeverforge.adapters` | 1.1 |
| `import openfactory`, `from openfactory.<module> import …` | `beeverforge`, `beeverforge.<module>` | 1.1 |
| the `openfactory` command | `beeverforge` | 1.1 |
| the Temporal task queue `openfactory-jobs` and `openfactory-*` workflow ids | BeeverForge's queue and ids | 1.0 |

What changes outright, with nothing to rename by hand:

- **The images.** `ghcr.io/open-factory-digital/openfactory-{base,sandbox,cli,worker}` are now
  `ghcr.io/beeverforge/beeverforge-{base,sandbox,cli,worker}`, pinned by `BEEVERFORGE_VERSION`
  instead of `OPENFACTORY_VERSION`. The installer writes the new names.
- **The compose stack.** Its project is `beeverforge`, not `openfactory`, so its volumes have new
  names, and the state directory inside the containers is `/var/lib/beeverforge`. The installer
  copies 0.7's volumes into the new ones (below).
- **The schedules.** At boot, once it has created its own schedules, the BeeverForge worker deletes
  0.7's (`openfactory-poller` and the per-project ones), so they do not fire twice. The log names
  each one it deleted. A poller paused in 0.7 is not carried over: `beeverforge-poller` starts
  running, so pause it again if you need it paused. [configuration.md](configuration.md) has the
  details of the Temporal side.

## A compose deployment: re-run the installer over it

This is the deployment `install.sh` set up: a directory holding `docker-compose.yml` and
`.env.compose`.

1. **Keep a copy of 0.7's `.env.compose`.** The upgrade rewrites it under BeeverForge's names, and
   only a file holding 0.7's rows tells the installer there is 0.7 data to carry. The copy is what
   lets you upgrade again after going back (below):

   ```sh
   cp -p <the 0.7 directory>/.env.compose <the 0.7 directory>/.env.compose.0.7
   ```

2. **Run the installer over the same directory, with `--force`.**

   ```sh
   curl -fsSL https://beeverforge.com/install.sh | sh -s -- --dir <the 0.7 directory> --force
   ```

   At a terminal, `init` asks its questions as on a fresh install. Unattended, pass its answers
   after a second `--`, as for a fresh install.

3. **What it does, in order.** Because `.env.compose` holds `OPENFACTORY_*` rows, the installer runs
   `beeverforge upgrade-from-openfactory` before it rewrites the file:

   - it stops 0.7's containers, without removing them;
   - it copies 0.7's Temporal database, state, repository cache and journals into BeeverForge's
     volumes, keeping owners and modes. The harness toolbox is not copied: the new image fills it
     with its own harness CLI;
   - `init --force` rewrites `.env.compose` under the `BEEVERFORGE_*` names, keeping every value,
     credentials included. A `BEEVERFORGE_*` value the file already holds wins. 0.7's work
     directory is kept;
   - the new stack starts on the copied volumes.

   A volume a BeeverForge stack already keeps data in is never written over: the installer stops and
   names it. Running the installer again copies nothing once every copy has finished. If a carry
   stopped part-way, the next run empties and copies every volume again from 0.7's, so all of them
   hold one moment: 0.7's state when that run stopped it, including any work 0.7 did after you
   started it again meanwhile.

4. **Check it.** `beeverforge project list` shows 0.7's projects. A card 0.7 had in flight is picked
   up by the BeeverForge worker where it stood, and a parked one resumes as before.
   `beeverforge doctor <project>` lists the former names still in use.

5. **Remove 0.7's containers and volumes once BeeverForge runs as it should.** The carry step
   prints both commands as it finishes, naming each volume, and the installer's last lines point
   back to them. Until you run them, nothing of 0.7's is deleted.

### Going back

0.7's volumes are only read, and its containers are only stopped. To go back, stop BeeverForge's
stack (`docker compose --env-file .env.compose down` in its directory, which keeps its volumes) and
start 0.7's again:

```sh
docker start $(docker ps -aq --filter label=com.docker.compose.project=openfactory)
```

If the upgrade stops after 0.7's containers were stopped, the installer prints this same command.
0.7's containers keep the environment they were created with, so they start without its old
`.env.compose`.

**Going back is a decision to stay on 0.7.** Work done on BeeverForge after the upgrade stays in
BeeverForge's volumes and does not reach 0.7. Work done on 0.7 after going back does not reach
BeeverForge either: `.env.compose` now holds BeeverForge's names, so a later `--force` run carries
nothing, and BeeverForge would start again from the copy taken at the upgrade, without a word. To
upgrade again from 0.7's newest state:

1. remove BeeverForge's stack and volumes with the installer's `--uninstall`, saved as the
   [README](../README.md)'s "read it first" line does: `sh install.sh --uninstall --dir <the
   directory>`. It asks first. This deletes everything BeeverForge did since the upgrade;
2. put back the copy of 0.7's file: `cp -p .env.compose.0.7 .env.compose`;
3. run the upgrade from step 2 again.

### BeeverForge installed in another directory

The installer carries 0.7's data only when it runs over 0.7's own directory. A BeeverForge install
in another directory starts on empty volumes, and they are the very volumes the carry writes to:
BeeverForge's compose project is always `beeverforge`, whatever the directory, so two installs share
one set of volumes. Once that install has started, the carry refuses to write over them.

To carry 0.7's data instead, remove the other install with the installer's `--uninstall`
(`sh install.sh --uninstall --dir <its directory>`, the script saved as the README's "read it first"
line does). It asks first, and removes its volumes, and with
them every project, card and setting that install holds. Then run the upgrade above over the 0.7
directory.

## A one-machine deployment

This is a deployment run with `openfactory up` from a pip install, configured in
`~/.openfactory/env`.

1. **Replace the package.** Both packages install the `openfactory` command and the `openfactory`
   import name, so remove OpenFactory first, in the environment it was installed in, then install
   BeeverForge the way the [README](../README.md) does:

   ```sh
   pip uninstall openfactory
   git clone https://github.com/BeeverForge/beeverforge-oss.git && cd beeverforge-oss
   pip install -e '.[runtime]'
   ```

2. **Run `beeverforge up`.** On a machine that has `~/.openfactory/` and no `~/.beeverforge/`, every
   operator file is read and written in `~/.openfactory/`, including `env`, so the registry, the
   approvals and the settings are there. Journals stay in `.openfactory-logs/` beside each checkout
   until `.beeverforge-logs/` exists.

3. **Rename the directory when you are ready**, with nothing running. Once `~/.beeverforge/`
   exists, it is the one read and `~/.openfactory/` is not, so rename it rather than creating the
   new one beside it:

   ```sh
   test -e ~/.beeverforge || mv ~/.openfactory ~/.beeverforge
   ```

   If `~/.beeverforge/` already exists, this does nothing. `beeverforge doctor` then lists
   `~/.openfactory/` as stale on its `former_names` line: move what you need from it into
   `~/.beeverforge/` by hand, then remove it.

   **Then edit `~/.beeverforge/env`.** The `env` 0.7's `init` wrote names the registry, the board
   database, the repository cache and the metrics database by their full paths under
   `~/.openfactory/`, and a path written out is read as written. Change each `/.openfactory/` in the
   file to `/.beeverforge/`, and rename its `OPENFACTORY_*` rows while you are there. Otherwise the
   machine starts with no registry.

4. **Move each checkout's journals the same way**, from the directory that holds the checkout, so a
   new job does not start the new directory beside them:

   ```sh
   mkdir -p .beeverforge-logs && mv .openfactory-logs/<project> .beeverforge-logs/<project>
   ```

## The environment

Every `OPENFACTORY_<NAME>` a BeeverForge process finds in its environment is read as
`BEEVERFORGE_<NAME>` when that one is unset: from the shell, from `.env` and from
`~/.openfactory/env`. When both are set to different values, the `BEEVERFORGE_*` one is read and the
other is ignored, and the log says so. An empty `BEEVERFORGE_*` counts as set. Rename each variable
before 1.1, and remove a former one whose new name is already set: renaming it would overwrite the
value that is read.

**Do not start BeeverForge's compose file on a 0.7 `.env.compose`.** Compose fills several rows only
from their `BEEVERFORGE_*` names, and passes them empty when only the `OPENFACTORY_*` name is there.
An empty `BEEVERFORGE_*` wins, so the `OPENFACTORY_*` value, a credential among them, is dropped,
and only a line in the stack's logs says so. Let the installer rewrite the file (step 2 above).

## The repositories: `beeverforge migrate`

A repository that keeps `.openfactory/` is read there. `beeverforge migrate <project> --yes` proposes
the rename, one pull request per repository of the product, for a person to merge: it moves the
folder and rewrites the `.openfactory/` paths written inside it. Without `--yes` it names the
repositories it would open a pull request on and stops. Files outside the folder that mention
`.openfactory/` (a `.gitignore` line, a CI step) are named for you to update. See
[reference/cli.md](reference/cli.md).

A project registered by its checkout on this machine, as on a one-machine deployment, has no forge to
propose through, and `migrate` refuses it. Run `git mv .openfactory .beeverforge` in the checkout,
update the `.openfactory/` paths written inside the folder, and commit it yourself.

While a repository carries both folders, `.beeverforge/` is read and `.openfactory/` is not, and
`beeverforge doctor` says so on its `folder` line.

## Add-ons

An add-on that declares its rows under `openfactory.adapters` still loads, after the rows under
`beeverforge.adapters`, and `from openfactory.<module> import …` still resolves to the same modules.
Both stop at 1.1. Move the entry points to `beeverforge.adapters` and the imports to `beeverforge`;
[writing-an-addon.md](writing-an-addon.md) has the details.

## Scripts and cron lines

`openfactory <command>` runs `beeverforge <command>`, with the same output on stdout and the same exit
code, and one warning line on stderr. Replace it with `beeverforge` before 1.1.
