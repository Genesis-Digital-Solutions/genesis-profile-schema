"""v0.1.118 (15 Out 2026, I30) — `audio.minutes_action_items_queue`: das atas
de reunião aos pedidos.

O que protege: nenhum perfil muda de comportamento (vazio = desligado, nunca
None no blob); o valor é o NOME de uma fila e sobrevive ao round-trip; declara
a dependência da tool `transcribe_audio` e de `reviewQueues` para o editor
avisar; é interno como a fila da captura (I24) e o próprio `reviewQueues`; e
tem textos nas duas línguas."""
from genesis_profile_schema import exposure as exp
from genesis_profile_schema.client_profile_schema import ClientProfileSchema, ProfileAudio
from genesis_profile_schema.ui_text import text_for


def test_desligado_por_omissao():
    a = ProfileAudio()
    assert a.minutes_action_items_queue == ""
    prof = ClientProfileSchema.model_validate({"client_id": "x"})
    assert prof.model_dump()["audio"]["minutes_action_items_queue"] == ""


def test_round_trip_do_nome_da_fila():
    prof = ClientProfileSchema.model_validate(
        {"client_id": "x", "audio": {"minutes_action_items_queue": "tarefas"}})
    assert prof.audio.minutes_action_items_queue == "tarefas"
    assert prof.model_dump()["audio"]["minutes_action_items_queue"] == "tarefas"


def test_dependencias_declaradas():
    props = ClientProfileSchema.model_json_schema()["$defs"]["ProfileAudio"]["properties"]
    f = props["minutes_action_items_queue"]
    assert f["requires_tool"] == "transcribe_audio"
    assert f["requires_field"] == "reviewQueues"


def test_exposicao_e_textos():
    assert exp.exposure_of("audio.minutes_action_items_queue") == exp.INTERNAL
    assert exp.EXPOSURE["tools.config"] == exp.INTERNAL  # a fila da captura (I24)
    for loc in ("pt-PT", "en-GB"):
        t = text_for("audio.minutes_action_items_queue", loc)
        assert t and t.get("label") and len(t.get("help") or "") <= 240
