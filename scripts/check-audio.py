"""Inspect one playlist song on a remote Runner without sending or changing song history."""
import logging
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audio_resolver import AudioResolver
from browser_session import BrowserSession
from cloudflare_storage import D1, R2
from config import Config
from history import History
from main import load_collection
from models import SyncError
from proxy import Network
from utils import configure_logging, mask_actions_secrets


def main():
    configure_logging()
    mask_actions_secrets()
    config = Config.load()
    video_id = sample_video()
    history = History(D1(config))
    installation = history.installation()
    history.acquire()
    network = Network(config)
    browser = None
    try:
        r2 = R2(config)
        r2.verify_installation(installation['installation_id'])
        browser = BrowserSession(config, r2)
        browser.restore()
        network.start()
        browser.r2 = R2(config, network.proxy_url)
        browser.proxy_url = network.proxy_url
        youtube, songs = load_collection(config, browser, network, history)
        song = next((song for song in songs if song.video_id == video_id), None)
        if song is None:
            raise SyncError('Sample is not in the configured playlist')
        with tempfile.TemporaryDirectory(prefix='tgmusic-audio-probe-') as directory:
            output = AudioResolver(youtube, network.session, config).resolve(song, directory)
            if output is None:
                raise SyncError('Audio probe failed: current resolver cannot produce an audio file; no message sent')
            logging.info('Audio probe passed: format=%s bytes=%d; no message sent', output.suffix, output.stat().st_size)
    finally:
        try:
            if browser:
                browser.cleanup()
        finally:
            network.close()
            history.release()


def sample_video():
    if len(sys.argv) != 2 or not re.fullmatch(r'[A-Za-z0-9_-]{11}', sys.argv[1]):
        raise SyncError('Pass one valid video ID from the configured playlist')
    return sys.argv[1]


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        logging.error('%s', str(error) if isinstance(error, SyncError) else type(error).__name__ + '; details suppressed')
        sys.exit(1)
