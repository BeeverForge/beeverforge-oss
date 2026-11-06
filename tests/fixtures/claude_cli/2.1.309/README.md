# What `claude` 2.1.309 printed on stdout, measured

The pinned CLI (`docker/worker.Dockerfile`, `@anthropic-ai/claude-code@2.1.309`, #436; published to npm 2026-10-22, past the two weeks a release is left to settle before it is adopted), taken from
`npm pack @anthropic-ai/claude-code-linux-x64@2.1.309` (sha256 of the tarball
`e960c4437f6f99648437784db43e04ad5f12711aecd710864f96876f94c2fc1a`, `package/claude`) and run on
2026-11-06 with `echo ok |` on stdin, from a fresh empty directory, under
`env -i HOME=$(mktemp -d) PATH=/usr/bin:/bin`: no credential, no configuration of this machine.
The recipe is the one `../2.1.219/README.md` used.

| file | argv after `claude` | exit |
|---|---|---|
| `json.stdout.jsonl` | `-p --output-format json --permission-mode plan --strict-mcp-config --mcp-config {"mcpServers":{}}` | 1 |
| `stream-json-verbose.stdout.jsonl` | `-p --output-format stream-json --verbose --permission-mode plan --strict-mcp-config --mcp-config {"mcpServers":{}}` | 1 |
| (no stdout) | `-p --output-format stream-json --permission-mode plan …` (no `--verbose`) | 1, stderr `Error: When using --print, --output-format=stream-json requires --verbose` |

Verbatim, key order kept, except the values that named the machine the run was taken on:
`cwd` and `original_cwd` → `"/work"`, `memory_paths.auto` and `messaging_socket_path` →
`"<stripped>"`.

Against 2.1.219, the json envelope keeps every key and adds `subagent_stats`, `safety_stops`,
`queued_turn_count` and `result_index`. It is still the same object as the stream's last line
(`type: "result"`, `is_error: true`, `result: "Not logged in · Please run /login"`), and the stream
still opens with `{"type":"system","subtype":"init",…}`, which has no `result`.

No credentialed run was recorded here, so neither file holds a `rate_limit_event`; its shape is
the one `tests/claude_cli_output.py` builds, as for 2.1.219.

## The read-only flags still restrict (measured the same day)

`docker/base-python.Dockerfile` asks for this before any bump. Each run below used the argv
`ClaudeCodeAdapter._cli` builds (`-p <prompt> --output-format stream-json --verbose
--permission-mode acceptEdits --strict-mcp-config --mcp-config {"mcpServers":{}} --max-turns 4
--model=haiku`, plus the flags in the table), with a credential, from a fresh empty directory. The
prompt asked the model to create `wrote.txt` with any tool it had.

| flags | tools the `init` event listed | `wrote.txt` |
|---|---|---|
| `--tools Read,Grep,Glob --disallowedTools Edit,Write,Bash,NotebookEdit,Task --allowedTools Read,Grep,Glob` (a read-only role) | `Glob`, `Grep`, `Read` | absent |
| `--tools Read,Grep,Glob --allowedTools Read,Grep,Glob` | `Glob`, `Grep`, `Read` | absent |
| `--disallowedTools Edit,Write,Bash,NotebookEdit,Task` | the deny list's five gone; 23 others left, among them `Workflow`, `SendMessage`, `RemoteTrigger`, `CronCreate` | absent |
| `--allowedTools Write,Bash` (the control) | 25, `Write` and `Bash` among them | present |

So `--tools` alone still restricts, and so does the deny list for the tools it names. On this
version the deny list no longer names every tool that can act, so the available set (`--tools`)
is what keeps a role read-only; every read-only role passes both.
