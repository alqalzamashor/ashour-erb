"""حقل البحث (SearchableDropdown): أول نتيجة متلوّنة، الأسهم بتنقل اللون، Enter بيختار المتلوّن، والمعالجات المتوازية ما بتسيبش صندوق فاضي."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from flet.controls.context import _context_page

from erp_app import theme

OPTS = [("1", "111001 - مبانى"), ("2", "111002 - مجمع اهلاك"), ("3", "111003 - اراضى"), ("4", "212000 - قرض")]


def _sd(**kw):
    pg = MagicMock()
    pg.on_keyboard_event = None
    _context_page.set(pg)
    sd = theme.SearchableDropdown(label="", options=OPTS, page=pg, **kw)
    return sd, pg


def _type(sd, text):
    sd.text_field.value = text
    sd._on_type(None)


def _key(sd, k):
    asyncio.run(sd._on_key(SimpleNamespace(key=k)))


def _bg(sd):
    return [c.bgcolor for c in sd._row_ctls]


def test_first_result_is_highlighted_and_arrows_move_it_with_wraparound():
    sd, _ = _sd()
    _type(sd, "111")
    assert sd.suggestions_container.visible and len(sd._row_ctls) == 3
    assert _bg(sd)[0] is not None and _bg(sd)[1] is None
    _key(sd, "Arrow Down"); assert _bg(sd)[1] is not None and _bg(sd)[0] is None
    _key(sd, "Arrow Down"); _key(sd, "Arrow Down"); assert _bg(sd)[0] is not None          # لفّ للأول
    _key(sd, "Arrow Up"); assert _bg(sd)[2] is not None                                    # ولفّ لآخر واحد
    assert sd._row_ctls[2].content.weight is not None and sd._row_ctls[0].content.weight is None


def test_enter_selects_highlighted_row_not_exact_code_when_user_navigated():
    sd, _ = _sd()
    _type(sd, "111")
    _key(sd, "Arrow Down"); _key(sd, "Arrow Down")
    sd._on_submit(None)
    assert sd.value == "3"
    sd2, _ = _sd()
    _type(sd2, "212000")                      # من غير أسهم: Enter بيختار المطابق/الأول
    sd2._on_submit(None)
    assert sd2.value == "4"


def test_new_search_resets_highlight_and_escape_closes():
    sd, _ = _sd()
    _type(sd, "111"); _key(sd, "Arrow Down")
    _type(sd, "1110")
    assert sd._hi == 0 and not sd._hi_moved
    _key(sd, "Escape")
    assert sd.suggestions_container.visible is False


def test_keyboard_handler_installed_on_focus_chains_and_is_restored_on_blur():
    sd, pg = _sd()
    seen = []
    pg.on_keyboard_event = lambda e: seen.append(e.key)
    sd._on_focus(None)
    assert pg.on_keyboard_event == sd._on_key
    _key(sd, "k")                              # مفيش اقتراحات ظاهرة: بيعدّي للمعالج القديم (Ctrl+K وغيره)
    assert seen == ["k"]
    sd._on_blur(None)
    assert pg.on_keyboard_event is not sd._on_key and callable(pg.on_keyboard_event)


def test_parallel_typing_never_leaves_stale_or_empty_results():
    sd, _ = _sd()
    errs = []

    def worker(txt):
        try:
            for _ in range(30):
                sd.text_field.value = txt
                sd._on_type(None)
        except Exception as ex:      # noqa: BLE001
            errs.append(ex)
    ts = [threading.Thread(target=worker, args=(t,)) for t in ("111", "212", "1110")]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs
    _type(sd, "212")
    assert [t for _, t in sd._matches] == ["212000 - قرض"] and sd.suggestions_container.visible
