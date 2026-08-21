"""O que a IA faz depois que o motor já analisou: sugestões priorizadas,
correção de um achado e geração de README.

**A análise em si não passa por aqui.** Ela é do CodeInsight Engine
(`app/engine/`), que não usa IA nenhuma. Houve um caminho em que cada dimensão
era analisada por prompt; ele foi substituído na migração e removido depois de
verificar que não tinha um único chamador no repositório.

Este módulo depende só da interface `AIProvider` (injetada pelo chamador,
tipicamente via `app.ai.factory.get_ai_provider()`) — nunca de um SDK de IA
específico.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProvider, AIProviderError
from app.models.analysis import Analysis
from app.models.enums import Severity
from app.models.fix_suggestion import FixSuggestion
from app.models.readme import GeneratedReadme
from app.models.suggestion import Suggestion
from app.prompts import fix, readme_gen
from app.prompts import suggestions as suggestions_prompt

logger = logging.getLogger(__name__)

# --- A resposta do provedor de IA é entrada não confiável ---------------------
#
# Não porque o provedor seja hostil, mas porque o texto que ele devolve não é
# garantido por contrato nenhum. Duas razões independentes:
#
# 1. O modelo erra sozinho. `"HIGH"` em vez de `"high"` é o caso clássico, e o
#    tipo da coluna é um ENUM do Postgres — a caixa alta não entra.
# 2. O conteúdo do repositório analisado entra no prompt, e ele é NÃO CONFIÁVEL.
#    Não medi que uma injeção dirigida funcione contra um modelo real; o ponto é
#    que a resposta não pode ser tratada como contrato validado quando parte da
#    entrada que a produziu veio de terceiro.
#
# O que acontecia sem isto, medido gravando de verdade no Postgres:
#
#   severity fora do enum      -> InvalidTextRepresentation
#   severity em caixa alta     -> InvalidTextRepresentation
#   title com 5000 caracteres  -> StringDataRightTruncation
#   file_path com 5000         -> StringDataRightTruncation
#   description nula           -> NotNullViolation
#   item que não é dict        -> AttributeError
#
# E o efeito era desproporcional ao defeito: as sugestões são gravadas numa
# transação só, então **uma** sugestão malformada levava junto todas as boas —
# medido com uma resposta de duas sugestões, uma válida e uma inválida, zero
# gravadas. Como `_enrich_with_ai` engole a exceção para não invalidar a análise
# do motor, o usuário via a análise concluída e nenhuma sugestão, sem explicação.

TITULO_MAX = 255
CAMINHO_MAX = 1024


def _texto(valor: object, *, padrao: str = "") -> str:
    """Aceita o que o modelo mandou e devolve texto.

    Número e lista viram texto em vez de derrubar a gravação: `explanation: 42`
    é uma explicação pobre, não um motivo para perder a correção inteira.
    """
    if valor is None:
        return padrao
    if isinstance(valor, str):
        return valor
    return str(valor)


def _severidade(valor: object) -> Severity:
    """`"HIGH"`, `"High"` e `" high "` são a mesma severidade que o modelo quis
    dizer, e nenhuma delas entra no ENUM sem normalizar.

    Valor que não corresponde a nenhuma severidade cai em MEDIUM — que já era o
    default da coluna e o default deste código quando a chave vem ausente. Não é
    inventar dado novo: é o mesmo desconhecido de sempre, agora registrado no log
    em vez de derrubar a gravação.
    """
    if isinstance(valor, str):
        normalizado = valor.strip().lower()
        for severidade in Severity:
            if severidade.value == normalizado:
                return severidade
    if valor is not None:
        logger.warning("Severidade fora do contrato na resposta da IA: %r", valor)
    return Severity.MEDIUM


def _normalizar_sugestao(item: object) -> dict | None:
    """Devolve os campos prontos para virar `Suggestion`, ou `None` quando o item
    não tem nada aproveitável."""
    if not isinstance(item, dict):
        logger.warning("Item de sugestão que não é objeto, descartado: %r", type(item).__name__)
        return None

    titulo = _texto(item.get("title")).strip()
    descricao = _texto(item.get("description")).strip()
    if not titulo and not descricao:
        logger.warning("Sugestão sem título e sem descrição, descartada")
        return None

    if len(titulo) > TITULO_MAX:
        # Truncar um título preserva o começo, que é onde está o assunto.
        titulo = titulo[: TITULO_MAX - 1] + "…"

    caminho = item.get("file_path")
    caminho = _texto(caminho) if caminho is not None else None
    if caminho is not None and len(caminho) > CAMINHO_MAX:
        # Caminho truncado é caminho errado — apontaria para um arquivo que não
        # existe. Melhor não afirmar nada sobre o arquivo.
        logger.warning("Caminho de arquivo grande demais na sugestão, descartado")
        caminho = None

    correcao = item.get("code_fix")
    return {
        "title": titulo or "Sugestão",
        "description": descricao,
        "severity": _severidade(item.get("severity")),
        "file_path": caminho,
        "code_fix": _texto(correcao) if correcao is not None else None,
    }


async def generate_and_persist_suggestions(
    db: AsyncSession,
    analysis: Analysis,
    full_name: str,
    findings_by_dimension: dict[str, list[dict]],
    ai_provider: AIProvider,
) -> list[Suggestion]:
    user_prompt = suggestions_prompt.build_user_prompt(full_name, findings_by_dimension)
    result = await ai_provider.generate_json(
        suggestions_prompt.SYSTEM_PROMPT, user_prompt, max_tokens=6000
    )
    items = result.get("suggestions") if isinstance(result, dict) else None
    if not isinstance(items, list):
        # `"suggestions": "texto"` era pior do que uma lista vazia: iterar uma
        # string entrega caracteres, e o `.get` do primeiro deles estourava.
        logger.warning(
            "Resposta da IA sem lista de sugestões (veio %s)",
            type(items).__name__,
        )
        items = []

    rows = []
    for item in items:
        campos = _normalizar_sugestao(item)
        if campos is None:
            continue
        row = Suggestion(analysis_id=analysis.id, **campos)
        db.add(row)
        rows.append(row)

    descartadas = len(items) - len(rows)
    if descartadas:
        logger.warning(
            "%d de %d sugestões descartadas por não terem conteúdo aproveitável",
            descartadas,
            len(items),
        )
    return rows


async def generate_and_persist_readme(
    db: AsyncSession,
    analysis: Analysis,
    full_name: str,
    files: dict[str, str],
    ai_provider: AIProvider,
) -> GeneratedReadme:
    user_prompt = readme_gen.build_user_prompt(full_name, files)
    content = await ai_provider.generate_text(
        readme_gen.SYSTEM_PROMPT, user_prompt, max_tokens=6000
    )

    readme = GeneratedReadme(analysis_id=analysis.id, content=content.strip())
    db.add(readme)
    return readme


async def generate_and_persist_fix(
    db: AsyncSession,
    analysis: Analysis,
    *,
    title: str,
    description: str,
    file_path: str | None,
    line: int | None,
    file_content: str | None,
    ai_provider: AIProvider,
) -> FixSuggestion:
    """Gera uma correção para UM achado específico, sob demanda. Nunca é
    aplicada no repositório — só fica disponível para o usuário revisar."""
    user_prompt = fix.build_user_prompt(title, description, file_path, line, file_content)
    result = await ai_provider.generate_json(fix.SYSTEM_PROMPT, user_prompt, max_tokens=3000)
    if not isinstance(result, dict):
        raise ValueError("Resposta inesperada do provedor de IA ao gerar a correção")

    codigo_sugerido = _texto(result.get("suggested_code")).strip()
    if not codigo_sugerido:
        # Sem código sugerido não há correção. Gravar a linha assim mesmo
        # devolvia 201 com os campos vazios — a interface mostrava uma correção
        # que não existe, o que é pior do que dizer que não deu certo.
        raise AIProviderError("O provedor de IA não devolveu um código corrigido para este achado.")

    fix_row = FixSuggestion(
        analysis_id=analysis.id,
        file_path=file_path,
        line=line,
        current_code=_texto(result.get("current_code")),
        suggested_code=codigo_sugerido,
        explanation=_texto(result.get("explanation")),
    )
    db.add(fix_row)
    return fix_row
