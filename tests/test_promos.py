from datetime import date

from radar.providers.promos import active_bonus, classify, parse_feed, relevant

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>Azul Fidelidade oferece até 120% de bônus nas transferências de pontos da Livelo</title>
<link>https://ex.com/a</link><pubDate>Fri, 25 Sep 2026 10:00:00 +0000</pubDate>
<description><![CDATA[<p>Promoção válida até domingo</p>]]></description></item>
<item><title>Passagens para Maceió saindo de Belém a partir de R$ 699</title>
<link>https://ex.com/b</link><pubDate>Sat, 26 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Smiles com 70% de bônus</title><link>https://ex.com/c</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Review do lounge em Doha</title><link>https://ex.com/d</link>
<pubDate>Sat, 26 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Livelo: 100% de bônus para Azul (antigo)</title><link>https://ex.com/e</link>
<pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_classify_transfer_bonus():
    kind, bonus, programs = classify("Ganhe até 80% de bônus ao transferir pontos do Inter Loop para a Azul")
    assert kind == "transferencia" and bonus == 80 and {"azul", "inter"} <= set(programs)


def test_inter_is_whole_word():
    _, _, programs = classify("Passagens internacionais em promoção")
    assert "inter" not in programs


def test_parse_and_filter_feed():
    promos = parse_feed(RSS, "ex.com")
    assert len(promos) == 5 and promos[0].published == date(2026, 9, 25)
    rel = relevant(promos, {"azul", "livelo"}, ["BEL", "Belém", "MCZ", "Maceió"], date(2026, 9, 27), 10)
    links = [p.link for p in rel]
    assert links == ["https://ex.com/a", "https://ex.com/b"]  # sem Smiles, review ou post antigo
    best = active_bonus(rel, ["livelo"])
    assert best and best.bonus_pct == 120


def test_transfer_out_of_azul_is_not_an_azul_promo():
    _, bonus, programs = classify("Últimas horas! Ganhe até 30% de bônus ao transferir pontos Azul para ALL Accor")
    assert bonus == 30 and "azul" not in programs
    _, _, programs = classify("Ganhe até 120% de bônus nas transferências da Livelo para o Azul Fidelidade")
    assert "azul" in programs
