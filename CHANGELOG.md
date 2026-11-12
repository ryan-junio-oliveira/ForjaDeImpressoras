# Changelog — Forja de Impressoras

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.4] — 2026-11-12

### Corrigido (som fantasma sem ação do usuário)
- Replay do SSE re-enviava `done` antigos a cada (re)conexão: abrir a página
  (ou qualquer reconexão) re-tocava fanfarra/game-over e reabria toasts de
  operações passadas. `done` não é mais repetido; de `busy` só o estado atual

## [1.1.3] — 2026-11-12

### Corrigido (varredura congelando no ping + spam `Bad file descriptor`)
- **Ping sem pipes**: `ping_host` só usa o returncode, agora com `DEVNULL`
  em vez de `capture_output` — elimina as reader-threads e o travamento sob
  dezenas de `ping.exe` simultâneos no Windows
- **Coleta com teto**: `_drain()` com heartbeat a cada 5s sem conclusão,
  prazo total por etapa e `shutdown(wait=False)` — nenhum futuro preso
  congela a varredura; IPs não-varríveis (multicast/loopback/inválidos)
  são pulados antes de spawnar processo
- **Filtro de ruído**: `threading.excepthook` instalado no `main.py` engole
  somente o `OSError 9` da `_readerthread` do `subprocess`; resto passa normal

## [1.1.2] — 2026-11-12

### Alterado
- **`run.bat` mínimo** (10 linhas): só garante admin e roda
  `python main.py --mode desktop`. Sem modos, sem repasse de args, sem `for`
  — escaneamento e servidor via `python main.py` direto. CRLF garantido
  (LF puro abortava o cmd com "... foi inesperado neste momento")
- **Tema padrão agora é Oficina Industrial** (carvão + laranja segurança,
  faixa zebrada, fonte Oswald) no lugar do steampunk; quem tinha steampunk
  salvo migra sozinho
- **Música medieval de verdade** (arquivos em `static/audio`, funciona offline):
  rádio menestrel (3 loops sorteados sem repetição, emenda automática),
  2 fanfarras sorteadas no sucesso, dobrado fúnebre irregular na falha
  e sino com pitch aleatório nos cliques; bonecos emoji removidos.
  Créditos no README (Kevin MacLeod, CC-BY 3.0)
- **Temas Arcano e Cyber removidos**: ficam só Oficina Industrial (padrão) e
  Paladino; quem tinha os antigos salvos migra sozinho para o Industrial
- **Botão de som corrigido**: mutar agora pausa na hora o loop e qualquer
  faixa em voo (`setSoundEnabled` centralizado); desmutar retoma o loop se
  a operação continua — antes o mudo ignorava o que já tocava

## [1.1.1] — 2026-11-12

### Corrigido (`run.bat` não executava o app como admin)
- **Elevação quebrava os argumentos**: `-ArgumentList '%*'` ia como UMA string
  só (cmd não entende aspas simples) e com `%*` vazio injetava um argumento
  fantasma `''` — o app elevado recebia `scan 192.168...` como modo único ou
  `main.py --mode desktop ''` e morria no argparse. Agora cada argumento é
  repassado separado (array PowerShell `'arg1','arg2'`) e sem args não envia
  `-ArgumentList`
- **`run.bat scan <CIDR>` perdia o CIDR**: `:scan` só repassava `%1` e o modo
  `desktop` repassava `%*` cru (duplicava `browser`/`servidor` no argparse).
  Modos agora consomem a própria palavra e repassam só o resto (`TAIL`/`SCAN`);
  múltiplos CIDRs são unidos com vírgula
- **"Python não encontrado" após o UAC**: o PATH do token elevado difere do
  usuário. O Python agora é resolvido pelo caminho completo (`where py`,
  fallback `where python`), com checagem de versão 3.10+
- **`run.bat scan` não pede mais UAC** (varredura é somente-leitura) e
  `FORJA_NO_ELEVATE=1` pula a elevação para depuração
- `pause` só em erro no modo desktop (antes prendia o console após fechar a GUI);
  `servidor` repassa `--port` e demais flags
- **`.bat` com LF puro abortava no cmd** (`... foi inesperado neste momento`):
  `run.bat` e `scripts/build.bat` normalizados para CRLF; detecção do Python
  refeita sem parênteses dentro do `IN (...)` do `for` (via `where py`),
  que era outro gatilho do mesmo erro

## [1.1.0] — 2026-11-12

### Corrigido (bloco 1 — bugs críticos)
- `is_admin` retornava sempre True; agora interpreta o retorno do PowerShell
- `print_test_page` aceitava qualquer `0` no log; agora exige `ReturnValue = 0`
- `ensure_tcp_port`/`install_printer` com `-ErrorAction Stop` + verificação pós-instalação + backup/rollback da fila antiga
- `free_usb_port` retornava porta ocupada; agora retorna None
- `install_usb_printer` verificava por sniff de texto; agora verifica `USB-OK` + compara driver da fila existente
- `list_printers` quebrava com `WARNING:` antes do JSON; agora extrai substring JSON
- `add_printer_driver`: busca `Install.exe` limitada a 3 níveis, timeout 180s, valida `.inf`
- `driver_manager`: não descarta `.inf` legítimo por header `Microsoft`; regex cobre KX/TASKalfa/ECOSYS/Universal/VersaLink; `resolve_driver` continua para download/inbox quando `.inf` sem nome; `find_inf_by_hardware` filtra por fabricante
- `driver_download`: cache validado por formato quando sem sha256; timeout 30s + retry 3x + valida Content-Type/tamanho; ZipSlip; threshold score >= 4; UTF-16; propaga progresso/cancelamento
- `scanner`: hostname `HP*` não classifica mais laptop como impressora; sort tolerante a IP inválido; `check_single_ip` valida IP; checagem de portas de servidor quando sem 9100
- `network`: `parse_cidrs` com `validate_cidrs` (retorna inválidos); redes `/8-/12` não são mais descartadas silenciosamente
- `snmp`: trata `NoSuchObject/Instance/EndOfMib`, ignora error-status != 0
- `usb`: normaliza `Hewlett-Packard->HP`, fallback `USBPRINT*/VID_*`
- `api.start_test_page`: match exato (evita `192.168.1.5` casar `192.168.1.50`)
- `config`: escrita atômica + lock; `paths.drivers_dir` com fallback gravável em dev; `instance_mutex` sem vazar handle

### Adicionado (bloco 2 — cancelamento e concorrência)
- Botão Cancelar + `POST /api/cancel` + `cancel_event` em scan/download/extract/install/remove/resolve
- `State` com `Lock`; `try_begin/finish`; mutações de `printers/checked` sob lock
- `test-ip/resolve` bloqueados durante operação; `snapshot` com cache admin/networks (TTL 30s)
- Remoção de drivers escopada aos drivers selecionados (não mais varredura global)
- `open_drivers_folder` multiplataforma com erro tratado

### Adicionado (bloco 3 — steampunk, bonecos e música)
- Tema `steampunk` padrão (latão/couro/rebites, fontes Rye/Special Elite), mantém arcane/cyber/paladin
- Bonecos CSS puros em `#runner-layer`: 3 ao varrer, 5 ao forjar, celebração no `done`; respeita `prefers-reduced-motion`
- `SoundFx` chiptune procedural original (sem sample protegido): scanLoop, coin, hammer, fanfarra, game-over; throttle de ticks
- Acessibilidade: `role=progressbar/checkbox`, `aria-live`, `focus-visible`, teclado Enter/Espaço nos cards

## [1.0.0] — 2026-11-11

### Corrigido (revisão pós-instalação em outro PC)
- **Navegador abrindo sozinho (removido por completo)**: o modo desktop
  abria a janela nativa E uma aba no navegador padrão; o botão nativo
  "Abrir no navegador" abria mais janelas a cada clique; e a
  `QWebEnginePage` repassava páginas internas de erro ao navegador.
  Política nova: **interface somente na janela desktop** — removidos o
  botão, o `--mode browser`, a flag `--no-browser` e qualquer chamada a
  `webbrowser/os.startfile`; navegações não-locais são descartadas
- **Fechar a janela deixava o app vivo**: `closeEvent` agora desmonta a
  WebView (`stop()` + `setPage(None)`) antes de fechar, o servidor
  embutido recebe `shutdown()` + `server_close()`, a thread é aguardada
  e, se insistir em viver, o processo é encerrado (`os._exit`)
- **Dezenas de janelas de console piscando durante a varredura**: todo
  `subprocess` do motor (`ping`, `arp`, `ipconfig`, PowerShell, `pnputil`,
  extratores) agora usa `CREATE_NO_WINDOW` via `app/platform/process.py`;
  teste automatizado garante que nenhum módulo chame `subprocess` direto
- **"Abrir no navegador" abria um monte de janelas**: a `QWebEnginePage`
  anterior repassava *qualquer* navegação não-local ao navegador —
  inclusive as páginas internas de erro do Chromium durante o retry de
  carregamento. Agora só `http(s)` com host e em frame principal abre o
  navegador; `about:`/`chrome:`/`data:`/`blob:` são bloqueados
- **Modo desktop abria a janela nativa E o navegador juntos**: agora o
  navegador só abre se o usuário clicar em "Abrir no navegador"
  (`--mode server`/`browser` continuam abrindo, como esperado)
- **Resolução de driver sobrescrevia o driver USB**: impressoras USB já
  chegam com o driver resolvido por HardwareID; o loop de resolução
  (scan e re-resolver) agora preserva isso em vez de aplicar o caminho
  de rede
- **Escritas em pasta somente-leitura** (instalação em `Program Files`):
  `ultimo_scan.json`, logs de instalação e pasta `drivers/` agora caem
  em `%LOCALAPPDATA%\ForjaDeImpressoras` quando a pasta do app não é
  gravável; extrator de `.exe` limitado a switches silenciosos
- **Qt interpretava argumentos do app** (`--help`, `--port`): agora a
  `QApplication` recebe só `argv[0]`
- **Janela duplicada**: instância única via mutex nomeado no modo desktop
- **Build travava com app aberto**: `build.bat` agora detecta
  `ForjaDeImpressoras.exe` em execução e orienta antes de falhar no meio
- **Ao abrir, impressora conhecida aparecia "sem driver"**: o boot
  re-resolvia com download proibido e o `ultimo_scan.json` era salvo
  *antes* da resolução. Agora o boot resolve com download permitido
  (usa o cache local) e o arquivo é regravado *após* a resolução —
  reabrir mostra o driver certo na hora, sem novo scan
- **Preferência "baixar driver" não persistia**: agora é salva em
  `%APPDATA%` e aplicada na abertura seguinte

### Adicionado
- **Instalador (Inno Setup 6)** com atalho no menu Iniciar e na área de trabalho,
  exigência de **Administrador** (necessário para instalar impressoras) e
  **desinstalação livre** (sem senha de administrador)
- **Suporte a impressoras USB**: detecção pela classe PnP `Printer`
  (`Get-PnpDevice`), com `DeviceID` e `HardwareIDs` (`USB\PRINTER_PROVIDER\...`,
  `USBPRINT\...`). Resolução do driver por casamento exato de hardware id no
  `.inf` do fabricante e instalação via `pnputil` → `Add-PrinterDriver` →
  `Add-Printer` na porta `USB00x` livre → página de teste
- **Interface web em Bootstrap 5.3** (vendorizado em `app/presentation/static`,
  sem CDN — funciona em rede isolada) com tema claro/escuro, KPIs, tabela de
  impressoras, painel de detalhes e registro em tempo real via SSE
- **Híbrido desktop**: janela nativa PySide6 (`QWebEngineView`) que renderiza a
  a interface web local, no mesmo padrão do HyperViewerTotem; botão nativo
  “Abrir no navegador padrão” na barra da janela
- **Servidor local seguro**: escuta apenas em `127.0.0.1`, exige token de sessão
  (cookie `HttpOnly`) e valida o `Host` (proteção contra DNS rebinding)
- **Build automatizado**: `scripts/build.bat` (dependências → limpeza → ícone →
  spec → PyInstaller → Inno Setup), `scripts/gen_spec.py`, `scripts/gen_icon.py`
  e `setup/windows/ForjaDeImpressorasSetup.iss`
- **Documentação de release**: `VERSION` (fonte única da versão), `CHANGELOG.md`
  e `new_version.md`
- **CLI completa**: `--scan`, `--test-ip`, `--install`, `--remove-all`,
  `--mode desktop|browser|server`, `--port`, `--version`

### Alterado
- **Estrutura de pastas reorganizada** no padrão HyperViewerTotem/HyperViewerDesktop:
  `app/core` (motor), `app/data` (dados e caminhos), `app/platform` (Windows),
  `app/presentation` (interface), `app/resources` (ícone)
- **Versão centralizada no arquivo `VERSION`**: `app/__init__.py` lê o arquivo em
  runtime (`0.0.0-dev` só quando ausente); `build.bat` aborta sem `VERSION`; o
  `.iss` exige `/DAppVersion` e falha em vez de embutir número fixo
- Interface redesenhada: caminho de uso em 3 passos (varrer → marcar → instalar),
  detalhes e registro em painéis laterais sob demanda, paleta semântica
  (verde/vermelho/amarelo) para confiança, origem do driver e estado

### Corrigido
- **`QPainter` não encerrado** ao gerar o ícone do app: o `p.end()` faltante
  provocava `abort()` no runtime do C (`ucrtbase.dll`, `0xc0000409`) na abertura
  da janela desktop
- **Pacote de driver re-extraído a cada varredura**: `extract_pack` agora
  reaproveita a pasta já extraída (`./drivers/_downloads/<pack_id>/`)
- **Driver USB genérico nunca é instalado**: drivers de fabricante com PCL
  específico são obrigatórios; caso contrário a impressora fica *pendente*

### Removido
- Interface Tkinter original e a dependência `customtkinter` (o projeto volta a
  **zero dependências** no núcleo; só o modo desktop exige `PySide6`)
- Arquivos soltos e logs na raiz (`instalacao_*.log`, `ultimo_scan.json`,
  `ui_config.json`, `__pycache__`) — logs agora vão para `logs/`
