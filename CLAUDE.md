# WorkTree-phpManager (`wtp`)

CLI em Python para criar, servir, testar e remover **git worktrees de projetos PHP**
na mesma máquina, cada um com seu próprio vhost no Apache. O objetivo é tirar o
trabalho manual de "criar worktree, copiar .env, ajustar baseURL, configurar
Apache, recarregar, limpar tudo depois".

Modo de trabalho: full vibe coding. Itere rápido, entregue algo que funciona e
refine depois. Mesmo assim, qualquer comando que mexa em `/etc/apache2` ou use
`sudo` precisa de uma confirmação antes, ou de `--yes`.

## Requisitos

- **Fica no PATH.** Deve ser instalável como comando `wtp`, via
  `pipx install -e .` ou um symlink em `~/.local/bin`.
- **Mexe direto no Apache.** Cria e remove o arquivo de vhost de cada worktree em
  `/etc/apache2/sites-available/`, roda `a2ensite`/`a2dissite`, valida com
  `apache2ctl configtest` e só então faz `systemctl reload apache2`. Se o
  configtest falhar, desfaz o arquivo e não recarrega.
- **Cria e remove tudo o que for dele.** Worktree, branch (quando pedido), `.env`
  do worktree, vhost, entrada de hosts (se usar). Nada fica órfão, e `rm` desfaz
  exatamente o que `new` criou.
- Linguagem: Python 3.12, só stdlib no início (`argparse`, `subprocess`,
  `pathlib`). Adicione dependências (por exemplo `typer` ou `rich`) só se
  realmente fizerem falta.

## Estilo de código

- Funções: de 4 a 20 linhas. Acima disso, divida.
- Arquivos: abaixo de 500 linhas. Divida por responsabilidade.
- Uma coisa por função, uma responsabilidade por módulo.
- Nomes específicos e únicos. Evite `data`, `handler`, `manager`, `utils`.
  Prefira nomes que devolvam menos de 5 resultados no grep do projeto.
- Tipos explícitos: type hints em todo parâmetro e todo retorno. Rode `mypy --strict`.
- Sem duplicação. Extraia a lógica comum para uma função ou módulo antes de repetir.
- Retorno antecipado em vez de if aninhado. No máximo 2 níveis de indentação.
- `match`/`case` quando houver várias condições possíveis, em vez de cadeia de `if`/`elif`.
- Nome de função, classe e variável em inglês.
- Sempre que possível, orientado a objetos (classes pequenas, `dataclass` para estado).
- Use `Enum` à vontade para estados e tipos fixos (por exemplo, o estado de um worktree).
- Mensagem de exceção inclui o valor recusado e o formato esperado. Quem lê é
  quem abre o log.
- Mensagem para quem usa a CLI: em português claro, dizendo o que aconteceu e o
  que fazer em seguida. Nada de traceback na tela, exceto com `--debug`.
- Efeitos colaterais (git, sudo, Apache, sistema de arquivos) ficam atrás de uma
  classe própria, para os testes usarem uma versão falsa nomeada, e não um mock
  anônimo no meio do teste.
- Formatação e lint: `ruff format` e `ruff check`. Não discuta estilo além do que
  eles decidem.

## Comentários e texto

- Preserve os comentários existentes ao refatorar.
- Escreva o porquê, não o quê.
- Docstring em função pública: intenção mais um exemplo de uso.
- Nunca use travessão em texto de tela, mensagem, comentário ou documentação.
  Troque por vírgula, dois pontos, parênteses ou frases separadas.

## Testes

- `pytest`. Todo método novo ganha teste. Correção de bug ganha teste de
  regressão escrito antes da correção.
- Testes rápidos, independentes e repetíveis. Nada de tocar no Apache ou no git
  real nos testes unitários: use as classes falsas e `tmp_path`.

## Entrega

- PRs pequenos, um por funcionalidade.
- Não commitar antes da revisão do usuário: ao terminar, peça revisão e só
  commite depois da aprovação.
- Mensagem de commit sem `Co-Authored-By` e sem mencionar Claude.
- Ao encontrar um erro ou uma armadilha, registre na seção "Armadilhas já
  conhecidas" deste arquivo.

## Comandos pensados

| Comando | O que faz |
|---|---|
| `wtp new <projeto> <nome> [--from main] [--branch x]` | `git fetch`, `git worktree add` em `~/Projects/<projeto>-<nome>` numa branch nova a partir de `origin/<from>`, copia o `.env` do checkout principal reescrevendo `app.baseURL`, roda `composer install` se o `vendor/` faltar, ajusta a permissão do `writable/`, cria e habilita o vhost, faz reload |
| `wtp ls [projeto]` | nome, branch, commits à frente e atrás do main, se tem alteração pendente, URL, se o vhost está ativo |
| `wtp open <projeto> <nome>` | abre a URL no navegador do Windows (`explorer.exe` / `wslview`) |
| `wtp rm <projeto> <nome> [--delete-branch]` | recusa se houver alteração não commitada; se não houver, desabilita e remove o vhost, faz reload, `git worktree remove` e, se pedido, apaga a branch |
| `wtp doctor [projeto] [nome]` | confere `.env`, `baseURL`, vhost habilitado, permissão do `writable/`, e se a URL responde com HTTP 200 ou 302 |
| `wtp adopt <projeto> <nome>` | serve um worktree que já existe (feito à mão): cria `.env`, copia `copy_files` e o vhost, sem tocar em git; o `rm` depois remove só isso |
| `wtp which [dir]` | diz de qual projeto e worktree é um diretório; é o primeiro passo da skill dos agentes |
| `wtp generate-config [dir]` | cadastra um projeto no config: descobre pelo código o que der (framework por triangulação, vhost existente, git) e devolve em `agent_tasks` o resto, para o agente investigar e rodar de novo; o usuário só entra se o código não mostrar |

Todo comando aceita `--json` (resultado no stdout, mensagens no stderr), para os
agentes lerem a saída. Os que usam sudo aceitam `--yes`.

Os projetos conhecidos ficam num config, por exemplo `~/.config/wtp/config.toml`:
caminho do checkout principal, domínio base, versão do PHP-FPM e o arquivo `.env`
com a chave do baseURL.

## Ambiente real (máquina do usuário)

- WSL2 no Windows, Ubuntu, kernel 6.18. O navegador roda no Windows.
- Python 3.12.3. Apache 2.4.58 (Ubuntu), com `sites-available`/`sites-enabled`.
- PHP-FPM 8.1, 8.2 e 8.4 rodando ao mesmo tempo, cada um com seu socket em
  `/run/php/php8.X-fpm.sock`.
- Os projetos ficam em `~/Projects/`. O usuário é `nk`.
- Vhost de referência (`/etc/apache2/sites-available/agenda.local.conf`), que é o
  molde do template:

  ```apache
  <VirtualHost *:80>
      ServerName agenda.local
      ServerAlias agenda.localhost
      DocumentRoot /home/nk/Projects/outserv_agenda/public
      <Directory /home/nk/Projects/outserv_agenda/public>
          Options FollowSymLinks
          AllowOverride All
          Require all granted
      </Directory>
      <FilesMatch \.php$>
          SetHandler "proxy:unix:/run/php/php8.1-fpm.sock|fcgi://localhost"
      </FilesMatch>
      ErrorLog ${APACHE_LOG_DIR}/agenda.local-error.log
      CustomLog ${APACHE_LOG_DIR}/agenda.local-access.log combined
  </VirtualHost>
  ```

- O `/etc/hosts` do WSL tem entradas `*.local`. Para worktrees, prefira
  `<nome>.<projeto>.localhost`: o navegador resolve `*.localhost` sozinho, sem
  mexer no hosts do WSL nem no do Windows.
- Outros vhosts já existentes (produto-main, benassi, hoerbiger, omega,
  portal-rh, produto-outservai) **não podem ser tocados**. O `wtp` só mexe em
  arquivos que ele mesmo criou. Use um prefixo fixo, como `wtp-<projeto>-<nome>.conf`,
  e um comentário de marcação no topo do arquivo.

## Primeiro caso de uso

Projeto `outserv_agenda` (CodeIgniter 4, PHP 8.1):
- Checkout principal em `~/Projects/outserv_agenda`.
- Já existe um worktree manual: `~/Projects/outserv_agenda-hotfix`, na branch
  `hotfix/select2-filtros-projetos`, sem `.env` e sem vhost. É o primeiro
  candidato para testar o `wtp`, adotando esse worktree ou recriando.
- O `.env` usa `app.baseURL = 'http://agenda.localhost/'`. No worktree, vira
  `http://<nome>.agenda.localhost/`.
- As views referenciam assets como `base_url('public/assets/...')`. Confirme com
  um teste real que os assets carregam no vhost novo.
- O `web.config` é arquivo do servidor de produção (IIS). **Nunca tocar.**

## Instalação e desenvolvimento

- Não há `pip` nem `pipx` no Python do sistema; usamos `uv`.
- Dev: `uv sync`, depois `.venv/bin/pytest`, `.venv/bin/mypy`, `.venv/bin/ruff check .`
  e `.venv/bin/ruff format .`.
- PATH: `uv tool install -e . --python /usr/bin/python3.12` instala `~/.local/bin/wtp`
  em modo editável, então mudanças no código valem na hora.
- Config: `wtp generate-config` dentro do checkout do projeto (ou copie o
  `config.example.toml`).
- Estado: `~/.local/state/wtp/worktrees/<projeto>-<nome>.json` é o manifesto do que o
  wtp criou (é dele que o `rm` lê o que desfazer); `~/.local/state/wtp/locks/` guarda
  os locks.
- Skill dos agentes: `skills/wtp/SKILL.md`, com symlink em `~/.claude/skills/wtp` e
  `~/.codex/skills/wtp`. Mudou o comportamento da CLI? Atualize a skill no mesmo PR.

## Armadilhas já conhecidas

- **Banco compartilhado.** Todos os worktrees usam o mesmo banco do `.env`. Uma
  migration rodada numa branch de feature muda o esquema para todos. O `wtp`
  deve avisar quando a branch tiver migrations que o main não tem
  (`app/Database/Migrations/`), e aceitar um override de banco.
- **`git stash` é compartilhado** entre worktrees. A ferramenta nunca usa stash.
- **Permissão do `writable/`.** Precisa ser gravável pelo usuário do pool do
  PHP-FPM. Descubra o usuário lendo `/etc/php/<v>/fpm/pool.d/*.conf`, não
  presuma `www-data`.
- **`sudo`.** Reload e escrita em `/etc/apache2` exigem root. Agrupe tudo numa
  única chamada de `sudo` por operação, ou documente uma regra de sudoers
  restrita aos comandos necessários.
- **Login por host:** cada worktree tem cookie de sessão próprio. É esperado.
- **Idempotência:** rodar `new` duas vezes, ou `rm` num worktree meio criado,
  não pode quebrar. Detecte o estado e complete ou limpe.
- **Config local ignorada pelo git.** No outserv_agenda, `app/Config/Constants.php`
  (credenciais do banco) e `app/Config/App.php` são ignorados pelo git, e o worktree
  nasce sem eles: HTTP 500 com `Failed opening required .../Constants.php`. Por isso
  existe `copy_files` no config. Veja o que falta com
  `git ls-files --others --ignored --exclude-standard --directory`.
- **`git branch -d` compara com o HEAD do checkout principal**, não com a base de
  onde a branch saiu. Uma branch nova sem nenhum commit falhava no `rm
  --delete-branch` porque o main checkout estava em outra branch. O wtp guarda
  `base_ref` no manifesto e só apaga se `merge-base --is-ancestor branch base_ref`,
  usando `update-ref -d` com o sha esperado. Nunca `-D`.
- **A raiz do agenda responde 307** para `/acesso/login`, e não 200 nem 302. O doctor
  aceita 2xx e 3xx, segue um redirect no mesmo host e confere se os links de
  `/assets/` apontam para o host do worktree (baseURL errado aparece aqui).
- **`vendor/` é versionado** no outserv_agenda, então lá o `composer install` quase
  nunca roda. No produto-main (Laravel) não é, e roda em todo `new`.
- **Composer com o PHP errado.** O `package:discover` do Laravel roda dentro do
  `composer install`, com o mesmo PHP do composer. O wtp roda `php<versão> composer`,
  com a versão do projeto, e não o `php` padrão da máquina.
- **Pastas do Laravel antes do composer.** `storage/framework/{views,sessions}` são
  ignoradas pelo git e não vêm no worktree; sem elas o `package:discover` falha com
  `Please provide a valid cache path`. O `ensure_dirs` cria essas pastas antes do
  composer. O manifesto guarda só a pasta mais alta que faltava, e o `rm` só apaga
  pastas vazias dentro dela, para não levar junto o que já existia.
- **Composer interrompido.** Um `composer install` que falha deixa `vendor/` pela
  metade. O manifesto marca `composer_running` e o próximo `new` roda de novo.
- **Estilo do `.env`.** CodeIgniter usa `app.baseURL = 'x'`, Laravel usa `APP_URL=x`.
  A reescrita mantém espaços e aspas da linha original; chave nova segue o estilo da
  maioria das linhas.
- **Vários agentes ao mesmo tempo.** `git fetch` e `git worktree add` em paralelo no
  mesmo repo brigam pelos locks de ref; o reload do Apache também. O wtp serializa
  essas etapas com `flock` (um lock por projeto para git, um global para Apache).
  Testado com três `new` e três `rm` simultâneos.
- **Host sem vhost cai no checkout principal.** Um `*.agenda.localhost` sem vhost
  próprio (nome errado, worktree removido) cai no primeiro vhost da máquina
  (`agenda.local.conf`) e responde normalmente com o código do main. Um 200 não
  prova nada; quem prova é a checagem de assets do doctor. Um vhost catch-all que
  devolva 404 resolveria, mas mexeria na ordem dos vhosts existentes: decisão do
  usuário.
- **Tudo que vai para o sudo, o git ou o vhost passa por `wtp/core/validation.py`.**
  Branch com `-` na frente virava opção do `git worktree add` (`--branch=--force`);
  `copy_files`/`writable_dir` com `..` saíam do worktree (e o `writable_dir` vai para
  um `chgrp -R` como root); `domain` e caminhos entram crus no vhost. O `rm` também
  confere que cada arquivo do manifesto fica dentro do worktree antes de apagar.
- **`chgrp -R` segue symlink por padrão.** Um symlink versionado em `writable/`
  apontando para `/etc` levava o chgrp (root) para fora. Use sempre `-h -P`.
- **O guard do Python não basta.** Os scripts que rodam com sudo revalidam o prefixo
  `wtp-` e a marca na primeira linha do `.conf`. Eles têm teste real em
  `tests/adapters/test_sudo_scripts.py`, com os comandos do Apache trocados por stubs.
- **Nem todo projeto guarda a URL base igual.** O wtp só reconhece `app.baseURL`
  (CodeIgniter 4) e `APP_URL` (Laravel). Fora disso, não chuta: devolve a tarefa para
  o **agente**, não para o usuário. O `generate-config` põe em `agent_tasks` onde
  procurar e com qual flag rodar de novo; o `new` com `base_url_key` vazio não mexe
  na URL e avisa com um warning que começa com "Agente:". O usuário só é chamado
  quando o código do projeto não mostra a resposta.
- **Framework por triangulação, não por um sinal só.** O agenda não tem
  `codeigniter4/framework` no composer.json (o `system/` é versionado), então um
  detector baseado só no composer erraria. O wtp cruza composer.json, arquivo de
  entrada (`spark`, `artisan`) e chave do `.env`: dois sinais confirmam, um é palpite,
  sinais de frameworks diferentes viram tarefa para o agente.
- **`*.localhost` e DNS.** O doctor não depende de DNS: conecta em 127.0.0.1:80
  mandando o header `Host`.
- **O hook anti-vibe-coding bloqueia comandos** em que apareçam `git branch` e `-D`
  na mesma linha, mesmo que o `-D` seja de outro comando (por exemplo `curl -D -`).
  Separe os comandos.

## Estrutura

Camadas: cada pasta só importa as de baixo (`core` não importa nada do wtp fora dele).

```
worktree-php-manager/
  pyproject.toml          # entry point: wtp = wtp.cli:main
  config.example.toml     # molde do ~/.config/wtp/config.toml
  skills/wtp/SKILL.md     # skill global dos agentes (Claude Code e Codex)
  wtp/
    core/                 # regras puras
      config.py           # leitura e validação do config.toml
      frameworks.py       # perfis de CodeIgniter 4 e Laravel
      validation.py       # tudo que vai para sudo, git ou vhost
      naming.py, envfile.py, manifest.py, errors.py
    adapters/             # efeitos colaterais, cada um atrás de uma classe ou função
      runner.py           # subprocess
      git_ops.py          # worktree add/remove/list, status, branch
      apache.py           # template do vhost e scripts do sudo
      composer.py, fpm.py, permissions.py, http_probe.py, browser.py, locking.py, console.py
    actions/              # o que cada comando faz
      services.py         # junta os adaptadores num lugar só
      provision.py        # new e adopt
      teardown.py         # rm
      listing.py, doctor.py, locate.py
    detection/            # generate-config
      triangulate.py      # descobre o framework por três sinais
      detect.py           # monta o ProjectConfig e as agent_tasks
      config_writer.py    # acrescenta o projeto ao config.toml
    cli/
      parser.py           # argparse
      commands.py         # um handler por subcomando
      main.py             # main(), erros sem traceback
  tests/                  # mesmas pastas de wtp/
    fakes.py              # ScriptedRunner, FakeGitWorld, FakeApacheHost, CannedHttpProbe
```
