"""The panel reads the job list on every visit and discards stale replies."""

import re

import pytest

from tests.test_a_refusal_is_not_an_answer import CODE, run

PAGE_LOGS = re.search(r"^let _logs=.*$", CODE, re.M).group(0)
STUBS = PAGE_LOGS + """
const lists=[];const details=[];
nodes['#app']=node();
function paintLogList(){lists.push({rows:_logs.rows,error:_logs.error})}
function loadJobLog(project,issue){details.push({project,issue})}
"""


def logs(scenario):
    return run(scenario, "curLogs", "renderLogsPage", stubs=STUBS)


def test_returning_to_logs_shows_a_run_written_after_the_first_visit():
    got = logs("""
      location.pathname='/logs/acme';
      routes={'/api/jobs':[{status:200,body:[{issue:'1'}]},
                           {status:200,body:[{issue:'2'},{issue:'1'}]}]};
      await renderLogsPage();location.pathname='/p/acme';location.pathname='/logs/acme';
      await renderLogsPage();return {calls,lists};
    """)
    assert got["calls"] == ["GET /api/jobs", "GET /api/jobs"]
    assert got["lists"] == [
        {"rows": [{"issue": "1"}], "error": ""},
        {"rows": [{"issue": "2"}, {"issue": "1"}], "error": ""},
    ]


def test_a_failed_visit_can_be_read_successfully_on_the_next_visit():
    got = logs("""
      location.pathname='/logs';routes={'/api/jobs':[{network:true},
                           {status:200,body:[{issue:'1'}]}]};
      await renderLogsPage();await renderLogsPage();return lists;
    """)
    assert got[0]["rows"] == [] and got[0]["error"]
    assert got[1] == {"rows": [{"issue": "1"}], "error": ""}


@pytest.mark.parametrize("first_issue", ["1", "2"])
def test_an_older_visit_cannot_overwrite_the_current_visit(first_issue):
    got = logs("""
      const held=[];api=()=>new Promise(resolve=>held.push(resolve));
      location.pathname='/logs/acme/FIRST';const first=renderLogsPage();
      location.pathname='/logs/acme/2';const second=renderLogsPage();
      held[1]([{issue:'2'}]);await second;held[0]([{issue:'1'}]);await first;
      return {lists,details,rows:_logs.rows};
    """.replace("FIRST", first_issue))
    assert got == {"lists": [{"rows": [{"issue": "2"}], "error": ""}],
                   "details": [{"project": "acme", "issue": "2"}],
                   "rows": [{"issue": "2"}]}


def test_a_reply_after_leaving_logs_does_not_paint_the_new_page():
    got = logs("""
      let finish;api=()=>new Promise(resolve=>finish=resolve);
      location.pathname='/logs/acme/1';const first=renderLogsPage();
      location.pathname='/p/acme';finish([{issue:'1'}]);await first;
      return {lists,details};
    """)
    assert got == {"lists": [], "details": []}


def test_returning_to_a_selected_run_reads_its_log_again():
    got = run("""
      location.pathname='/logs/acme/1';
      routes={'/api/jobs':[{status:200,body:[{project:'acme',issue:'1'}]}],
              '/api/jobs/acme/1/events':[{status:200,body:[{message:'a'}]},
                                         {status:200,body:[{message:'a'},{message:'b'}]}]};
      await renderLogsPage();await settle();location.pathname='/p/acme';
      location.pathname='/logs/acme/1';await renderLogsPage();await settle();
      return {calls,shown};
    """, "curLogs", "renderLogsPage", "loadJobLog", stubs=PAGE_LOGS + """
      nodes['#app']=node();nodes['#logdetail']=node();const shown=[];
      function paintLogList(){}
      function paintJobLog(project,issue){shown.push((_logs.events||[]).map(e=>e.message))}
    """)
    assert got["calls"] == ["GET /api/jobs", "GET /api/jobs/acme/1/events",
                            "GET /api/jobs", "GET /api/jobs/acme/1/events"]
    assert got["shown"] == [["a"], ["a", "b"]]
