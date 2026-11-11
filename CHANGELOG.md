# Changelog — Forja de Impressoras

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
