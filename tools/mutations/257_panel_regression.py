"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_revisiting_logs_reads_new_runs.py'
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ('logs reuse the first cached list forever', PANEL,
     'const r=await api("/api/jobs");',
     'const r=_logs.rows||await api("/api/jobs");'),
    ('an older visit overwrites a newer visit', PANEL,
     'if(request!==_logs.request || location.pathname!==path)return;',
     'if(location.pathname!==path)return;'),
    ('a response paints after leaving logs', PANEL,
     'if(request!==_logs.request || location.pathname!==path)return;',
     'if(request!==_logs.request)return;'),
    ('the selected run remains cached between visits', PANEL,
     '_logs.rows=rows;_logs.error=error;_logs.loaded="";',
     '_logs.rows=rows;_logs.error=error;'),
    ('the request counter is not initialized', PANEL,
     ',all:false,request:0}', ',all:false}'),
    ('a stale response overwrites stored rows', PANEL,
     '  if(request!==_logs.request || location.pathname!==path)return;\n'
     '  _logs.rows=rows;_logs.error=error;_logs.loaded="";',
     '  _logs.rows=rows;_logs.error=error;_logs.loaded="";\n'
     '  if(request!==_logs.request || location.pathname!==path)return;'),
]
