import { ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { Card, CardContent } from "@/components/ui/card";

const PRIVACY_CONTACT = "codeinsightai.suporte@gmail.com";
const PRIVACY_UPDATED_AT = "7 de novembro de 2026";

/**
 * Política de privacidade pública (/privacidade).
 *
 * Cada afirmação aqui corresponde ao que o código faz — tabelas em
 * `backend/app/models`, armazenamento do navegador em `frontend/src/lib`,
 * provedores em `docs/deployment.md`. Mudou o que o sistema coleta ou com quem
 * compartilha? Atualize este texto e `PRIVACY_UPDATED_AT` no mesmo PR.
 */
export function PrivacyPage() {
  return (
    <div className="relative min-h-screen bg-gradient-to-b from-background to-secondary/40 px-4 py-12">
      <ThemeToggle className="absolute right-4 top-4" />

      <div className="mx-auto mb-8 flex max-w-3xl flex-col items-center gap-3 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg">
          <ShieldCheck className="h-6 w-6" />
        </span>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Política de privacidade</h1>
        <p className="text-sm text-muted-foreground">
          CodeInsight AI · Última atualização: {PRIVACY_UPDATED_AT}
        </p>
      </div>

      <Card className="mx-auto w-full max-w-3xl">
        <CardContent className="prose prose-sm max-w-none p-6 dark:prose-invert sm:p-8">
          <p>
            Esta política explica quais dados o CodeInsight AI coleta, para que eles são usados, com
            quem são compartilhados e como você pode exercer seus direitos, nos termos da Lei Geral
            de Proteção de Dados (Lei nº 13.709/2018 — LGPD).
          </p>

          <h2>1. Contato</h2>
          <p>
            Para dúvidas sobre privacidade ou para exercer seus direitos, escreva para{" "}
            <a href={`mailto:${PRIVACY_CONTACT}`}>{PRIVACY_CONTACT}</a>.
          </p>

          <h2>2. Dados que coletamos</h2>
          <ul>
            <li>
              <strong>Dados da conta:</strong> e-mail, nome de usuário e a data de criação. A senha
              nunca é guardada: armazenamos apenas um hash bcrypt dela.
            </li>
            <li>
              <strong>Login com Google ou GitHub (opcional):</strong> o identificador da sua conta
              no provedor, o e-mail verificado e o nome exibido, além das datas de vinculação e do
              último acesso. Não recebemos nem guardamos sua senha do Google ou do GitHub, e o token
              de acesso entregue pelo provedor é descartado logo após identificar você. O login com
              GitHub pede apenas leitura do perfil e dos e-mails — nenhum acesso aos seus
              repositórios.
            </li>
            <li>
              <strong>Token do GitHub (opcional):</strong> se você conectar um Personal Access Token
              nas configurações para analisar repositórios privados, ele é guardado criptografado e
              usado apenas para consultar a API do GitHub em seu nome. Você pode removê-lo a
              qualquer momento.
            </li>
            <li>
              <strong>Repositórios e análises:</strong> o nome, a descrição e os metadados dos
              repositórios que você adiciona, e os resultados das análises (notas, achados,
              sugestões, correções e READMEs gerados).
            </li>
            <li>
              <strong>Dados técnicos:</strong> o endereço IP de cada requisição é usado, apenas na
              memória do servidor, para limitar tentativas excessivas (por exemplo, de login); ele
              não é gravado no banco de dados. O provedor de hospedagem mantém registros técnicos de
              acesso por tempo limitado. Senhas, tokens e chaves nunca são registrados.
            </li>
          </ul>

          <h2>3. Para que usamos os dados</h2>
          <ul>
            <li>Criar e autenticar sua conta e manter sua sessão.</li>
            <li>Analisar os repositórios que você solicitar e exibir os resultados.</li>
            <li>Enviar o e-mail de redefinição de senha, quando você o pedir.</li>
            <li>Proteger o serviço contra abuso e acessos indevidos.</li>
          </ul>
          <p>
            Não vendemos dados, não os usamos para publicidade e não fazemos perfis de usuários.
          </p>

          <h2>4. Com quem compartilhamos</h2>
          <p>
            Os dados são tratados por fornecedores necessários para o serviço funcionar, cada um
            apenas no que lhe cabe:
          </p>
          <ul>
            <li>
              <strong>Render</strong> (servidor da aplicação), <strong>Vercel</strong> (site),{" "}
              <strong>Neon</strong> (banco de dados) e <strong>Cloudflare</strong> (rede de entrega)
              — hospedagem e infraestrutura.
            </li>
            <li>
              <strong>Brevo</strong> — envio do e-mail de redefinição de senha (recebe seu e-mail e
              seu nome de usuário).
            </li>
            <li>
              <strong>Google</strong> e <strong>GitHub</strong> — apenas quando você escolhe entrar
              com eles.
            </li>
            <li>
              <strong>API do GitHub</strong> — de onde vem o conteúdo dos repositórios analisados.
            </li>
            <li>
              <strong>Provedor de inteligência artificial</strong> — somente quando você usa os
              recursos opcionais de IA (explicar achados, sugerir correções, gerar README): trechos
              do repositório analisado e os achados são enviados ao provedor configurado para gerar
              a resposta. A análise principal não usa IA externa.
            </li>
          </ul>
          <p>
            Alguns desses fornecedores processam dados fora do Brasil. Também podemos divulgar dados
            quando exigido por lei ou ordem judicial.
          </p>

          <h2>5. Armazenamento no seu navegador</h2>
          <ul>
            <li>
              <strong>Sessão:</strong> um token de acesso fica no armazenamento local do navegador (
              <code>localStorage</code>) enquanto você estiver conectado e é apagado ao sair.
            </li>
            <li>
              <strong>Preferência de tema</strong> (claro/escuro), também no armazenamento local.
            </li>
            <li>
              <strong>Login social:</strong> um cookie técnico temporário, válido por até 10
              minutos, protege a ida e a volta ao Google ou GitHub e é apagado ao fim do login.
            </li>
          </ul>
          <p>Não usamos cookies de rastreamento, de publicidade ou de análise de audiência.</p>

          <h2>6. Por quanto tempo guardamos</h2>
          <ul>
            <li>
              Dados da conta, repositórios e análises: enquanto sua conta existir, ou até você pedir
              a exclusão.
            </li>
            <li>
              Conteúdo dos repositórios: baixado em uma pasta temporária durante a análise e apagado
              ao fim dela. Ficam guardados apenas os resultados.
            </li>
            <li>Links de redefinição de senha: expiram em 30 minutos e valem uma única vez.</li>
          </ul>

          <h2>7. Segurança</h2>
          <p>
            Usamos conexões criptografadas (HTTPS), hash bcrypt para senhas, criptografia para o
            token do GitHub, proteção contra falsificação de requisições no login social e limitação
            de tentativas. Nenhum sistema é totalmente invulnerável; se identificarmos um incidente
            que possa afetar você, avisaremos conforme a lei.
          </p>

          <h2>8. Seus direitos</h2>
          <p>
            Você pode pedir a qualquer momento: confirmação e acesso aos seus dados, correção,
            exclusão da conta e dos dados associados, portabilidade e informações sobre o
            compartilhamento. Basta escrever para{" "}
            <a href={`mailto:${PRIVACY_CONTACT}`}>{PRIVACY_CONTACT}</a> a partir do e-mail da conta.
          </p>
          <p>
            Você também pode, sozinho: remover o token do GitHub e desconectar contas Google ou
            GitHub em <em>Configurações</em>, e revogar o acesso do CodeInsight AI em{" "}
            <a href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
              myaccount.google.com/permissions
            </a>{" "}
            e{" "}
            <a href="https://github.com/settings/applications" target="_blank" rel="noreferrer">
              github.com/settings/applications
            </a>
            .
          </p>

          <h2>9. Dados do Google</h2>
          <p>
            O uso e a transferência, para qualquer outro aplicativo, de informações recebidas das
            APIs do Google seguem a{" "}
            <a
              href="https://developers.google.com/terms/api-services-user-data-policy"
              target="_blank"
              rel="noreferrer"
            >
              Política de Dados do Usuário dos Serviços de API do Google
            </a>
            , incluindo os requisitos de uso limitado. Do Google, usamos apenas o identificador da
            conta, o e-mail verificado e o nome, exclusivamente para criar e identificar sua conta
            no CodeInsight AI.
          </p>

          <h2>10. Alterações</h2>
          <p>
            Esta política pode ser atualizada. A data no topo indica a versão em vigor; mudanças
            relevantes serão comunicadas no site.
          </p>
        </CardContent>
      </Card>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        <Link to="/login" className="font-medium text-primary-text hover:underline">
          Voltar para o login
        </Link>
      </p>
    </div>
  );
}
