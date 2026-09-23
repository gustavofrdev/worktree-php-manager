---
name: wtp
description: Use ao precisar de um worktree git isolado e servido pelo Apache num projeto PHP desta máquina (por exemplo outserv_agenda), para trabalhar em paralelo com outros agentes, testar uma branch no navegador, ou quando o usuário falar em wtp, worktree, vhost ou "servidor próprio". Nesses projetos substitui git worktree add, EnterWorktree e .claude/worktrees.
---

# wtp: um worktree, um servidor

O `wtp` cria um git worktree de um projeto PHP e já o deixa servido pelo Apache em
`http://<nome>.<domínio>/`, com `.env` próprio, arquivos de config local copiados e
vhost habilitado. Cada agente tem o seu worktree e a sua URL, sem pisar nos outros.

## Regra principal

Em projeto cadastrado no wtp, **não crie worktree com `git worktree add` nem com a
ferramenta de worktree do harness** (EnterWorktree, `.claude/worktrees/`). Esses
worktrees ficam sem `.env`, sem `app/Config/Constants.php` e sem vhost, e o site
responde HTTP 500. Use sempre o `wtp`.

## Fluxo

1. **Descubra o projeto** a partir do diretório atual:

   ```bash
   wtp which --json
   ```

   Use o campo `project` nos próximos comandos. `worktree: null` quer dizer que você
   está no checkout principal (ou num worktree feito fora do wtp): crie o seu no passo
   3. Se `worktree` vier preenchido e `url` também, você já está num worktree do wtp;
   confira com o usuário se ele é seu antes de reaproveitar.

   Se der `não pertence a nenhum projeto`, o projeto não está no wtp. Pergunte ao
   usuário se ele quer cadastrar. Se quiser, rode no checkout do projeto:

   ```bash
   wtp generate-config --print --json     # mostra o que seria gravado
   wtp generate-config --json             # grava em ~/.config/wtp/config.toml
   ```

   O wtp descobre o framework cruzando três sinais (composer.json, arquivo de entrada
   como `artisan` ou `spark`, chave do `.env`) e já conhece CodeIgniter 4 e Laravel.
   O que ele não conseguir descobrir pelo código vem em `agent_tasks`: **isso é
   trabalho seu, não do usuário.** Investigue o projeto e rode de novo com a flag
   indicada. Exemplo: sem chave de URL base conhecida, leia `.env.example`,
   `config/app.php` ou `app/Config/App.php`, ache a chave e rode
   `wtp generate-config --base-url-key <chave>`. Só pergunte ao usuário quando o
   código não mostrar a resposta. As `notes` são palpites: confira os que parecerem
   estranhos.

2. **Escolha um nome** curto, derivado da tarefa: `fix-select2`, `rel-horas`.
   Regras: letras minúsculas, dígitos e hífen, até 40 caracteres. Veja os que já
   existem para não colidir com outro agente:

   ```bash
   wtp ls <projeto> --json
   ```

   Se o nome já existe e não é seu, escolha outro. Nunca reaproveite o worktree de
   outro agente.

3. **Crie o worktree**:

   ```bash
   wtp new <projeto> <nome> --branch <tipo>/<descricao> --yes --json
   ```

   - `--from <branch>` quando a base não for a main do projeto.
   - Se a branch já existe localmente, o wtp usa essa branch em vez de criar outra.
   - `--yes` é obrigatório para agente: sem terminal, o wtp não pode pedir
     confirmação do sudo. O wtp só mexe em arquivos `wtp-*.conf` que ele mesmo criou.
   - Guarde `path`, `url` e `branch` do JSON e leia `warnings`. Os que começam com
     "Agente:" são para você resolver: por exemplo, sem `base_url_key` o wtp não mexe
     na URL; descubra a chave pelo código, ponha no config e rode o `new` de novo.
     Os demais (migrations, banco compartilhado) você repassa ao usuário.

4. **Trabalhe só dentro de `path`.** Rode os comandos com caminho absoluto ou dentro
   de `path` (no Claude Code, `cd <path>` persiste entre chamadas do Bash; no Codex,
   use `path` como workdir). Não edite o checkout principal nem o worktree de outro
   agente.

5. **Teste no servidor do worktree**:

   ```bash
   wtp doctor <projeto> <nome>          # exit 0 = tudo certo
   curl -s -o /dev/null -w '%{http_code}\n' <url>
   ```

   O doctor confere `.env`, baseURL, arquivos locais, vhost, PHP-FPM, `writable/`,
   HTTP e se os assets carregam do host certo.

   Cuidado: um host sem vhost próprio (nome digitado errado, ou worktree já removido)
   não dá erro. O Apache cai no primeiro vhost da máquina e serve o código do
   **checkout principal**. Um `200` no curl não prova que você está testando a sua
   branch. A prova é o `wtp doctor` passar, porque ele confere se os links de assets
   apontam para o seu host, e não para outro. `wtp open <projeto> <nome>` abre o
   navegador do Windows; use só se o usuário pedir. Cada host tem cookie de sessão
   próprio, então é preciso fazer login de novo em cada worktree. Isso é esperado.

6. **Ao terminar**, informe ao usuário `url`, `path` e `branch`. Commit e push seguem
   as regras do projeto (AGENTS.md ou CLAUDE.md dele). Remova o worktree só se o
   usuário pedir, ou se a tarefa disser isso:

   ```bash
   wtp rm <projeto> <nome> --yes [--delete-branch]
   ```

   O `rm` recusa quando há alteração não commitada. `--delete-branch` só apaga uma
   branch criada pelo wtp e cujos commits já estão na base; se não estiverem, o wtp
   mantém a branch e explica o motivo.

## Nunca

- **`git stash`.** O stash é compartilhado entre todos os worktrees do repo; seu
  stash aparece para os outros agentes.
- **Rodar migrations no banco compartilhado.** Todos os worktrees usam o mesmo
  banco. Se `warnings` citar migrations novas, avise o usuário antes de rodar
  qualquer `php spark migrate`. Para isolar, crie com `--db <banco_existente>`.
- **Editar ou remover vhost em `/etc/apache2` à mão**, nem mexer nos vhosts que não
  são `wtp-*`.
- **Consertar `.env`, baseURL ou vhost à mão.** Rode o mesmo `wtp new` de novo: ele
  é idempotente e completa o que faltou.
- **Tocar em `web.config`**, que é do servidor de produção (IIS).

## Quando algo dá errado

| Mensagem do wtp | O que fazer |
|---|---|
| `Já existe um worktree em ... que o wtp não criou` | Worktree manual. Se é para servir esse mesmo: `wtp adopt <projeto> <nome> --yes` |
| `Nome de worktree inválido` | Use só a-z, 0-9 e hífen, sem hífen nas pontas |
| `tem alterações não commitadas; não removi nada` | Commite ou descarte (sem stash) e rode o `rm` de novo |
| `A branch ... tem commits que origin/main não tem` | Worktree e vhost já saíram. Mantenha a branch ou faça merge, e rode `wtp rm` sem `--delete-branch` para concluir |
| `configtest falhou; desfiz o vhost` | Outro vhost da máquina está quebrado. Pare e mostre o erro ao usuário |
| doctor com `falha` em HTTP | Leia `sudo tail /var/log/apache2/<host>-error.log` e o `writable/logs/` do worktree |

## Referência

```bash
wtp which [dir] [--json]                        # projeto e worktree de um diretório
wtp generate-config [dir] [--print] [--base-url-key k] [--name n] [--json]
wtp ls [projeto] [--json]                       # branch, +/- da main, alterado, URL
wtp new <projeto> <nome> [--branch b] [--from main] [--db banco] [--no-composer] --yes [--json]
wtp adopt <projeto> <nome> --yes [--json]       # serve um worktree que já existe
wtp doctor [projeto] [nome] [--json]
wtp open <projeto> <nome>
wtp rm <projeto> <nome> --yes [--delete-branch] [--json]
```

Código e config do wtp: `~/Projects/worktree-php-manager`, `~/.config/wtp/config.toml`.
