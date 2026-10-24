"""Start Aurora OS. Double-click the installed app, or run:  python run.py"""
import socket
import sys
import threading
import time


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    from aurora.app import create_app
    app = create_app()
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else free_port()
    url = f"http://127.0.0.1:{port}"

    def serve():
        from waitress import serve as wserve
        wserve(app, host="127.0.0.1", port=port, threads=8)       # only this computer can reach it

    if "--no-window" in sys.argv:                                   # server only (for tests / browsers)
        print("Aurora OS running at", url)
        serve()
        return
    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.8)
    try:
        import webview                                               # a real desktop window
        webview.create_window("Aurora OS", url, width=1360, height=840, min_size=(1000, 650))
        webview.start()
    except Exception:                                                # no window library: use the browser
        import webbrowser
        webbrowser.open(url)
        print("Aurora OS is open in your browser:", url, "\nKeep this window open. Press Ctrl+C to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
