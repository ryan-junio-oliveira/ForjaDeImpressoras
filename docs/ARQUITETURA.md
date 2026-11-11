# Arquitetura — Forja de Impressoras

Documento técnico da estrutura, dos fluxos e das decisões de projeto.

## Visão geral

O app é dividido em quatro camadas, com responsabilidades isoladas:

```
        ┌─────────────────────────────────────────────┐
        │            app/presentation                 │
        │  desktop.py (PySide6)  ·  server.py (HTTP) │
        │  api.py (ponte + eventos)  ·  static/ (UI)  │
        └───────────────────┬─────────────────────────┘
                            │  chama
        ┌───────────────────▼─────────────────────────┐
        │                 app/core                    │
        │  scanner · usb_scanner · model_identifier   │
        │  driver_manager · driver_download           │
        │  printer_install · network · snmp_client    │
        └───────────────────┬─────────────────────────┘
                            │  lê
        ┌───────────────────▼─────────────────────────┐
        │                 app/data                    │
        │  paths (recursos x gravável) · config       │
        │  driver_packs.json · drivers_catalog.json    │
        └─────────────────────────────────────────────┘

        app/platform  →  instance_mutex · elevation
```

`app/platform` é transversal (instância única e elevação), por isso fica fora
da cadeia de chamadas.

## Fluxo de uma instalação

```
1. Varredura
   scanner.scan_network(cidrs)
     ├─ expand_targets()      → lista de IPs (sub-redes reais via ipconfig + ARP)
     ├─ ping sweep            → hosts vivos (0–50% da barra)
     └─ scan_host()           → portas + SNMP + EWS + IPP (50–100%)
           └─ classify_host() → score ≥ 2 e sem evidência de servidor

2. Impressoras USB (PnP)
   usb_scanner.list_usb_devices()   → classe Printer + HardwareIDs
   usb_scanner.match_queue()       → fila já instalada?

3. Resolução do driver
   driver_manager.resolve_driver()      (rede)
   driver_manager.resolve_usb_driver()  (USB, por HardwareID)
     1) .inf local  2) inbox exato  3) download do pack  4) inbox do fabricante
     5) pendente — NUNCA genérico

4. Instalação
   printer_install.full_install()        (rede: pnputil → driver → porta → fila → teste)
   printer_install.install_usb_printer() (USB:  pnputil → driver → porta USB → fila → teste)
```

## Threading

- O **processo principal** hospeda o loop de eventos (Qt) ou o `serve_forever()`.
- Todo trabalho pesado (varredura, download, instalação) roda em **threads de
  fundo** — nunca no loop principal.
- A comunicação thread → UI é feita por um **event bus** (`api.EventBus`):
  - o servidor HTTP assina a fila e repassa os eventos via **SSE**;
  - o frontend consome com `EventSource` e atualiza a tela.
- Nenhum componente de UI é tocado a partir de thread de trabalho.

## Segurança

| Ameaça | Mitigação |
|---|---|
| Outro site local acionar o instalador | token de sessão + cookie `HttpOnly` + `SameSite=Strict` |
| DNS rebinding | validação do header `Host` (só `127.0.0.1`/`localhost`) |
| Exposição na rede | servidor escuta **apenas** em `127.0.0.1` |
| Dois instaladores simultâneos | `app/platform/instance_mutex.py` (mutex nomeado) |
| Driver genérico | `driver_manager.is_generic_name()` validado no scan **e** na instalação |
| Executar sem privilégio | `run.bat` eleva; a API recusa instalar sem admin |

## Dados graváveis vs. recursos

| Tipo | Empacotado | Dev | Empacotado (instalado) |
|---|---|---|---|
| `driver_packs.json`, `drivers_catalog.json` | sim (read-only) | `app/data/` | dentro do .exe |
| interface web (`static/`) | sim (read-only) | `app/presentation/static/` | dentro do .exe |
| `icon.ico` | sim (read-only) | `app/resources/` | dentro do .exe |
| `drivers/` (.inf do TI + cache) | não | `./drivers/` | ao lado do .exe |
| `logs/` | não | `./logs/` | `%LOCALAPPDATA%\ForjaDeImpressoras\logs` |
| `config.json` | não | `%APPDATA%` | `%APPDATA%\ForjaDeImpressoras` |

A distinção está centralizada em `app/data/paths.py`.

## Frontend

- **Bootstrap 5.3 vendorizado** em `app/presentation/static/vendor/` — sem CDN,
  funciona em rede isolada.
- Tema claro/escuro via `data-bs-theme` (Bootstrap 5.3) + `localStorage`.
- Paleta semântica: **verde** (confiança alta / origem OK), **amarelo**
  (confiança média / pendência), **vermelho** (erro / sem driver), **azul**
  (ação primária).
- A lista é renderizada por JavaScript a partir dos eventos SSE; o contrato
  entre backend e frontend é o dicionário serializado em `api._public()`.

## Build

`scripts/build.bat` executa o fluxo completo e é idempotente:

```
deps (requirements.txt + pyinstaller)
  → VERSION (abortar se ausente)
  → limpeza (dist, build, __pycache__, logs)
  → gen_icon.py  (app/resources/icon.ico)
  → gen_spec.py  (build/windows/ForjaDeImpressoras.spec)
  → pyinstaller  (dist/windows/ForjaDeImpressoras.exe)
  → ISCC /DAppVersion=<VERSION>  (dist/windows/ForjaDeImpressorasSetup.exe)
```

O `.spec` embute recursos, interface web e dados como `datas`, mantendo o
`QtWebEngine` (excluído do `excludes` para não quebrar a interface).
