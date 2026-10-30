"""#112: an image, a GitHub alert and math the agent writes stay text in the quoted account.

Each reverse drops one character from what `_MARKUP` escapes: without `!`, an `![…](…)` badge
renders as an image and a first line `[!CAUTION]` as an alert inside the platform's section;
without `$`, `$…$` reaches GitHub's math renderer, which reads it after resolving the escapes.
"""

TEST = "tests/test_an_image_an_alert_and_math_the_agent_writes_stay_text.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("`!` is not escaped: an image badge and a `[!CAUTION]` alert render inside the quote", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~!$])")', '_MARKUP = re.compile(r"([\\\\`<&*_~$])")'),

    ("`$` is not escaped: math the agent writes is typeset inside the quote", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~!$])")', '_MARKUP = re.compile(r"([\\\\`<&*_~!])")'),
]
