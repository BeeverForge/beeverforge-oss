"""The browser owns modal focus containment, Escape, and focus restoration."""

from html.parser import HTMLParser

from tests.test_a_refusal_is_not_an_answer import PAGE, run


def test_the_modal_container_is_a_native_dialog():
    class Modal(HTMLParser):
        tag = None

        def handle_starttag(self, tag, attrs):
            if dict(attrs).get("id") == "modal":
                self.tag = tag

    parser = Modal()
    parser.feed(PAGE)
    assert parser.tag == "dialog"


def test_opening_uses_modal_mode_and_updates_keep_the_dialog_named_and_focused():
    got = run("""
      modal('<h3>New project</h3><input id="name">');
      const first={open:el.open,shows,attributes:{...el.attributes}};
      document.activeElement={id:'name'};
      modal('<h3>New project</h3><input id="name">');
      const updated={shows,focused};closeModal();
      return {first,updated,open:el.open,closes};
    """, "modal", "closeModal", stubs="""
      let shows=0,closes=0,focused=0,_modalOpener='';
      const input={focus(){focused++}},other={focus(){focused+=100}},title={id:''};
      const el=nodes['#modal']={open:false,attributes:{},
        contains:x=>!!x,querySelector:q=>q==='h3'?title:other,querySelectorAll:()=>[input],
        setAttribute(k,v){this.attributes[k]=v},removeAttribute(k){delete this.attributes[k]},
        show(){this.open=true},showModal(){shows++;this.open=true},
        close(){closes++;this.open=false}};
      document.getElementById=id=>id==='name'?input:null;
    """)
    assert got == {
        "first": {"open": True, "shows": 1, "attributes": {"aria-labelledby": "modalTitle"}},
        "updated": {"shows": 1, "focused": 1}, "open": False, "closes": 1,
    }


def test_closing_after_the_trigger_was_redrawn_returns_focus_to_its_replacement():
    got = run("""
      document.activeElement={id:'registerProject'};
      modal('<h3>New project</h3>');closeModal();modalClosed();
      return {returned,html:el.innerHTML,kind:el.dataset.kind,opener:_modalOpener};
    """, "modal", "closeModal", "modalClosed", stubs="""
      let _modalOpener='';const returned=[];
      const el=nodes['#modal']={open:false,dataset:{kind:'new'},contains:()=>false,
        querySelector:()=>({id:''}),setAttribute(){},
        showModal(){this.open=true},close(){this.open=false}};
      document.getElementById=id=>({focus:()=>returned.push(id)});
    """)
    assert got == {"returned": ["registerProject"], "html": "", "kind": "", "opener": ""}


def test_a_live_rerender_keeps_focus_on_the_control_the_person_chose():
    got = run("""
      modal(html);document.activeElement=renders[0][1];
      modal(html);return focused;
    """, "modal", stubs="""
      let _modalOpener='';const renders=[],focused=[];const html='<button>A</button><button>B</button>';
      const el=nodes['#modal']={open:false,contains:x=>renders.some(r=>r.includes(x)),
        querySelector:q=>q==='h3'?null:renders.at(-1)[0],querySelectorAll:()=>renders.at(-1),
        removeAttribute(){},setAttribute(){},showModal(){this.open=true},
        set innerHTML(v){const n=renders.length;
          renders.push(['A','B'].map(k=>({id:'',focus(){focused.push(k+n)}})))}};
      document.getElementById=()=>null;
    """)
    assert got == ["B1"]


def test_the_browsers_own_close_restores_focus_and_empties_the_dialog():
    from tests.test_a_refusal_is_not_an_answer import CODE

    wiring = "\n".join(line for line in CODE.splitlines() if line.startswith('$("#modal").addEventListener('))
    got = run(wiring + """
      document.activeElement={id:'registerProject'};modal('<h3>New project</h3>');
      el.open=false;for(const f of listeners.close||[])f();
      return {returned,html:el.innerHTML};
    """, "modal", "closeModal", "modalClosed", stubs="""
      let _modalOpener='';const returned=[],listeners={};
      const el=nodes['#modal']={open:false,dataset:{},contains:()=>false,querySelector:()=>null,
        setAttribute(){},removeAttribute(){},showModal(){this.open=true},close(){this.open=false},
        addEventListener(t,f){(listeners[t]=listeners[t]||[]).push(f)}};
      document.getElementById=id=>id==='registerProject'?{focus:()=>returned.push(id)}:null;
    """)
    assert got == {"returned": ["registerProject"], "html": ""}


def test_the_new_project_trigger_carries_the_id_focus_returns_to():
    from tests.test_a_refusal_is_not_an_answer import _function

    class Buttons(HTMLParser):
        def __init__(self):
            super().__init__()
            self.found = []

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "button" and a.get("onclick") == "openRegister()":
                self.found.append(a.get("id"))

    parser = Buttons()
    parser.feed(_function("renderIndex"))
    assert parser.found == ["registerProject"]


def test_a_dialog_opened_in_the_same_task_as_a_close_survives_the_late_close_event():
    got = run("""
      modal('<h3>One</h3>');closeModal();modal('<h3>Two</h3>');
      modalClosed();return {html:el.innerHTML,open:el.open};
    """, "modal", "closeModal", "modalClosed", stubs="""
      let _modalOpener='';
      const el=nodes['#modal']={open:false,dataset:{},contains:()=>false,querySelector:()=>null,
        setAttribute(){},removeAttribute(){},showModal(){this.open=true},close(){this.open=false}};
      document.getElementById=()=>null;
    """)
    assert got == {"html": '<div class="mbox"><h3>Two</h3></div>', "open": True}
