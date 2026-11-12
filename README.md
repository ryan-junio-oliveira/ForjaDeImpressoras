# Forja de Impressoras

Ferramenta de TI que **varre a rede, identifica impressoras reais, resolve o driver
PCL específico do modelo e instala no Windows** — com interface web moderna
(Bootstrap 5) em modo **híbrido**: janela desktop nativa que renderiza a web local,
A interface aparece SOMENTE na janela desktop — nenhum fluxo abre o navegador.

> Regra de ouro: **nunca** instala driver genérico (`Microsoft IPP Class Driver`,
> `Print to PDF`, `Generic / Text Only`…). Se não há driver PCL do modelo exato,
> a impressora fica **pendente** com a orientação do que baixar.

**Versão:** [`VERSION`](VERSION) · **Release:** [`new_version.md`](new_version.md) ·
**Histórico:** [`CHANGELOG.md`](CHANGELOG.md)

---

## Como usar

```bat
run.bat                      :: janela desktop (recomendado) — eleva para Admin
```

Modos extras direto no Python (sem elevação automática):

```bat
python main.py --mode server    :: só sobe o servidor local (desenvolvimento)
python main.py --scan [CIDR]    :: varredura pela linha de comando
python main.py --help           :: todas as opções
```

**O fluxo da tela é sempre o mesmo:**

1. **Varrer rede** — varre as sub-redes locais (ou um CIDR informado) e detecta
   impressoras de rede **e** impressoras **USB** conectadas.
2. **Marcar** — clique na caixa de seleção das impressoras desejadas.
3. **Instalar selecionadas** — registra o driver, cria a porta e a fila, e imprime
   a página de teste.

Detalhes de cada impressora ficam em um painel lateral sob demanda; o registro
completo da execução fica no botão **Registro**.

### Linha de comando

```bat
python main.py --scan                          :: varre as sub-redes locais
python main.py --scan 192.168.15.0/24          :: varre um CIDR
python main.py --scan 192.168.15.0/24,10.0.0.0/24
python main.py --test-ip 192.168.15.50         :: testa um host
python main.py --install 192.168.15.50 --driver "HP LaserJet M404 PCL6" [--inf C:\drv\hp.inf]
python main.py --remove-all [--include-virtual] [--remove-drivers]
python main.py --version
```

---

## Estrutura

```
main.py                     entrada: CLI + sobe a interface (desktop / servidor)
VERSION                     fonte única da versão (lida por app/__init__.py)
CHANGELOG.md                histórico de versões
new_version.md              notas de release
run.bat                     inicializador elevado (modo desktop)

app/
  __init__.py               __version__ lida do VERSION
  core/                     motor
    network.py              sub-redes reais via ipconfig, expansão de CIDR
    snmp_client.py          SNMP v1/v2c implementado à mão (sem pysnmp)
    scanner.py              varredura de rede: ping sweep + ARP + portas + SNMP + EWS + IPP
    usb_scanner.py          detecção de impressoras USB (PnP, classe Printer)
    model_identifier.py     modelo canônico + confiança (alta/média/baixa)
    driver_manager.py       resolve o driver PCL específico (bloqueia genéricos)
    driver_download.py      baixa o pack do fabricante, confere sha256, extrai
    printer_install.py      instalação (rede e USB) + página de teste + remoção
  data/                     dados e caminhos
    paths.py                recursos (somente-leitura) x pasta gravável
    config.py               configuração persistida (%APPDATA%)
    driver_packs.json       URLs/checksums dos packs por fabricante
    drivers_catalog.json    links oficiais por fabricante
  platform/                 integração Windows
    instance_mutex.py       instância única
    elevation.py            elevação para Administrador
  presentation/             interface
    api.py                  ponte entre a API HTTP e o motor + eventos ao vivo
    server.py               servidor HTTP local (SPA + API JSON + SSE), só em 127.0.0.1
    desktop.py              janela PySide6 (QWebEngineView) que renderiza a web local
    static/                 Bootstrap 5.3 + ícones vendorizados + app.css + app.js
  resources/
    icon.ico                ícone multi-resolução (gerado por scripts/gen_icon.py)

scripts/
  build.bat                 build completo: deps → limpeza → ícone → spec → PyInstaller → Inno Setup
  gen_spec.py               gera o .spec do PyInstaller
  gen_icon.py               gera o icon.ico (sem dependências)
setup/windows/
  ForjaDeImpressorasSetup.iss  instalador (Inno Setup 6)
docs/                       documentação técnica
tests/                      testes de fumaça (sem rede, sem privilégio)
drivers/                    .inf do TI + cache de downloads
logs/                       logs de execução
```

### Segurança do servidor local

- Escuta **apenas em 127.0.0.1** (nunca na rede).
- Exige um **token de sessão** por URL; a API exige cookie `HttpOnly` ou header
  `X-Auth-Token`. Outro site aberto na máquina não consegue acionar o instalador.
- O `Host` é validado (evita *DNS rebinding*).

---

## Varredura de rede

- **Sub-redes reais** via `ipconfig` (não assume `/24`) + ARP local.
- **Portas**: 9100 RAW / 515 LPD / 631 IPP / 161 SNMP / 80-443 HTTP.
- **Anti-falso-positivo**: 631 e 515 sozinhas **não** valem (servidor com CUPS ou
  Windows com função Servidor de Impressão). Exige score ≥ 2 em sinais
  independentes (9100, MIB SNMP, modelo no EWS, modelo IPP em `/ipp/print`,
  device-id `MFG/MDL`, hostname JetDirect) e **veta** servidores (SMB/RPC/RDP,
  header `CUPS`, SO servidor) sem evidência de hardware.
- **Validação SNMP**: `sysDescr`, `sysObjectID`, `hrDeviceDescr`,
  `prtGeneralPrinterName/Serial` + título HTTP do EWS → fabricante e modelo exato.

## Impressoras USB

Detecção pela classe PnP `Printer` (`Get-PnpDevice`), com **HardwareIDs** e
`DeviceID` (`USB\PRINTER_PROVIDER\...`, `USBPRINT\...`).

Ordem de resolução do driver USB:

1. Fila já instalada no Windows (driver em uso).
2. `.inf` local que casa com os **HardwareIDs** do dispositivo.
3. Download do pack do fabricante → `.inf` que casa com os HardwareIDs.
4. Driver PCL do fabricante já presente no Windows.
5. **Pendente** — nunca genérico.

Instalação: `pnputil /add-driver` (driver PnP + criação da porta USB) →
`Add-PrinterDriver` → `Add-Printer` na porta `USB00x` livre → página de teste.

## Resolução do driver (rede)

1. `.inf` local em `./drivers/` (pacote do modelo extraído pelo TI).
2. Driver do Windows que casa com o **modelo exato** (ex.: `HP LaserJet MFP E52645 PCL-6 (V4)`).
3. **Download automático** do pack PCL do fabricante (`driver_packs.json`, com
   sha256 verificado; cache em `./drivers/_downloads/`).
4. Driver PCL do fabricante no inbox do Windows.
5. **Pendente** — orienta o download; nenhum genérico é usado.

## Remoção

- Lista as impressoras instaladas no computador.
- Opções: manter virtuais (PDF/XPS/Fax), remover portas de rede órfãs
  (`TCPIPE:`, `IP_*`, `WSD*`, IP puro) e remover drivers órfãos.
- **Proteções**: porta em uso por outra impressora nunca é removida; portas de
  sistema (USB/LPT/COM/FILE/PORTPROMPT) nunca são tocadas.

---

## Build

```bat
scripts\build.bat
```

Fluxo: dependências → limpeza → `gen_icon.py` → `gen_spec.py` → PyInstaller
(`dist\windows\ForjaDeImpressoras.exe`) → Inno Setup
(`dist\windows\ForjaDeImpressorasSetup.exe`).

O instalador pede **Administrador** (necessário para instalar impressoras) e cria
atalho no menu Iniciar e na área de trabalho.

### Testes

```bat
python tests\test_smoke.py
```

## Creditos de audio (CC-BY 3.0)

Musica medieval vendorizada em `app/presentation/static/audio/`:

- `minstrel.mp3` — "Minstrel Guild", Kevin MacLeod (incompetech.com),
- `lord.mp3` — "Lord of the Land", Kevin MacLeod (incompetech.com),
- `celtic.mp3` — "Celtic Impulse", Kevin MacLeod (incompetech.com),
- `fanfare.mp3` — "The Rule", Kevin MacLeod (incompetech.com),
- `mighty.mp3` — "Mighty and Meek", Kevin MacLeod (incompetech.com).
  Todas acima licenciadas em Creative Commons Attribution 3.0 (`CC BY 3.0`).
- `bell.ogg` — sino de bronze, domínio público (PDSounds, via Wikimedia Commons).

## Requisitos

- Windows 10/11, Python 3.10+.
- **Administrador** para instalar (`run.bat` eleva automaticamente).
- `PySide6` (QtWebEngine) e obrigatorio para a janela desktop.
- O núcleo (CLI + API web) usa **somente a biblioteca padrão**.
