"""
tests/test_contact_rules.py — regras de ação dos contactos do agente (`contact.ask`/`contact.tell`, v0.1.174).

O QUE ESTES TESTES PROTEGEM:
  • `contact` é o servidor reservado das ferramentas do agente: nunca «servidor desconhecido»;
  • «permitir» sem fila e aprovadores avisa: o 1.º contacto com alguém de fora vai sempre a aprovação (D1) e não sai;
  • com fila e aprovadores, ou a bloquear, ou só a registar, não avisa;
  • «aprovar» continua a exigir fila e aprovadores (erro), como nas outras ações.
"""

from genesis_profile_schema import action_rules as ar

QUEUES = {"aprov": {"states": ["pending", "approved", "rejected"],
                    "actions": [{"id": "approve"}, {"id": "reject"}], "kind": "approval"}}
APPR = {"queue": "aprov", "roles": ["Acoes.Aprovador"]}


def _codes(rule):
    prof = {"actionRules": {"enabled": True, "rules": [dict({"id": "r1"}, **rule)]}, "reviewQueues": QUEUES}
    return [p["code"] for p in ar.action_rules_problems(prof)]


def test_servidor_contact_nunca_e_desconhecido():
    for action in ar.CONTACT_ACTIONS:
        assert ar.UNKNOWN_SERVER not in _codes({"action": action, "mode": "allow", "approval": APPR})
    assert ar.UNKNOWN_SERVER in _codes({"action": "erp.post", "mode": "allow"})


def test_permitir_sem_aprovadores_avisa_o_primeiro_contacto():
    assert ar.CONTACT_FIRST_WITHOUT_APPROVERS in _codes({"action": "contact.ask", "mode": "allow"})
    # «confirmar» num contacto é «aprovar» (só há automatismos): sem aprovadores é ERRO, não aviso.
    codes = _codes({"action": "contact.tell", "mode": "confirm"})
    assert ar.APPROVE_WITHOUT_QUEUE in codes and ar.CONTACT_FIRST_WITHOUT_APPROVERS not in codes


def test_com_aprovadores_bloquear_ou_so_registar_nao_avisa():
    assert ar.CONTACT_FIRST_WITHOUT_APPROVERS not in _codes({"action": "contact.ask", "mode": "allow", "approval": APPR})
    assert ar.CONTACT_FIRST_WITHOUT_APPROVERS not in _codes({"action": "contact.ask", "mode": "block"})
    assert ar.CONTACT_FIRST_WITHOUT_APPROVERS not in _codes({"action": "contact.ask", "mode": "allow", "log_only": True})
    assert ar.CONTACT_FIRST_WITHOUT_APPROVERS not in _codes({"action": "erp.post", "mode": "allow"})


def test_permitir_com_fila_que_nao_e_de_aprovacao_e_erro():
    assert ar.UNKNOWN_QUEUE in _codes({"action": "contact.ask", "mode": "allow",
                                       "approval": {"queue": "nao-existe", "roles": ["A.B"]}})
    prof = {"actionRules": {"enabled": True, "rules": [{"id": "r1", "action": "contact.ask", "mode": "allow",
                                                        "approval": {"queue": "x", "roles": ["A.B"]}}]},
            "reviewQueues": {"x": {"states": [{"id": "new"}], "actions": []}}}
    assert ar.APPROVAL_QUEUE_SHAPE in [p["code"] for p in ar.action_rules_problems(prof)]


def test_aprovar_sem_aprovadores_continua_erro():
    codes = _codes({"action": "contact.tell", "mode": "approve", "approval": {"queue": "aprov"}})
    assert ar.APPROVE_WITHOUT_APPROVERS in codes and ar.CONTACT_FIRST_WITHOUT_APPROVERS not in codes
