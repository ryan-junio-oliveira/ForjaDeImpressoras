# Forja de Impressoras v1.0.0

**A ferramenta que varre a rede, encontra as impressoras de verdade e instala o
driver certo do modelo — sem nunca cair no driver genérico do Windows.**

> **Status:** Lançada (versão estável 1.0.0)
> **Histórico completo:** [`CHANGELOG.md`](CHANGELOG.md)
> **Versão:** `1.0.0`

---

## O que a Forja de Impressoras faz

- Varre a rede local e **só lista o que é impressora de verdade** (combina SNMP,
  ARP, portas RAW/IPP/LPD, página do EWS e device-id IPP — e descarta
  servidores com CUPS ou com função Servidor de Impressão)
- Reconhece também **impressoras USB** plugadas no computador
- Resolve o **driver PCL específico do modelo exato** (HP LaserJet E52645,
  Brother HL-L5100DN, Epson EcoTank L5590…) — baixando do site do fabricante
  quando preciso, com verificação de checksum
- Instala no Windows (driver → porta → fila) e **imprime a página de teste**
- Remove impressoras, portas órfãs e drivers não utilizados, com proteção
  (nunca toca em porta em uso nem em porta de sistema)

## Novidades desta versão

### Interface nova

- Tela enxuta com o caminho sempre visível: **varrer → marcar → instalar**
- Tema claro e escuro, paleta semântica (verde, vermelho, amarelo) para
  confiança do modelo, origem do driver e situação
- Detalhes e registro em painéis laterais que só aparecem quando você precisa
- Roda como **janela desktop nativa** (a web embarcada, sem abrir o navegador)
  padrão** — você escolhe no botão da própria janela

### Impressoras USB

- A tool agora enxerga as impressoras plugadas via USB
- Casa o driver pelo identificador de hardware do próprio aparelho, então
  instala o driver exato do modelo, não um genérico

### Build e instalação

- `scripts\build.bat` gera o executável e o instalador (Inno Setup) num comando
- Instalador com atalho no menu Iniciar e na área de trabalho

## Instalação

1. Execute `scripts\build.bat` (gera `dist\windows\ForjaDeImpressorasSetup.exe`)
2. Instale e abra pelo atalho — o programa pede elevação de administrador
   (necessário para instalar impressoras)

### Rodando direto do código

```bat
pip install -r requirements.txt
run.bat                 :: híbrido desktop (eleva para Administrador)
python main.py --scan 192.168.15.0/24
```
