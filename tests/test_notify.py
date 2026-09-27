from radar import notify
from radar.engine import PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_URGENT, Alert


def alerts(n, priority=PRIORITY_NORMAL):
    return [Alert(f"k{i}", f"Alerta {i}", "texto", f"https://ex.com/{i}", priority) for i in range(n)]


def test_messages_are_ordered_and_have_click_link():
    al = [Alert("a", "promo", "t", "https://ex.com/a", PRIORITY_LOW),
          Alert("b", "🎯 Maceió abaixo do alvo", "R$ 800", "https://ex.com/b", PRIORITY_URGENT)]
    msgs = notify.build_messages(al, "meu-topico", "https://painel")
    assert [m["title"] for m in msgs] == ["🎯 Maceió abaixo do alvo", "promo"]
    assert msgs[0] == {"topic": "meu-topico", "title": "🎯 Maceió abaixo do alvo", "message": "R$ 800",
                       "priority": PRIORITY_URGENT, "click": "https://ex.com/b",
                       "actions": [{"action": "view", "label": "Ver painel", "url": "https://painel"}]}


def test_many_alerts_are_summarized():
    msgs = notify.build_messages(alerts(8), "t")
    assert len(msgs) == notify.MAX_INDIVIDUAL + 1
    assert msgs[-1]["title"] == "E mais 3 alerta(s) do radar"
    assert "actions" not in msgs[0]


def test_send_push_posts_json(monkeypatch):
    posted = []

    class Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(notify.requests, "post", lambda url, json, timeout: posted.append((url, json)) or Resp())
    assert notify.send_push(alerts(2), topic="t", server="https://ntfy.sh/") == 2
    assert posted[0][0] == "https://ntfy.sh" and posted[0][1]["topic"] == "t"


def test_send_push_without_topic_only_prints(monkeypatch, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send_push(alerts(1)) == 0
    assert "Alerta 0" in capsys.readouterr().out
