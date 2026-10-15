"""Modo demonstração: o que `MODELOS_FALSOS=true` injeta no sistema de verdade.

Os falsos dos testes repetem um roteiro fixo. Estes são dublês que reagem à mensagem por
palavras-chave, para o chatbot inteiro poder ser apresentado sem chave nenhuma e sem depender
do Jev estar no ar: o Roteador escolhe o caminho certo, os Guardrails bloqueiam o óbvio, o
agente consulta Pedidos e pede Reembolsos (e o Gate decide de verdade, por código), a resposta
de dúvida cita a política recuperada e o Ticket tem um resumo legível. Não há inteligência
aqui, e é de propósito: o que se demonstra é o sistema em volta do modelo.
"""

import re
import typing
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from ampere.nucleo.falsos import JevFalso, ModeloFalso, instancia_padrao
from ampere.nucleo.jev import EstadoDoJev, Perguntas, RespostasJev

PROBABILIDADE_QUANDO_BATE = 0.93

SINAIS_DO_GUARDRAIL = {
    "manipulacao": r"ignor|esque[çc]a (as|suas)|prompt|instru[çc][õo]es|finja|jailbreak"
    r"|sou (o |a )?(gerente|desenvolvedor|funcion[áa]rio)",
    "fora_de_escopo": r"receita|futebol|piada|capital d[aoe]|poema|hor[óo]scopo|elei[çc]",
    "dado_sensivel": r"cart[ãa]o|\bcpf\b|senha|\bcvv\b|\brg\b",
}
SINAIS_DE_INTENCAO = (
    ("quer_humano", r"humano|pessoa|atendente|algu[ée]m de verdade"),
    ("transacao", r"\bp\d{4}\b|pedido|reembols|estorn|dinheiro de volta|rastre|cancel"),
)
PEDIDO = re.compile(r"\bP\d{4}\b", re.IGNORECASE)
REEMBOLSO = re.compile(r"reembols|estorn|dinheiro de volta|devolver o dinheiro", re.IGNORECASE)
TRECHO = re.compile(
    r"## Trechos da Base de Conhecimento\n\[(.+?)\] (.+?)(?:\n\n\[|\n\n##|\Z)", re.S
)


class JevDeDemonstracao(JevFalso):
    """Responde "sim" (0,93) quando a mensagem bate com o padrão da pergunta."""

    def perguntar(self, estado: EstadoDoJev, perguntas: Perguntas) -> RespostasJev:
        texto = str(estado.get("mensagem_do_cliente", "")) if isinstance(estado, dict) else ""
        self.nouls = {
            nome: PROBABILIDADE_QUANDO_BATE
            for nome, padrao in SINAIS_DO_GUARDRAIL.items()
            if re.search(padrao, texto, re.IGNORECASE)
        }
        intencao = next(
            (nome for nome, padrao in SINAIS_DE_INTENCAO if re.search(padrao, texto, re.I)),
            "duvida",
        )
        self.choices = {"intencao": intencao}
        return super().perguntar(estado, perguntas)


class GeradorDeDemonstracao(ModeloFalso):
    """Com Ações disponíveis, pede a Ação que a mensagem sugere e depois conta o resultado;
    sem Ações (caminho da dúvida), cita o primeiro trecho da Base de Conhecimento."""

    com_acoes: bool = False
    pausa_entre_palavras: float = 0.02

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable:
        return self.model_copy(update={"com_acoes": True})

    def _responder(self, messages: list[BaseMessage]) -> AIMessage:
        ultima = messages[-1]
        if isinstance(ultima, ToolMessage):
            return AIMessage(_contar_resultados(messages))
        if self.com_acoes:
            return _pedir_acao(_ultima_fala_do_cliente(messages))
        sistema = str(messages[0].content) if isinstance(messages[0], SystemMessage) else ""
        return AIMessage(_citar_politica(sistema))


class TrabalhadorDeDemonstracao(ModeloFalso):
    """Saídas estruturadas montadas a partir das falas do Cliente no prompt."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(["Resumo das mensagens anteriores (modo demonstração)."], **kwargs)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        def responder(entrada: Any) -> BaseModel:
            mensagens = entrada if isinstance(entrada, list) else [entrada]
            self.chamadas.append(list(mensagens))
            falas = re.findall(
                r"^Cliente: (.+)$", "\n".join(str(m.content) for m in mensagens), re.M
            )
            return _preencher(schema, falas)

        return RunnableLambda(responder)


# --- como o gerador responde ----------------------------------------------------------------


def _ultima_fala_do_cliente(messages: Sequence[BaseMessage]) -> str:
    return next((str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), "")


def _pedir_acao(fala: str) -> AIMessage:
    pedido = PEDIDO.search(fala)
    if not pedido:
        return AIMessage(
            "Claro, posso ajudar com isso. Qual é o número do Pedido? Ele começa com P, "
            "por exemplo **P1001**."
        )
    pedido_id = pedido.group(0).upper()
    if REEMBOLSO.search(fala):
        chamada = {"name": "emitir_reembolso", "args": {"pedido_id": pedido_id, "motivo": fala}}
    else:
        chamada = {"name": "consultar_pedido", "args": {"pedido_id": pedido_id}}
    return AIMessage(content="", tool_calls=[{**chamada, "id": f"demo-{pedido_id}"}])


def _contar_resultados(messages: Sequence[BaseMessage]) -> str:
    resultados = []
    for mensagem in reversed(messages):
        if not isinstance(mensagem, ToolMessage):
            break
        resultados.insert(0, str(mensagem.content))
    return "\n\n".join(_traduzir(resultado) for resultado in resultados)


def _traduzir(resultado: str) -> str:
    if rejeitado := re.search(r"REJEITADO pelo Atendente\. Motivo: (.+?)\. Explique", resultado):
        return (
            "O Atendente analisou o seu pedido e **não aprovou o Reembolso**. "
            f"Motivo informado: {rejeitado.group(1)}."
        )
    if resultado.startswith("Reembolso de"):
        return (
            f"Pronto! {resultado} O valor volta pelo mesmo meio de pagamento da compra, "
            "nos prazos da política de devolução."
        )
    if pedido := re.match(
        r"Pedido (\S+): (.+?) \((\w+)\), (R\$ [\d.,]+), status (.+?), feito em (\S+)", resultado
    ):
        numero, produto, _, valor, status, data = pedido.groups()
        return (
            f"Encontrei o Pedido **{numero}**:\n\n- **Produto:** {produto}\n- **Valor:** {valor}\n"
            f"- **Status:** {status}\n- **Feito em:** {data}"
        )
    if resultado.startswith("Ticket"):
        return "Abri um Ticket e um Atendente vai continuar o seu atendimento em breve."
    return resultado


def _citar_politica(sistema: str) -> str:
    trecho = TRECHO.search(sistema)
    if not trecho:
        return (
            "Não encontrei essa informação nas políticas da Loja. "
            "Quer que eu abra um Ticket para um Atendente?"
        )
    documento, texto = trecho.group(1).removesuffix(".md"), trecho.group(2).strip()
    corpo = re.sub(r"^#{1,3}\s+(.+)$", r"**\1**", texto, flags=re.M)
    return f"Segundo a política da Loja (`{documento}`):\n\n{corpo}"


# --- como o trabalhador preenche uma saída estruturada ---------------------------------------


def _preencher(schema: type[BaseModel], falas: list[str]) -> BaseModel:
    primeira, ultima = (falas[0], falas[-1]) if falas else ("(sem mensagens)", "(sem mensagens)")
    texto = " ".join(falas).lower()
    candidatos: dict[str, Any] = {
        "episodio": f"O Cliente escreveu: “{primeira}”.",
        "fatos": [],
        "resumo": f"O Cliente precisa de um Atendente. Última mensagem: “{ultima}”.",
        "prioridade": "media",
    }
    campos = schema.model_fields
    categoria = campos.get("categoria")
    if categoria and typing.get_origin(categoria.annotation) is typing.Literal:
        opcoes = typing.get_args(categoria.annotation)
        candidatos["categoria"] = next((o for o in opcoes if o in texto), opcoes[-1])
    padrao = instancia_padrao(schema)
    return padrao.model_copy(update={k: v for k, v in candidatos.items() if k in campos})
