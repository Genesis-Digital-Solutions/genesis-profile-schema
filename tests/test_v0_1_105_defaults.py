"""v0.1.105 (13 Out 2026): voz sem fila por omissão; anónimos a 180 dias."""
from genesis_profile_schema.client_profile_schema import ClientProfileSchema


def test_voice_queue_default_is_no_queue():
    assert ClientProfileSchema().voice.queue == ""
    # um perfil gravado com o valor explícito mantém-no
    assert ClientProfileSchema.model_validate({"voice": {"queue": "tickets"}}).voice.queue == "tickets"


def test_anonymous_conversations_default_is_180_days():
    assert ClientProfileSchema().compliance.retention.conversations_anonymous_days == 180
    p = ClientProfileSchema.model_validate(
        {"compliance": {"retention": {"conversations_anonymous_days": 90}}})
    assert p.compliance.retention.conversations_anonymous_days == 90
