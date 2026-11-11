"""
Testes de fumaca da Forja de Impressoras.

Executa sem rede e sem Windowsprivilegiado: valida imports, regras de
seguranca do driver, caminhos e a API do servidor.

Uso:
    python -m tests.test_smoke
    python tests/test_smoke.py
"""
import sys
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
