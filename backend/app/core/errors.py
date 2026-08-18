"""Fronteira entre o erro que o usuário lê e o erro que fica no log.

`Analysis.error_message` é devolvido pela API e renderizado na página da
análise. Enquanto ele recebia `str(exc)` de qualquer exceção, o que chegava lá
era o que o Python tivesse a dizer — medido:

    FileNotFoundError -> "[Errno 2] No such file or directory:
                          'C:\\Users\\Jacta\\AppData\\Local\\Temp\\
                           codeinsight-a1b2c3\\src\\repo-abc123\\x.py'"
    KeyError          -> "'chave_que_nao_existe'"

O primeiro entrega o caminho do diretório temporário e o nome da conta que roda
o servidor; o segundo não diz nada a quem pediu a análise. E como as mensagens
de erro do sistema de arquivos carregam o nome do arquivo, um repositório
hostil consegue escolher parte do texto — é conteúdo não confiável chegando à
interface por um caminho que ninguém tinha desenhado.

A regra, então: só chega ao usuário a mensagem que foi **escrita para ele**.
Herdar de `FalhaVisivelAoUsuario` é a forma de declarar isso. Qualquer outra
exceção vira um texto genérico, e o detalhe inteiro continua no log via
`logger.exception` — que é onde ele serve para depurar sem servir de vazamento.

Este módulo não importa nada de propósito: o motor pode usá-lo sem arrastar
configuração nem persistência junto (ver `tests/test_engine_independente.py`).
"""


class FalhaVisivelAoUsuario(Exception):
    """Exceção cuja mensagem foi escrita para ser lida por quem pediu a análise.

    Quem levanta uma destas está afirmando que o texto:

    - explica o que aconteceu em vez de nomear a exceção;
    - não contém caminho de arquivo do servidor, host interno, credencial nem
      trecho de configuração;
    - não repassa texto vindo do repositório analisado sem necessidade.
    """
