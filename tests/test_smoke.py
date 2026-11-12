"""
Testes de fumaca da Forja de Impressoras.

Executa sem rede e sem Windowsprivilegiado: valida imports, regras de
seguranca do driver, caminhos e a API do servidor.

Uso:
    python -m tests.test_smoke
    python tests/test_smoke.py
"""
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import __version__                                   # noqa: E402
from app.core import (driver_manager, model_identifier,       # noqa: E402
                      printer_install, scanner)
from app.core import usb_scanner                             # noqa: E402
from app.data import config, paths                           # noqa: E402


class TestCaminhos(unittest.TestCase):
    def test_base_existe(self):
        self.assertTrue(paths.base_dir().exists())

    def test_packs_disponiveis(self):
        self.assertTrue(paths.PACKS_JSON.exists(), "driver_packs.json ausente")
        self.assertTrue(paths.CATALOG_JSON.exists(),
                        "drivers_catalog.json ausente")

    def test_interface_web_presente(self):
        self.assertTrue((paths.STATIC_DIR / "index.html").exists())
        self.assertTrue((paths.STATIC_DIR / "app.css").exists())
        self.assertTrue((paths.STATIC_DIR / "app.js").exists())

    def test_bootstrap_vendorizado(self):
        vendor = paths.STATIC_DIR / "vendor"
        self.assertTrue((vendor / "bootstrap.min.css").exists(),
                        "Bootstrap nao vendorizado (interface quebrada offline)")

    def test_mudo_corta_tudo_e_retoma(self):
        # Regressao: mutar precisa pausar loop + one-shots em voo, e
        # desmutar retoma o loop se a operacao continua (wantLoop).
        # Checa o contrato no fonte (unico ponto de troca do estado).
        js = (paths.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("function setSoundEnabled(on)", js)
        self.assertIn("live.add(el)", js)
        self.assertIn("live.forEach((el)", js)
        # botao e init passam pelo contrato, sem mexer no estado direto
        self.assertIn("SoundFx.setSoundEnabled(!S.soundEnabled)", js)
        self.assertIn(
            "SoundFx.setSoundEnabled(localStorage.getItem('rpg-sound')",
            js)
        self.assertNotIn("S.soundEnabled = !S.soundEnabled", js)

    def test_musica_medieval_vendorizada(self):
        # Musica real em /static/audio (funciona offline); cada faixa
        # precisa existir e ter tamanho de audio de verdade.
        audio = paths.STATIC_DIR / "audio"
        faixas = (("minstrel.mp3", (b"ID3", b"\xff\xfb")),
                  ("lord.mp3", (b"ID3", b"\xff\xfb")),
                  ("celtic.mp3", (b"ID3", b"\xff\xfb")),
                  ("fanfare.mp3", (b"ID3", b"\xff\xfb")),
                  ("mighty.mp3", (b"ID3", b"\xff\xfb")),
                  ("bell.ogg", (b"OggS",)))
        for nome, magias in faixas:
            with self.subTest(faixa=nome):
                f = audio / nome
                self.assertTrue(f.exists(), f"{nome} ausente")
                raw = f.read_bytes()
                self.assertGreater(len(raw), 500_000, f"{nome} pequeno demais")
                self.assertTrue(any(raw.startswith(m) for m in magias),
                                f"{nome} nao e audio valido")


class TestSegurancaDriver(unittest.TestCase):
    """Regra de ouro: NUNCA driver generico."""

    GENERICOS = [
        "Microsoft IPP Class Driver",
        "Microsoft Print to PDF",
        "Microsoft XPS Document Writer",
        "Generic / Text Only",
        "Microsoft Shared Fax Driver",
        "OneNote",
    ]

    def test_genericos_bloqueados(self):
        for nome in self.GENERICOS:
            with self.subTest(nome):
                self.assertTrue(driver_manager.is_generic_name(nome),
                                f"{nome} deveria ser bloqueado")

    def test_drivers_de_fabricante_liberados(self):
        for nome in ("HP LaserJet MFP E52645 PCL-6 (V4)",
                     "Brother HL-L5100DN series PCL-6 (v4)",
                     "Kyocera ECOSYS P2040dn KX"):
            with self.subTest(nome):
                self.assertFalse(driver_manager.is_generic_name(nome))


class TestModelo(unittest.TestCase):
    def test_modelo_canonico(self):
        modelo, conf = model_identifier.canonical_model(
            "HP", sys_descr="HP LaserJet Flow MFP E52645, Firmware 2.4")
        self.assertIn("E52645", modelo)
        self.assertIn(conf, ("alta", "media", "baixa"))

    def test_confianca_desconhecida(self):
        modelo, conf = model_identifier.canonical_model("Desconhecido")
        self.assertTrue(modelo)
        self.assertIn(conf, ("alta", "media", "baixa"))


class TestInstalacao(unittest.TestCase):
    def test_portas_de_sistema_protegidas(self):
        for porta in ("LPT1", "COM3", "USB001", "FILE:", "PORTPROMPT:", "NUL"):
            with self.subTest(porta):
                self.assertFalse(printer_install.is_removable_port(porta),
                                 f"{porta} nao deveria ser removivel")

    def test_portas_de_rede_removiveis(self):
        for porta in ("TCPIPE:192.168.15.50", "IP_192.168.15.50",
                      "192.168.15.91", "WSDport_abc"):
            with self.subTest(porta):
                self.assertTrue(printer_install.is_removable_port(porta))

    def test_impressora_virtual_reconhecida(self):
        self.assertTrue(printer_install.is_virtual_printer(
            "Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:"))
        self.assertFalse(printer_install.is_virtual_printer(
            "HP LaserJet M404", "HP LaserJet M404 PCL6", "TCPIPE:192.168.15.9"))


class TestUSB(unittest.TestCase):
    def test_deteccao_nao_quebra(self):
        """A deteccao USB pode nao achar nada — mas nunca pode estourar."""
        dispositivos = usb_scanner.list_usb_devices()
        self.assertIsInstance(dispositivos, list)

    def test_modelo_a_partir_do_nome(self):
        dev = {"nome": "HP LaserJet M404 MFP (USB)", "device_id": "X"}
        self.assertEqual(usb_scanner.model_from_device(dev), "HP LaserJet M404 MFP")

    def test_fabricante_a_partir_do_nome(self):
        dev = {"nome": "Brother HL-L5100DN", "device_id": "X", "fabricante": ""}
        self.assertEqual(usb_scanner.vendor_from_device(dev, "Brother HL-L5100DN"),
                         "Brother")


class TestVarredura(unittest.TestCase):
    def test_expansao_de_cidr(self):
        from app.core.network import expand_targets
        alvos, avisos = expand_targets(["192.168.15.0/29"], include_arp=False)
        self.assertEqual(len(alvos), 6)   # /29 = 6 hosts usaveis
        self.assertIsInstance(avisos, list)

    def test_expansao_de_host_unico(self):
        from app.core.network import expand_targets
        alvos, _ = expand_targets(["192.168.15.50"], include_arp=False)
        self.assertEqual(alvos, ["192.168.15.50"])

    def test_expansao_ignora_ips_nao_varriveis(self):
        from app.core.network import expand_targets
        alvos, avisos = expand_targets(
            ["224.0.0.1", "127.0.0.1", "999.0.0.1"], include_arp=False)
        self.assertEqual(alvos, [])
        self.assertTrue(avisos)

    def test_replay_sem_done_fantasma(self):
        """Replay do SSE nao pode re-disparar `done` (fanfarra fantasma)."""
        from app.presentation import api
        api.STATE.bus.publish("busy", {"busy": "scan"})
        api.STATE.bus.publish("busy", {"busy": None})
        api.STATE.bus.publish("done", {"action": "install", "ok": 1,
                                       "fail": 0})
        rep = api.replay_snapshot()
        tipos = [m.get("type") for m in rep]
        self.assertNotIn("done", tipos)
        busies = [m for m in rep if m.get("type") == "busy"]
        self.assertTrue(busies)
        self.assertEqual(busies[-1], {"type": "busy",
                                      "data": {"busy": None}})


class TestVarreduraSemTravar(unittest.TestCase):
    """O sweep nunca pode congelar: futuro preso nao para a coleta."""

    def test_ping_invalido_nao_spawna_processo(self):
        from app.core import scanner
        t0 = time.monotonic()
        self.assertFalse(scanner.ping_host("999.1.1.1"))
        self.assertFalse(scanner.ping_host("224.0.0.1"))
        self.assertFalse(scanner.ping_host(""))
        self.assertLess(time.monotonic() - t0, 5)

    def test_ping_sem_pipes(self):
        """ping_host nao pode usar pipes (reader-threads travam no Windows)."""
        from app.core import scanner
        fonte = Path(scanner.__file__).read_text(encoding="utf-8")
        bloco = fonte[fonte.find("def ping_host"):fonte.find("def check_port")]
        self.assertIn("DEVNULL", bloco)
        self.assertNotIn("capture_output", bloco)

    def test_drain_respeita_teto(self):
        """Um futuro eternamente preso nao congela o _drain."""
        from concurrent.futures import ThreadPoolExecutor
        from app.core.scanner import _drain
        stop = threading.Event()
        ex = ThreadPoolExecutor(max_workers=2)
        try:
            preso = ex.submit(stop.wait)
            rapido = ex.submit(lambda: 42)
            vistos = []
            n = _drain(ex, {preso: "1.1.1.1", rapido: "2.2.2.2"},
                       0, 2, None, None, 2,
                       lambda d, t, ip: f"{d}/{t}",
                       lambda f, ip: vistos.append(ip),
                       tick_s=1)
            self.assertEqual(n, 1)
            self.assertEqual(vistos, ["2.2.2.2"])
        finally:
            stop.set()
            ex.shutdown(wait=True)

    def test_filtro_de_ruido_readerthread(self):
        """threading.excepthook filtra SO o EBADF da _readerthread."""
        import threading
        from types import SimpleNamespace
        from app.platform import process as proc
        proc.install_readerthread_excepthook()
        self.assertEqual(threading.excepthook.__name__,
                         "forja_readerthread_filter")
        proc.install_readerthread_excepthook()  # idempotente
        chamadas = []
        anterior = threading.excepthook
        threading.excepthook = chamadas.append
        try:
            proc.install_readerthread_excepthook()
            filtro = threading.excepthook
            frame = SimpleNamespace(
                f_code=SimpleNamespace(co_name="_readerthread",
                                       co_filename="C:\\Python\\Lib\\subprocess.py"))
            tb = SimpleNamespace(tb_frame=frame, tb_next=None)
            # caso real: OSError 9 na _readerthread -> engolido
            filtro(SimpleNamespace(exc_value=OSError(9, "Bad file descriptor"),
                                   exc_traceback=tb))
            self.assertEqual(chamadas, [])
            # outros erros passam normalmente
            filtro(SimpleNamespace(exc_value=OSError(2, "x"), exc_traceback=tb))
            filtro(SimpleNamespace(exc_value=ValueError("x"),
                                   exc_traceback=None))
            self.assertEqual(len(chamadas), 2)
        finally:
            threading.excepthook = anterior


class TestVersion(unittest.TestCase):
    def test_versao_lida_do_arquivo(self):
        self.assertNotEqual(__version__, "0.0.0-dev",
                            "arquivo VERSION ausente ou vazio")
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+")


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = config.load()
        self.assertIn("theme", cfg)
        self.assertIn("auto_download", cfg)


class TestProcessosSemJanela(unittest.TestCase):
    """Processos filhos NAO podem abrir janela de console.

    O app e um executavel 'windowed' (sem console). Sem CREATE_NO_WINDOW o
    Windows abre um console VISIVEL para cada ping/ipconfig/PowerShell —
    centenas de janelas durante um ping sweep.
    """

    def test_flag_define(self):
        from app.platform import process
        self.assertEqual(process.CREATE_NO_WINDOW, 0x08000000)

    def test_run_aplica_create_no_window(self):
        from app.platform import process
        capturado = {}

        class Fake:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(*args, **kwargs):
            capturado.update(kwargs)
            return Fake()

        original = process.subprocess.run
        process.subprocess.run = fake_run
        try:
            process.run(["cmd", "/c", "echo"])
        finally:
            process.subprocess.run = original
        if sys.platform == "win32":
            self.assertTrue(capturado.get("creationflags", 0)
                            & process.CREATE_NO_WINDOW,
                            "CREATE_NO_WINDOW nao aplicado")

    def test_nenhum_subprocess_direto_no_motor(self):
        """Nenhum modulo do motor pode chamar subprocess.run cru."""
        from app.core import (driver_download, driver_manager, network,
                              printer_install, scanner, usb_scanner)
        modulos = (scanner, network, driver_manager, driver_download,
                   printer_install, usb_scanner)
        for mod in modulos:
            with self.subTest(mod.__name__):
                fonte = Path(mod.__file__).read_text(encoding="utf-8")
                self.assertNotIn("subprocess.run(", fonte,
                                 f"{mod.__name__} chama subprocess.run direto")
                self.assertNotIn("subprocess.Popen(", fonte,
                                 f"{mod.__name__} chama subprocess.Popen direto")


class TestCaminhosGravaveis(unittest.TestCase):
    """Em pasta somente-leitura o app nao pode quebrar."""

    def test_scan_result_path_gravavel(self):
        destino = paths.scan_result_path()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text("[]", encoding="utf-8")
        self.assertTrue(destino.exists())
        destino.unlink(missing_ok=True)

    def test_logs_dir_gravavel(self):
        d = paths.logs_dir()
        probe = d / ".teste"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)

    def test_drivers_dir_existe(self):
        self.assertTrue(paths.drivers_dir().is_dir())


class TestRunBat(unittest.TestCase):
    """O run.bat precisa elevar para admin SEM corromper os argumentos."""

    def _bat(self):
        return (ROOT / "run.bat").read_text(encoding="utf-8")

    def test_sem_forward_de_asterisco_simples(self):
        # "'%*'" vira UM argumento so (cmd nao entende aspas simples):
        # quebrava "scan <CIDR>" e injetava '' fantasma no desktop.
        self.assertNotIn("'%*'", self._bat())

    def test_desktop_nao_repassa_modo_cru(self):
        # "--mode desktop %*" duplicava a palavra do modo ("browser",
        # "servidor") e fazia o argparse falhar.
        self.assertNotIn("--mode desktop %*", self._bat())

    def test_executa_main_como_admin(self):
        # O bat so faz isso: garante admin e roda o main.py desktop.
        bat = self._bat()
        self.assertIn("net session", bat)
        self.assertIn("Verb RunAs", bat)
        self.assertIn("python main.py --mode desktop", bat)

    def test_sem_dispatch_de_modo(self):
        # Sem if de modo, sem call, sem repasse de args: minimalista.
        bat = self._bat().lower()
        self.assertNotIn("call ", bat)
        self.assertNotIn("%~1", bat)
        self.assertNotIn("%*", bat)
        self.assertNotIn("goto :scan", bat)
        self.assertNotIn("goto :server", bat)

    def test_bat_usa_crlf(self):
        # O parser do cmd exige CRLF: .bat com LF puro quebra blocos
        # if/for com "... foi inesperado neste momento".
        # (As ferramentas de edicao normalizam para LF: apos editar um
        # .bat, reconverter com:
        #  python -c "import pathlib; [pathlib.Path(f).write_bytes(pathlib.Path(f).read_bytes().replace(bytes([13,10]),bytes([10])).replace(bytes([10]),bytes([13,10]))) for f in ['run.bat','scripts/build.bat']]")
        for rel in ("run.bat", "scripts/build.bat"):
            raw = (ROOT / rel).read_bytes()
            lf = raw.count(b"\n")
            crlf = raw.count(b"\r\n")
            with self.subTest(arquivo=rel):
                self.assertGreater(crlf, 0, f"{rel} sem CRLF")
                self.assertEqual(lf, crlf, f"{rel} tem LF solitario (exige CRLF)")

    def test_for_sem_parenteses_no_in(self):
        # O parser do cmd conta parenteses mesmo entre aspas dentro do
        # IN ('...') do for: um ')' ali dentro fecha o conjunto antes da
        # hora e o bat morre com "... foi inesperado neste momento".
        import re
        for i, line in enumerate(self._bat().splitlines(), start=1):
            m = re.match(r"\s*for\s+/f\b.*? in \(", line, re.I)
            if not m:
                continue
            depth = 1
            j = m.end()
            while j < len(line) and depth > 0:
                c = line[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                j += 1
            resto = line[j:].strip().lower()
            with self.subTest(linha=i):
                self.assertTrue(
                    resto.startswith("do "),
                    f"run.bat:{i}: ')' prematuro no IN do for: {line.strip()}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
