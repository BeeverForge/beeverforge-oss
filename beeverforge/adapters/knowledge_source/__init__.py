"""The knowledge-source axis — a source of knowledge the product role reads beside its own (ADR-0052
D15: the product's repositories and its context repository are in the core; any other source is an
add-on).

`base.py` is the port, `registry.py` the rows and the one line of configuration that switches one
on, `service.py` the row that asks BeeverForge Knowledge, an optional separate service, over HTTP.
The core is born with the axis OFF (`none`): a deployment that says nothing reads exactly what it
read before the axis existed, and asks nobody anything. What a row answers reaches the role as one
file of its facts pack (`product/knowledge_answers.py`, ADR-0041), never as a tool it calls.
"""
