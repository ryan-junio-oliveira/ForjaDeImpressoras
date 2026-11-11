"""
Hibrido desktop: janela nativa (PySide6) que renderiza a interface web
local — mesmo padrao do HyperViewerTotem (QWebEngineView), porem com o
servidor HTTP embarcado no proprio processo.

Politica: interface SOMENTE na janela desktop. Nenhum codigo deste
modulo abre o navegador do usuario. Fechar a janela encerra o
processo por completo (app + servidor embutido).
"""
import os
import sys
import threading

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton,
                               QVBoxLayout, QWidget)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView


def make_icon() -> QIcon:
    """Ícone do app desenhado em runtime (sem arquivos externos)."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#7C3AED"))
    p.drawRoundedRect(0, 0, 64, 64, 14, 14)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRoundedRect(20, 11, 24, 12, 3, 3)      # bandeja superior
    p.drawRoundedRect(13, 21, 38, 21, 4, 4)      # corpo
    p.drawRoundedRect(19, 41, 26, 13, 3, 3)      # papel saindo
    p.setBrush(QColor("#F59E0B"))
    p.drawRoundedRect(40, 26, 7, 5, 2, 2)        # visor dourado
    p.end()                                      # encerra o painter (obrigatorio)
    return QIcon(pm)


class InstallerPage(QWebEnginePage):
    """Bloqueia popups e qualquer navegacao para fora do app local.

    Politica do app: interface SOMENTE na janela desktop. Nenhum link
    abre o navegador — navegacoes nao-locais sao descartadas.
    """

    def createWindow(self, _type):  # noqa: N802 (assinatura Qt)
        return None

    def acceptNavigationRequest(self, url, _type, is_main_frame):  # noqa: N802
        host = url.host()
        if host in ("127.0.0.1", "localhost"):
            return True
        return False


class InstallerWindow(QMainWindow):
    def __init__(self, url: str):
        super().__init__()
        self.url = url
        self.setWindowTitle("Instalador de Impressoras")
        self.setWindowIcon(make_icon())
        self.resize(1360, 880)
        self.setMinimumSize(1024, 680)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # a WebView e criada antes da barra (a barra usa self.view.reload)
        self.view = QWebEngineView(central)
        page = InstallerPage(self.view)
        page.profile().setHttpUserAgent(
            "InstaladorDeImpressoras/2.0 (Windows)")
        self.view.setPage(page)
        self.view.setUrl(QUrl(url))
        self.view.loadFinished.connect(self._on_loaded)

        root.addWidget(self._build_toolbar())
        root.addWidget(self.view, 1)

        # barra de status da janela nativa
        self.status = QLabel("Carregando interface…", central)
        self.status.setContentsMargins(14, 5, 14, 5)
        self.status.setStyleSheet("background:#070b14;color:#8b9bb4;font-size:12px;border-top:1px solid #23304c;")
        root.addWidget(self.status)

        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self.view.reload)
        self._retry.setInterval(4000)

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(50)
        bar.setStyleSheet(
            "QFrame{background:#0c1222;border-bottom:1px solid #23304c;}"
            "QPushButton{background:#11182c;border:1px solid #23304c;"
            "border-radius:6px;padding:6px 12px;color:#cbd5e1;font-size:12px;font-weight:600;}"
            "QPushButton:hover{background:#17223b;border-color:#8b5cf6;color:#ffffff;}"
            "QLabel{color:#ffffff;font-size:13px;font-weight:700;letter-spacing:0.5px;}"
            "QLabel#sub{color:#8b9bb4;font-size:11px;font-weight:400;}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(10)

        title = QLabel("Forja de Impressoras")
        lay.addWidget(title)
        sub = QLabel("Varredura SNMP/ARP/IPP • Forja de Drivers PCL Oficiais")
        sub.setObjectName("sub")
        lay.addWidget(sub)
        lay.addStretch(1)

        btn_reload = QPushButton("Recarregar")
        btn_reload.clicked.connect(self.view.reload)
        lay.addWidget(btn_reload)

        return bar

    # ------------------------------------------------------------------
    def _on_loaded(self, ok: bool):
        if ok:
            self.status.setText("Pronto.")
        else:
            self.status.setText("Falha ao carregar a interface — tentando novamente…")
            self._retry.start()

    def closeEvent(self, event):  # noqa: N802
        # Desmonta a WebView ANTES de fechar: sem isso o QtWebEngine pode
        # segurar processos filhos (render/gpu) e a janela some mas o
        # app continua vivo em segundo plano.
        try:
            self._retry.stop()
        except Exception:
            pass
        try:
            self.view.stop()
            self.view.setPage(None)
        except Exception:
            pass
        super().closeEvent(event)
        try:
            QApplication.instance().quit()
        except Exception:
            pass


def run(port=8765):
    """Sobe servidor + janela desktop. Retorna o codigo de saida."""
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass

    from .server import start_server

    httpd, url = start_server(port=port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"  Interface local: {url}")

    # Qt parseia sys.argv: passar so o argv[0] evita que opcoes nossas
    # (--help, --port...) sejam interpretadas pelo proprio Qt.
    app = QApplication([sys.argv[0] if sys.argv else "ForjaDeImpressoras"])
    app.setApplicationName("Instalador de Impressoras")
    app.setApplicationDisplayName("Forja de Impressoras")
    app.setQuitOnLastWindowClosed(True)

    win = InstallerWindow(url)
    win.show()

    def _shutdown():
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass

    app.aboutToQuit.connect(_shutdown)
    code = app.exec()
    # Fechou a janela = acabou: garante que o servidor embutido parou
    # e que NENHUMA thread segura o processo vivo em segundo plano.
    _shutdown()
    try:
        t.join(timeout=8)
    except Exception:
        pass
    if t.is_alive():
        os._exit(code if isinstance(code, int) else 0)
    return code
