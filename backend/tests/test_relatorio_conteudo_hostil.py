"""O conteúdo do repositório analisado não vira markup no relatório.

Título, descrição, evidência e caminho de arquivo de cada achado vêm do
repositório analisado — dado **não confiável** por definição. Tudo isso entra no
template do relatório e sai num PDF que o usuário abre.

Quem controla o repositório controla esses valores: basta um arquivo chamado
`<script>.py`, ou uma linha de código com `<img onerror=...>`, para o conteúdo
chegar ao template.

`autoescape=True` no ambiente Jinja é o que segura. **Nada verificava**: trocar
para `autoescape=False`, ou marcar um campo com `|safe`, não quebrava teste
algum.

Os payloads aqui são inertes — servem para observar o escape, não para explorar
coisa alguma.
"""

import pytest

from app.enums import Dimension, Severity
from app.services.pdf_service import render_analysis_pdf, render_report_html

# Injeção de HTML: precisa sair escapada, nunca literal.
PAYLOADS_HTML = {
    "script": "<script>alert(1)</script>",
    "atributo": '"><img src=x onerror=alert(1)>',
    "entidade": "&lt;script&gt;",
    "aspas": "\"'`",
}

# Sintaxe de template: precisa sair **literal**, como texto.
#
# São propriedades diferentes, e confundi-las escreve um teste errado: exigir
# que `{{ 7*7 }}` suma do HTML testaria o oposto do que importa. `{` e `%` não
# são especiais em HTML, então o autoescape corretamente não os toca — o que
# não pode acontecer é o Jinja avaliá-los.
#
# O segundo item de cada par é procurado no documento INTEIRO, então ele precisa
# ser um valor que não possa aparecer por outro motivo. Os dois primeiros
# sentinelas eram curtos demais e colidiam:
#
#   "49"     -> o relatório carimba a data de geração, e às 22:49 o teste
#               falhou na main com "o template avaliou o conteúdo". Duas horas
#               por dia o teste acusava um problema que não existia.
#   "Config" -> é prefixo de "Configuração", o rótulo da dimensão CONFIGURATION.
#               Passava só porque o relatório de teste tem uma dimensão só.
#
# Um teste de segurança que dá alarme falso é pior do que nenhum: da próxima vez
# que ele apontar algo de verdade, ninguém vai acreditar.
PAYLOADS_TEMPLATE = {
    # 31337 * 1337 = 41897569, oito dígitos que nada mais no relatório produz.
    "expressao": ("{{ 31337 * 1337 }}", "41897569"),
    "bloco": ("{% for _ in range(9) %}INJETADO{% endfor %}", "INJETADO" * 9),
    # `{{ config }}` renderizaria o repr do objeto de configuração do Jinja, que
    # começa com "<Config " — com o espaço, que "Configuração" não tem.
    "config": ("{{ config }}", "<Config "),
}


class _Resultado:
    def __init__(self, dimension, score, summary, findings):
        self.dimension = dimension
        self.score = score
        self.summary = summary
        self.findings = findings


class _Sugestao:
    def __init__(self, title, description, severity):
        self.title = title
        self.description = description
        self.severity = severity


class _Analise:
    """Dublê com a forma que o serviço consome. Evita banco: o que está sob
    teste é a renderização, não a persistência."""

    id = "00000000-0000-0000-0000-000000000000"

    def __init__(self, resultados, sugestoes=()):
        self.overall_score = 42.0
        self.results = list(resultados)
        self.suggestions = list(sugestoes)


def _analise_com(payload: str) -> _Analise:
    """Coloca o payload em **todo** campo que vem do repositório analisado."""
    return _Analise(
        resultados=[
            _Resultado(
                dimension=Dimension.SECURITY,
                score=10,
                summary=payload,
                findings=[
                    {
                        "title": payload,
                        "description": payload,
                        "suggestion": payload,
                        "severity": "high",
                        "file_path": payload,
                        "line": 1,
                        "evidence": payload,
                    }
                ],
            )
        ],
        sugestoes=[_Sugestao(title=payload, description=payload, severity=Severity.HIGH)],
    )


# --- a garantia central ------------------------------------------------------


@pytest.mark.parametrize("nome,payload", PAYLOADS_HTML.items())
def test_injecao_de_html_sai_escapada(nome, payload):
    html = render_report_html(_analise_com(payload), repository_full_name="dono/repo")

    assert payload not in html, f"{nome}: o payload saiu intacto no HTML do relatório"


@pytest.mark.parametrize("nome,caso", PAYLOADS_TEMPLATE.items())
def test_sintaxe_de_template_e_dado_e_nao_codigo(nome, caso):
    """O conteúdo do repositório não pode ser avaliado pelo motor de template.

    A asserção é sobre o **efeito** da avaliação, não sobre o texto: o payload
    aparece literal (correto) e o resultado que ele produziria se fosse
    executado não aparece em lugar nenhum.
    """
    payload, efeito_se_avaliasse = caso
    html = render_report_html(_analise_com(payload), repository_full_name="dono/repo")

    assert payload in html, f"{nome}: o payload deveria aparecer literal, como texto"
    assert efeito_se_avaliasse not in html, f"{nome}: o template avaliou o conteúdo"


def test_os_sentinelas_nao_aparecem_num_relatorio_inofensivo():
    """Cada sentinela é procurada no documento inteiro, então precisa ser um
    valor que só a avaliação do template possa produzir.

    Foi por não conferir isso que o teste acima acusou um problema inexistente:
    `"49"` também é o minuto da data de geração carimbada no rodapé.
    """
    html = render_report_html(_analise_com("conteúdo inofensivo"), repository_full_name="dono/repo")

    for nome, (_, sentinela) in PAYLOADS_TEMPLATE.items():
        assert sentinela not in html, (
            f"{nome}: a sentinela {sentinela!r} aparece num relatório sem payload nenhum "
            "— o teste acusaria avaliação de template que não houve"
        )


@pytest.mark.parametrize("nome,caso", PAYLOADS_TEMPLATE.items())
def test_a_sentinela_e_improvavel_o_bastante(nome, caso):
    """Regra de bolso, não prova: sentinela curta colide com o conteúdo normal
    do relatório mais cedo ou mais tarde.

    O teste acima cobre o relatório de hoje; este cobre o de amanhã, quando
    alguém acrescentar um número, um rótulo ou um rodapé novo. As duas que
    quebraram tinham 2 e 6 caracteres.
    """
    _, sentinela = caso
    assert len(sentinela) >= 8, (
        f"{nome}: a sentinela {sentinela!r} é curta demais para ser procurada no "
        "documento inteiro sem risco de alarme falso"
    )


def test_o_nome_do_repositorio_tambem_e_escapado():
    """Vem da API do GitHub e reflete o que o dono do repositório escolheu."""
    html = render_report_html(
        _analise_com("inofensivo"), repository_full_name=f"dono/{PAYLOADS_HTML['script']}"
    )
    assert PAYLOADS_HTML["script"] not in html
    assert "&lt;script&gt;" in html


def test_o_escape_preserva_o_texto_para_quem_le():
    """A trava do outro lado: apagar o conteúdo também passaria nos testes
    acima. O usuário precisa continuar vendo o que foi encontrado."""
    html = render_report_html(
        _analise_com("<script>alert(1)</script>"), repository_full_name="dono/repo"
    )

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --- o PDF continua sendo gerado ---------------------------------------------


def test_o_pdf_e_gerado_mesmo_com_conteudo_hostil():
    """Escapar não pode virar erro de renderização: o relatório de um
    repositório hostil ainda precisa sair."""
    pdf = render_analysis_pdf(
        _analise_com(PAYLOADS_HTML["script"]), repository_full_name="dono/repo"
    )

    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 1000


# --- a configuração de escape não pode ser desligada --------------------------


def test_o_ambiente_jinja_escapa_por_padrao():
    """Trava explícita. `autoescape=False` faria todos os testes acima falharem,
    mas esta asserção nomeia a causa em vez de deixar o diagnóstico para quem
    for ler cinco falhas de injeção.
    """
    from app.services.pdf_service import _env

    assert _env.autoescape is True


def test_o_template_nao_marca_nada_como_seguro():
    """`|safe` num campo desfaz o escape só naquele ponto — e é a forma mais
    provável de a proteção sumir, porque parece uma correção de formatação."""
    from pathlib import Path

    from app.services.pdf_service import TEMPLATES_DIR

    for template in Path(TEMPLATES_DIR).glob("*.html"):
        conteudo = template.read_text(encoding="utf-8")
        assert "|safe" not in conteudo, f"{template.name} usa |safe"
        assert "| safe" not in conteudo, f"{template.name} usa | safe"
        assert "autoescape false" not in conteudo, f"{template.name} desliga autoescape"
