"""A review run that ended in error is not a verdict, and a limit is a pause (#131).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/131_a_review_that_ended_in_error_is_not_a_verdict.py

The claims, each a row:

  * `is_error: true` (row 1) or a non-zero exit (row 2) on the result event is a failed run, and
    its text is never parsed as a verdict: an approving `result` on an error envelope answered
    approved / 88 before;
  * a failed run is classified by the executor's own `_detect_pause` (row 3), only when it failed
    (row 4: a successful review that talks about a 429 is a verdict), and a stream that died with
    no result event by `_pause_from` (row 5);
  * what the failed run cost is still charged (row 6);
  * the job pauses on a review pause, at the first review (row 7) and at the re-review after a
    review-repair (row 8);
  * `HarnessReviewer` carries its agent's pause onto the review (row 9);
  * the pull request (row 10) and the first round's review stage (row 11) read a review that did
    not complete, or paused, from its fields — the "did not complete" sentence holds neither of
    the phrases they matched on before — and the reviewer sets that field (row 12).
"""

TEST = "tests/test_the_review_is_read_from_the_last_result_event_of_its_stream.py"
JOB = "tests/test_a_review_that_hits_the_usage_limit_pauses_the_job.py"
REVIEWER = "beeverforge/adapters/reviewer/claude_code.py"
HARNESS = "beeverforge/adapters/reviewer/harness.py"
MACHINE = "beeverforge/orchestrator/machine.py"
CONTRACT = "beeverforge/contracts/review.py"

MUTATIONS = [
    ("THE DEFECT: an error result event is read as a verdict at exit 0", REVIEWER,
     'if envelope.get("is_error") is True or rc != 0:', "if rc != 0:"),
    ("a run that exited non-zero is read as a verdict when its event says no error", REVIEWER,
     'if envelope.get("is_error") is True or rc != 0:', 'if envelope.get("is_error") is True:'),
    ("the executor's pause detection is ignored: a usage limit is a did-not-complete rejection",
     REVIEWER,
     "        if reason:\n            review = self._paused(reason, retry)",
     "        if False:\n            review = self._paused(reason, retry)"),
    ("every result event is classified for a pause, a successful review's prose included",
     REVIEWER, "            if envelope.get(\"is_error\") is True or rc != 0:\n"
     "                return self._did_not_complete(rc, envelope)\n",
     "            if (envelope.get(\"is_error\") is True or rc != 0\n"
     "                    or _detect_pause(str(envelope.get(\"result\", \"\")))[0]):\n"
     "                return self._did_not_complete(rc, envelope)\n"),
    ("a stream that died on a rejected rate_limit_event is not read for a pause", REVIEWER,
     "reason, retry = _pause_from(out) if rc != 0 else (None, None)",
     "reason, retry = None, None"),
    ("the failed review's cost is lost", REVIEWER,
     '"cost_usd": event.get("total_cost_usd"),', '"cost_usd": None,'),
    ("the first review's pause is recorded as a rejection and the job opens a pull request",
     MACHINE,
     "                if result.review.pause_reason:\n"
     "                    return self._paused(ticket, result.review.pause_reason,\n",
     "                if False:\n"
     "                    return self._paused(ticket, result.review.pause_reason,\n", JOB),
    ("the re-review's pause is recorded as a rejection", MACHINE,
     "                    if result.review.pause_reason:  # the re-review's limit too (#131)",
     "                    if False:", JOB),
    ("the harness reviewer drops its agent's pause", HARNESS,
     '                pause_reason=getattr(res, "pause_reason", None),\n', "", JOB),
    ("the pull request heads a review that did not complete as a rejection", CONTRACT,
     'if getattr(review, "pause_reason", None) or getattr(review, "did_not_complete", False):',
     "if False:", "tests/test_an_unread_review_is_not_a_rejection.py"),
    ("THE REGRESSION ONBOARDING WOULD TAKE: the first round's review stage reads only the old "
     "phrases, and a review that did not complete is the reviewer's rejection of the diff",
     "beeverforge/onboarding/firstrun.py", "        unread = not_a_verdict(result)\n",
     "        unread = (result.score == 0 and not result.findings\n"
     "                  and (\"could not be parsed\" in summary or \"never ran\" in summary))\n",
     "tests/test_onboarding_firstrun.py"),
    ("the reviewer does not mark a failed run as did-not-complete", REVIEWER,
     'decision="rejected", score=0, did_not_complete=True,', 'decision="rejected", score=0,'),
    ("a review that says it never ran in capitals is headed as a rejection of the diff", CONTRACT,
     '    summary = (getattr(review, "summary", "") or "").lower()\n',
     '    summary = getattr(review, "summary", "") or ""\n',
     "tests/test_an_unread_review_is_not_a_rejection.py"),
]
