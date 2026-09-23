# wtp: worktrees PHP com vhost próprio

`wtp` é uma CLI em Python que cria, serve, testa e remove **git worktrees de projetos
PHP**, cada um com o seu vhost no Apache:

```
~/Projects/outserv_agenda-fix-login  ->  http://fix-login.agenda.localhost/
~/Projects/outserv_agenda-relatorio  ->  http://relatorio.agenda.localhost/
```

Um comando cria o worktree, copia o `.env` reescrevendo o `baseURL`, copia a config
local que o git ignora, ajusta a permissão do `writable/`, cria e habilita o vhost e
recarrega o Apache. Outro comando desfaz exatamente isso.

O motivo: vários agentes de IA (Claude Code, Codex) trabalhando no mesmo repositório
ao mesmo tempo, cada um com o seu código e o seu servidor, sem pisar nos outros.

## Requisitos

- Linux ou WSL2, com Apache 2.4 no layout Debian/Ubuntu (`sites-available`,
  `a2ensite`, `apache2ctl`) e `systemctl`.
- PHP-FPM com socket em `/run/php/php<versão>-fpm.sock` (pode haver várias versões).
- Python 3.12 e [uv](https://docs.astral.sh/uv/).
- `sudo` sem senha para o seu usuário (veja [Sobre o sudo](#sobre-o-sudo)).
- Git 2.31 ou mais novo.

Os hosts são `*.localhost`: o navegador e o `curl` resolvem esses nomes para
127.0.0.1 sozinhos, sem mexer em `/etc/hosts` nem no hosts do Windows.

## Instalação

```bash
git clone https://github.com/gustavofrdev/worktree-php-manager.git
cd worktree-php-manager

# Coloca o comando wtp em ~/.local/bin, em modo editável
uv tool install -e . --python python3.12
wtp --version

# Config dos projetos
mkdir -p ~/.config/wtp
cp config.example.toml ~/.config/wtp/config.toml
$EDITOR ~/.config/wtp/config.toml
```

O `~/.local/bin` precisa estar no `PATH`.

## Configuração

Cada projeto é uma seção `[projects.<nome>]`. O nome da seção é o que você passa
na linha de comando.

```toml
[defaults]
worktrees_dir = "~/Projects"          # worktrees em <worktrees_dir>/<projeto>-<nome>

[projects.outserv_agenda]
main_checkout = "~/Projects/outserv_agenda"
domain = "agenda.localhost"           # worktree "x" vira http://x.agenda.localhost/
php_version = "8.1"                   # entre aspas
env_file = ".env"
base_url_key = "app.baseURL"
main_branch = "main"
document_root = "public"
db_override_key = "database.dbportal.database"
migrations_dir = "app/Database/Migrations"
writable_dir = "writable"
copy_files = ["app/Config/App.php", "app/Config/Constants.php"]
```

| Chave | Obrigatória | Para que serve |
|---|---|---|
| `main_checkout` | sim | checkout principal do repositório; é de onde saem o `.env` e os `copy_files` |
| `domain` | sim | domínio base dos hosts dos worktrees |
| `php_version` | sim | escolhe o socket do PHP-FPM no vhost e o pool em `/etc/php/<v>/fpm/pool.d` |
| `env_file`, `base_url_key` | não | arquivo `.env` e a chave do baseURL que é reescrita |
| `main_branch` | não | base das branches novas e referência do `+/-` no `wtp ls` |
| `document_root` | não | pasta pública, relativa ao worktree |
| `db_override_key` | não | chave do `.env` que o `--db` preenche (no CodeIgniter 4, `database.<grupo>.database`) |
| `migrations_dir` | não | o wtp avisa quando a branch traz migrations que a main não tem |
| `writable_dir` | não | pasta em que o usuário do pool do PHP-FPM precisa gravar |
| `copy_files` | não | arquivos ignorados pelo git que o app precisa para subir (credenciais, config local) |

Para descobrir o que colocar em `copy_files`, rode no checkout principal:

```bash
git ls-files --others --ignored --exclude-standard --directory
```

Sem esses arquivos, o worktree costuma responder HTTP 500.

## Uso

```bash
wtp new outserv_agenda fix-login --branch feat/fix-login   # cria e serve
wtp doctor outserv_agenda fix-login                        # confere tudo, exit 0 = ok
wtp open outserv_agenda fix-login                          # abre no navegador (Windows, via WSL)
wtp ls                                                     # lista worktrees e estado
wtp rm outserv_agenda fix-login --delete-branch            # desfaz tudo
```

| Comando | O que faz |
|---|---|
| `wtp new <projeto> <nome> [--branch b] [--from main] [--db banco] [--no-composer]` | `git fetch`, worktree numa branch nova a partir de `origin/<from>` (ou numa branch local que já existe), `.env`, `copy_files`, `composer install` se faltar `vendor/`, `writable/`, vhost e reload |
| `wtp adopt <projeto> <nome>` | serve um worktree que já existe em `<worktrees_dir>/<projeto>-<nome>`, sem tocar no git |
| `wtp ls [projeto]` | nome, branch, commits à frente e atrás da main, se há alteração pendente, URL, se é do wtp |
| `wtp doctor [projeto] [nome]` | `.env` e baseURL, `copy_files`, vhost, PHP-FPM, `writable/`, HTTP e se os assets vêm do host do worktree |
| `wtp open <projeto> <nome>` | abre a URL com `wslview`, `explorer.exe` ou `xdg-open` |
| `wtp rm <projeto> <nome> [--delete-branch]` | recusa se houver alteração não commitada; remove vhost, worktree e, se pedido, a branch |
| `wtp which [dir]` | diz de qual projeto e de qual worktree é um diretório |

Opções de cada comando (vão depois do subcomando):

- `--json`: resultado em JSON no stdout, mensagens no stderr. É o formato para agentes.
- `--yes` (ou `-y`): não pergunta antes de usar o sudo. Sem terminal e sem `--yes`, o
  wtp para antes de mexer em qualquer coisa.

Opções globais (vão antes do subcomando, por exemplo `wtp --debug ls`):

- `--debug`: mostra o traceback em erros inesperados.
- `--config <arquivo>` ou a variável `WTP_CONFIG`: usa outro config.

Rodar `wtp new` de novo com os mesmos argumentos é seguro: ele só completa o que
faltou, por exemplo depois de uma execução interrompida.

## Para agentes de IA

A skill em [`skills/wtp/SKILL.md`](skills/wtp/SKILL.md) ensina o fluxo para os
agentes: descobrir o projeto, escolher um nome único, criar com `--yes --json`,
trabalhar só dentro do worktree, testar com o `doctor` e remover quando pedido.
Também traz o que nunca fazer, como `git stash` ou migrations no banco compartilhado.

Instale como skill global com symlinks, assim ela se atualiza junto com o repositório:

```bash
mkdir -p ~/.claude/skills ~/.codex/skills
ln -s "$PWD/skills/wtp" ~/.claude/skills/wtp    # Claude Code
ln -s "$PWD/skills/wtp" ~/.codex/skills/wtp     # Codex
```

Depois disso, basta pedir a um agente uma tarefa num projeto cadastrado ("prepare um
ambiente isolado para corrigir X"); ele encontra a skill e usa o `wtp` sozinho.

## Como funciona

- **Só mexe no que é dele.** Os vhosts se chamam `wtp-<projeto>-<nome>.conf` e têm
  uma marca na primeira linha. O wtp recusa tocar em qualquer outro arquivo, e os
  scripts que rodam com sudo conferem isso de novo.
- **Um sudo por operação.** Instalar ou remover um vhost é uma única chamada de
  `sudo`, que roda o `apache2ctl configtest` antes do reload. Se o configtest falhar,
  o arquivo anterior volta (ou o novo sai) e o Apache não é recarregado.
- **Manifesto.** Cada worktree tem um JSON em `~/.local/state/wtp/worktrees/` com o
  que o wtp criou: worktree, branch, `.env`, arquivos copiados, vhost. O `rm` lê esse
  arquivo e desfaz só isso. Num worktree adotado, por exemplo, ele remove o `.env` e
  o vhost, mas deixa a pasta e a branch.
- **Branch.** O `--delete-branch` só apaga uma branch criada pelo wtp cujos commits já
  estão na base de onde ela saiu. Nunca força.
- **Vários agentes ao mesmo tempo.** `git fetch`, `git worktree add` e o reload do
  Apache são serializados com `flock` (em `~/.local/state/wtp/locks/`).
- **`writable/`.** O usuário do pool vem de `/etc/php/<v>/fpm/pool.d/*.conf`. Se não
  for o seu usuário, o wtp dá escrita ao grupo do pool, sem seguir symlinks.

## Cuidados

- **O banco é compartilhado.** Todos os worktrees usam o banco do `.env` do checkout
  principal. Uma migration rodada numa branch muda o esquema para todos. O `wtp new`
  avisa quando a branch traz migrations novas; para isolar, use `--db <banco>` (o
  banco precisa existir).
- **`git stash` é compartilhado** entre todos os worktrees de um repositório. Evite.
- **Host errado não dá erro.** Um `*.localhost` sem vhost próprio cai no primeiro
  vhost do Apache e responde com o código de outro site. Um HTTP 200 não prova que você
  está no worktree certo; o `wtp doctor` prova, porque confere de onde vêm os assets.
- **Login por host.** Cada worktree tem cookie de sessão próprio; é preciso logar em
  cada um.

## Sobre o sudo

O wtp chama `sudo -n bash -c <script>` para instalar e remover vhosts e para ajustar
o `writable/`. O `-n` faz o sudo falhar em vez de pedir senha, então o seu usuário
precisa de sudo sem senha. Como o comando é `bash`, uma regra de sudoers restrita a
ele equivale, na prática, a acesso total; o wtp foi pensado para uma máquina de
desenvolvimento pessoal. Os scripts ficam em `wtp/apache.py` e `wtp/permissions.py`
para você ler antes de usar.

## Desenvolvimento

```bash
uv sync
.venv/bin/pytest
.venv/bin/mypy
.venv/bin/ruff check . && .venv/bin/ruff format .
```

Os testes não tocam no Apache nem no git reais: usam classes falsas nomeadas em
`tests/fakes.py` e `tmp_path`. Os scripts que vão para o sudo são testados de verdade
em `bash`, com os comandos do Apache trocados por stubs (`tests/test_sudo_scripts.py`).

As regras de código, as decisões e as armadilhas encontradas estão no
[`AGENTS.md`](AGENTS.md) (o mesmo arquivo que o `CLAUDE.md`). Leia antes de contribuir.
