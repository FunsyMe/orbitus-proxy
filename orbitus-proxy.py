from tkinter import messagebox
import tkinter as tk

import threading
import asyncio
import signal
import sys
import logging
import pyperclip

from proxy import tg_proxy

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler('orbitus-proxy.log', mode='a', encoding='utf-8')
        ]
    )
logger = logging.getLogger('proxy-wrapper')

def show_error_popup(title: str, message: str):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        messagebox.showerror(title, message, master=root)
        root.destroy()
    except Exception as error:
        logger.error(f'Failed to show error GUI: {error}')

def show_info_popup(title: str, message: str, link: str = None):
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        if link:
            pyperclip.copy(link)

        messagebox.showinfo(title, message, master=root)
        root.destroy()
    except Exception as error:
        logger.error(f'Failed to show info GUI: {error}')

class ProxyManager:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            raise RuntimeError('Прокси уже работает')

        self._thread = threading.Thread(
            target=self._run,
            daemon=False,
        )
        self._thread.start()

        logger.info('Proxy thread started')

    def stop(self):
        logger.info('Stopping proxy...')

        if self._loop and self._stop_event:
            try:
                self._loop.call_soon_threadsafe(self._stop_event.set)
            except RuntimeError:
                pass

        if self._thread:
            self._thread.join(timeout=5)

        logger.info('Proxy stopped')

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._stop_event = asyncio.Event()

        # Создаем асинхронную функцию-обертку
        async def run_proxy_and_popup():
            cfg = tg_proxy.proxy_config
            link = (
                f'tg://proxy?'
                f'server={tg_proxy.get_link_host(cfg.host)}'
                f'&port={cfg.port}'
                f'&secret=dd{cfg.secret}'
            )

            proxy_task = asyncio.create_task(
                tg_proxy._run(stop_event=self._stop_event)
            )

            await asyncio.sleep(0.5)
            if not proxy_task.done():
                threading.Thread(
                    target=show_info_popup,
                    args=(
                        'Инфо',
                        f'Прокси запущен на {cfg.host}:{cfg.port}\nСсылка для прокси скопирована в буфер обмена',
                        link
                    ),
                    daemon=True
                ).start()

            await proxy_task


        try:
            self._loop.run_until_complete(run_proxy_and_popup())

        except Exception as error:
            logger.exception('Proxy crashed')

            show_error_popup(
                'Критическая ошибка',
                f'Прокси упал:\n\n{error}'
            )

        finally:
            self._loop.close()
            self._loop = None
            self._stop_event = None

def main():
    setup_logging()
    manager = ProxyManager()

    def shutdown_handler(signum=None, frame=None):
        logger.info('Received shutdown signal')

        manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        manager.start()
        while True:
            signal.pause() if hasattr(signal, 'pause') else threading.Event().wait()

    except RuntimeError as error:
        logger.error(str(error))

        show_error_popup('Ошибка', str(error))
        manager.stop()

    except KeyboardInterrupt:
        logger.info('Keyboard interrupt')
        shutdown_handler()

    except Exception as error:
        logger.exception('Fatal error')

        show_error_popup('Фатальная ошибка', f'Непредвиденная ошибка в основном потоке:\n\n{error}')
        shutdown_handler()

if __name__ == '__main__':
    main()