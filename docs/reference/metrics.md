# The metrics rows: what a consumer counts, and by which field

Everything the factory measures lands as rows in one metrics store, told apart by `kind`. Two of
them are easy to count wrongly.

## `job` rows

A `job` row says what happened to a ticket's job. There are two sorts:

- **A per-attempt row** is written when an attempt of the job finishes: its state at that point, its
  wall clock, its cost, its knowledge arm. A job that is retried or resumed writes one per attempt.
- **An ending row** is written once, when the job ends: its final state (for example `merged` or
  `done`), its pull request and its platform stamp (`extra.platform`: the version and the build that
  ran). It is marked `extra.ending: true`. Pick it by that field, never by guessing from
  timestamps. It carries no wall clock and no cost: those are the attempts'.

Both drivers write it — the durable workflow's `record_outcome` and the attended driver (`beeverforge
run`, `beeverforge poll`) — through one function, `observability/job_record.record_job_ending`. It
holds whether the pull request was merged by the factory, by an operator's merge action or by a
person on the forge. A job that only parks (`on_hold`, `paused`: it can resume and will end again)
writes no ending row, so a job is counted when it ends and not when it is parked; `failed` is an
ending. It is written once per job, state and pull request: a replay writes nothing
again, and a job that ends `merged` and later `done` has one row for each.

To count the jobs that ended past the merge, count the ending rows whose `state` is in
`contracts/state.PAST_THE_MERGE`. To count attempts, skip the ending rows.

## `card_transition` rows

A card's record (ADR-0055). Two sorts share the kind:

- **A transition row** carries an `event` (`merged`, `closed`, `delivered`…), who, why and the facts.
  Its key is `card#<ref>#<seq>`.
- **An effect outcome** has no `event`: it records what applying one effect of a transition came to.
  Its key is `card#<ref>#<seq>#effect#<n>#<try>`.

Count transitions by key — the rows with no `#effect#` in it — never by counting rows of the kind.

A `merged` transition is keyed by the pull request (`handed_back.merged_event`), so it is recorded
once per pull request. It is recorded even when the forge closed the issue before the workflow saw
the merge, as a pull request merged by hand does: that row has `facts.late: true`, and writes
nothing to the card, which the forge already did.
