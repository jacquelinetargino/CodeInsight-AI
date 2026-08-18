# Política de Segurança

## Reportando uma vulnerabilidade

Se você encontrar uma vulnerabilidade de segurança no CodeInsight AI, **não abra uma
issue pública**. Em vez disso:

1. Envie os detalhes de forma privada para o mantenedor do repositório (ex.: via
   [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories)
   no menu "Security" do repositório, se habilitado, ou por contato direto listado no
   perfil do mantenedor).
2. Inclua: passos para reproduzir, impacto esperado, e uma sugestão de correção se
   tiver uma.
3. Você deve receber uma resposta em até 5 dias úteis reconhecendo o recebimento.

Pedimos que você não divulgue a vulnerabilidade publicamente até que uma correção
esteja disponível.

## Escopo

Este é um projeto de portfólio educacional. Ainda assim, levamos a sério relatos sobre:

- Exposição de credenciais (chaves de API, PATs do GitHub, tokens JWT)
- Bypass de autenticação/autorização (acessar dados de outro usuário)
- Injeção (SQL, template, comando)
- Vulnerabilidades nas dependências listadas em `requirements.txt`/`package.json`

## Boas práticas já aplicadas neste projeto

- Nenhuma credencial é versionada — tudo via `.env` (fora do controle de versão)
- Senhas de usuário: hash bcrypt via `passlib`, nunca texto puro, entre 8 e 72 bytes
  (o bcrypt ignora o que passa disso, então aceitar mais seria prometer o que não existe)
- PATs do GitHub: criptografados em repouso (Fernet), nunca logados
- Autenticação: JWT assinado, validado em toda rota protegida via dependência do FastAPI
- Rate limiting nos endpoints mais sensíveis (criação de análise, solicitação de correção)
  e nos dois abertos ao público (login, cadastro)
- O tempo de resposta do login não revela se o e-mail está cadastrado
- CORS restrito ao domínio configurado do frontend
- Nenhum código enviado/analisado é executado pelo backend — o conteúdo dos arquivos é
  tratado sempre como texto, tanto na coleta quanto no envio para o provedor de IA

Mais detalhes técnicos em [`docs/security.md`](docs/security.md).

## Versões suportadas

Este projeto não segue um ciclo formal de releases (é um projeto de portfólio) — o
único ponto de suporte é a branch `main`.
