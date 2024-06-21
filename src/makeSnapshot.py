import sys
import socket
import logging
from snapshot_pyppeteer import snapshot
from pyecharts.render import make_snapshot

hostname = socket.gethostname()
ip = socket.gethostbyname(hostname)
logging.basicConfig(filename='record.log', format=f'%(asctime)s - {ip} - %(levelname)s: %(message)s',
                    level=logging.INFO)
make_snapshot(snapshot, f"./render.html", f"./mind_maps/{sys.argv[1]}.png")