"""Public identity of the agent: the A2A v1.0 Agent Card."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill

CAMINHO_A2A = "/a2a"
EXEMPLO = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"


def criar_cartao(url_publica: str) -> AgentCard:
    return AgentCard(
        name="Central de Salas",
        description="Reserva salas de reuniao da Hill Valley Tech.",
        provider=AgentProvider(organization="Hill Valley Tech", url="https://hillvalley.example"),
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(
                url=url_publica.rstrip("/") + CAMINHO_A2A,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False, extended_agent_card=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="reservar-sala",
                name="Reservar sala",
                description="Reserva uma sala em um intervalo. Se houver conflito, pergunta qual alternativa usar.",
                tags=["salas", "agenda"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
                examples=[EXEMPLO],
            )
        ],
    )
