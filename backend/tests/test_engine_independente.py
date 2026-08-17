"""O motor não depende da camada de persistência.

Importar o detector de credenciais exigia um Postgres configurado. A cadeia era
`secrets` → `rules/__init__` → `registry` → `findings` → `app.models.enums`, e
essa última importação dispara o `__init__` do pacote `app.models`, que carrega
os modelos SQLAlchemy e, com eles, `get_settings()`.

O efeito era absurdo na prática: processar texto em busca de segredo pedia
`DATABASE_URL`, `JWT_SECRET` e `ENCRYPTION_KEY`.

Os testes rodam em subprocesso com o ambiente limpo, porque é a única forma de
observar o que acontece **no momento do import**: o `conftest` já definiu as
variáveis neste processo.
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# Só o indispensável para o Python achar o pacote. Nenhuma variável da aplicação.
AMBIENTE_LIMPO = {
    "PATH": "",
    "SYSTEMROOT": "",  # o Windows precisa dela para carregar o interpretador
    "PYTHONPATH": str(BACKEND),
    "PYTHONIOENCODING": "utf-8",
}


def _importa_sem_configuracao(codigo: str) -> subprocess.CompletedProcess:
    import os

    ambiente = dict(AMBIENTE_LIMPO)
    ambiente["PATH"] = os.environ.get("PATH", "")
    ambiente["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        cwd=str(BACKEND),
        env=ambiente,
        timeout=120,
    )


def test_detector_de_credenciais_importa_sem_banco():
    """A garantia central: processar texto não exige um Postgres."""
    resultado = _importa_sem_configuracao(
        "from app.engine.rules.secrets import detect_secrets;"
        "achados = detect_secrets('AWS_KEY = \"AKIAIOSFODNN7EXAMPLE\"');"
        "print('OK', len(achados))"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "OK" in resultado.stdout


def test_pipeline_completo_importa_sem_banco():
    """Não é só o detector: o motor inteiro precisa ser importável isolado."""
    resultado = _importa_sem_configuracao(
        "from app.engine.pipeline import analyze_directory; print('OK')"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "OK" in resultado.stdout


def test_o_motor_nao_carrega_a_camada_de_persistencia():
    """Trava de arquitetura: importar o motor não pode trazer `app.models` junto.

    Verifica os módulos de fato carregados, não as linhas de import — um import
    indireto por qualquer caminho falha aqui igual.
    """
    resultado = _importa_sem_configuracao(
        "import sys;"
        "import app.engine.pipeline;"
        "carregados = [m for m in sys.modules if m.startswith('app.models')];"
        "print('MODULOS:', carregados)"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "MODULOS: []" in resultado.stdout


def test_o_atalho_de_compatibilidade_continua_funcionando():
    """`from app.models.enums import ...` aparece em muito lugar e não pode
    quebrar — ele só passa a exigir configuração, como qualquer coisa de
    `app.models`."""
    from app.enums import Severity as SeverityDireto
    from app.models.enums import Severity as SeverityCompat

    assert SeverityDireto is SeverityCompat
