"""Catálogo de regras de segurança (SEC-*).

Declarativo de propósito: dá para auditar tudo que o motor procura em segurança
sem abrir um único analyzer. Severidade e recomendação moram aqui, então o mesmo
problema é reportado da mesma forma independentemente de qual detector o achou.
"""

from app.engine.findings import FindingCategory
from app.engine.rules.registry import Rule, RuleRegistry

_S = FindingCategory.SECURITY


def _rule(
    rule_id: str, name: str, severity: str, description: str, recommendation: str, confidence: float
) -> Rule:
    return Rule(
        rule_id=rule_id,
        name=name,
        category=_S,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        recommendation=recommendation,
        confidence=confidence,
    )


SECURITY_RULES: list[Rule] = [
    _rule(
        "SEC-001",
        "Possível chave de API no código",
        "high",
        "Uma credencial com formato de chave de API foi encontrada no código-fonte. "
        "Qualquer pessoa com acesso ao repositório — inclusive no histórico do git — "
        "consegue usá-la.",
        "Mova a credencial para uma variável de ambiente e rotacione a chave exposta: "
        "remover do código não invalida o que já vazou.",
        0.9,
    ),
    _rule(
        "SEC-002",
        "Credencial ou senha no código",
        "critical",
        "Uma senha ou credencial de acesso está escrita diretamente no código ou numa "
        "URL de conexão.",
        "Use variável de ambiente e rotacione a credencial exposta.",
        0.8,
    ),
    _rule(
        "SEC-003",
        "Chave privada no repositório",
        "critical",
        "Um bloco de chave privada foi encontrado. Chaves privadas nunca devem ser " "versionadas.",
        "Remova o arquivo, gere um par de chaves novo e revogue o antigo. Lembre que o "
        "histórico do git ainda contém a chave.",
        0.99,
    ),
    _rule(
        "SEC-004",
        "JSON Web Token no código",
        "high",
        "Um JWT foi encontrado no código. Tokens costumam carregar identidade e "
        "permissões, e continuam válidos até expirarem.",
        "Remova o token e gere um novo. Tokens não devem ser versionados nem em testes.",
        0.85,
    ),
    _rule(
        "SEC-005",
        "Arquivo .env versionado",
        "critical",
        "Um arquivo .env está presente no repositório. Ele normalmente contém as "
        "credenciais reais do ambiente.",
        "Remova o .env do versionamento, adicione ao .gitignore e rotacione tudo que "
        "estava nele. Mantenha apenas um .env.example sem valores reais.",
        0.95,
    ),
    _rule(
        "SEC-006",
        "Uso de eval()",
        "high",
        "eval() executa qualquer expressão que receber. Se algum dado externo chegar até "
        "essa chamada, vira execução de código arbitrário.",
        "Substitua por parsing explícito — ast.literal_eval para dados, json.loads para JSON.",
        0.95,
    ),
    _rule(
        "SEC-007",
        "Uso de exec() ou compile()",
        "high",
        "exec() e compile() executam código construído em tempo de execução.",
        "Reestruture para não precisar gerar código dinamicamente; quase sempre há uma "
        "alternativa com funções ou mapeamento.",
        0.95,
    ),
    _rule(
        "SEC-008",
        "Possível injeção de SQL",
        "critical",
        "Uma consulta SQL está sendo montada por interpolação de string. Se algum valor "
        "vier do usuário, ele controla a consulta.",
        "Use consulta parametrizada — passe os valores como parâmetros em vez de "
        "concatená-los na string.",
        0.85,
    ),
    _rule(
        "SEC-009",
        "Execução de comando do sistema",
        "high",
        "O código executa comandos do sistema operacional. Com shell=True ou os.system, "
        "qualquer dado externo na string vira injeção de comando.",
        "Evite o shell: passe os argumentos como lista para subprocess e nunca interpole "
        "entrada do usuário no comando.",
        0.85,
    ),
    _rule(
        "SEC-010",
        "Criptografia fraca",
        "medium",
        "MD5 e SHA-1 têm colisões conhecidas e não servem para senhas, assinaturas ou "
        "verificação de integridade.",
        "Use SHA-256 para integridade e um algoritmo com fator de custo (bcrypt, argon2) "
        "para senhas.",
        0.9,
    ),
    # As duas seguintes vão além da lista original: os detectores dos PRs 06 e 07
    # as encontram de fato, e enquadrá-las numa das dez acima seria classificar
    # errado.
    _rule(
        "SEC-011",
        "Desserialização insegura",
        "high",
        "pickle e marshal executam código embutido no dado ao desserializar. Carregar um "
        "arquivo desses vindo de fora é o mesmo que executá-lo.",
        "Use um formato de dados sem execução, como JSON.",
        0.9,
    ),
    _rule(
        "SEC-012",
        "yaml.load() sem Loader seguro",
        "high",
        "yaml.load() sem Loader instancia objetos Python arbitrários descritos no arquivo.",
        "Use yaml.safe_load() ou passe Loader=yaml.SafeLoader.",
        0.9,
    ),
    _rule(
        "SEC-013",
        "Injeção de HTML (XSS)",
        "high",
        "HTML é montado dinamicamente e inserido no documento. Se algum trecho vier do "
        "usuário, ele consegue executar script na página de quem abrir.",
        "Insira texto com textContent, ou sanitize o HTML com uma biblioteca dedicada "
        "antes de injetá-lo.",
        0.7,
    ),
    _rule(
        "SEC-014",
        "Aleatoriedade insegura",
        "medium",
        "Math.random() é previsível e não serve para gerar token, senha, identificador de "
        "sessão ou salt.",
        "Use crypto.randomUUID() ou crypto.getRandomValues() no navegador, e crypto.randomBytes() "
        "no Node.",
        0.7,
    ),
    _rule(
        "SEC-015",
        "Credencial no armazenamento do navegador",
        "high",
        "Token guardado em localStorage ou sessionStorage fica acessível a qualquer script "
        "da página — inclusive a um injetado por XSS.",
        "Prefira cookie httpOnly com SameSite, que o JavaScript da página não consegue ler.",
        0.7,
    ),
    _rule(
        "SEC-016",
        "Transporte sem criptografia",
        "medium",
        "Uma URL em http:// envia os dados em texto claro, sujeitos a leitura e alteração "
        "no caminho.",
        "Use https://. Endereços locais de desenvolvimento são exceção aceitável.",
        0.6,
    ),
]


def register_security_rules(registry: RuleRegistry) -> None:
    """Registra o catálogo. Recebe o registro por parâmetro para que os testes
    montem catálogos isolados sem tocar no global."""
    registry.register_all(SECURITY_RULES)
