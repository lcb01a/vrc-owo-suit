import asyncio
import threading
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from tinyoscquery.queryservice import OSCQueryService
from tinyoscquery.utility import get_open_tcp_port, get_open_udp_port
from owo_suit import OWOSuit
from config import Config
from gui import Gui
import os


def start_oscquery(server_udp_port, server_tcp_port):
    def start_server():
        oscquery_server = OSCQueryService("VRC OWO Suit", server_tcp_port, server_udp_port)
        oscquery_server.advertise_endpoint("/avatar")
    return start_server

gui = None
try:
    cfg = Config()
    cfg.init()
    logo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), './img/logo.png'))
    gui = Gui(config=cfg, window_width=550,
              window_height=1000, logo_path=logo_path)
    gui.init()
    owo_suit = OWOSuit(config=cfg, gui=gui)
    owo_suit.init()
    dispatcher = Dispatcher()
    owo_suit.map_parameters(dispatcher)

    server_udp_port = cfg.get_by_key("server_port")

    if cfg.get_by_key("use_oscquery"):
        server_udp_port = get_open_udp_port()
        server_tcp_port = get_open_tcp_port()
        threading.Thread(target=start_oscquery(server_udp_port, server_tcp_port),
                         daemon=True).start()

    osc_server = ThreadingOSCUDPServer(
        ("127.0.0.1", server_udp_port), dispatcher, asyncio.new_event_loop())
    threading.Thread(target=lambda: osc_server.serve_forever(2),
                     daemon=True).start()
    threading.Thread(target=owo_suit.watch,
                     daemon=True).start()
    gui.run()
except KeyboardInterrupt:
    print("Shutting Down...\n")
except OSError:
    pass
finally:
    if gui is not None:
        gui.cleanup()
