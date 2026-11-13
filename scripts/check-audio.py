"""Inspect one authorized song on a remote Runner without sending or changing song history."""
import logging
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
    video_id = authorized_video(config)
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
            raise SyncError('Authorized sample is not in the configured playlist')
        data = youtube.player(video_id)
        formats = data.get('streamingData', {}).get('adaptiveFormats', [])
        audio = [row for row in formats if row.get('mimeType', '').startswith('audio/')]
        status = data.get('playabilityStatus', {}).get('status')
        logging.info('Audio probe: playable=%s audio_formats=%d direct_https=%d ciphered=%d',
                     status == 'OK', len(audio),
                     sum(row.get('url', '').startswith('https://') for row in audio),
                     sum(bool(row.get('signatureCipher') or row.get('cipher')) for row in audio))
        with tempfile.TemporaryDirectory(prefix='tgmusic-audio-probe-') as directory:
            output = AudioResolver(youtube, network.session, config).resolve(song, directory)
            if output is None:
                raise SyncError('Audio probe failed: current resolver would send a link; no message sent')
            logging.info('Audio probe passed: format=%s bytes=%d; no message sent', output.suffix, output.stat().st_size)
    finally:
        try:
            if browser:
                browser.cleanup()
        finally:
            network.close()
            history.release()


def authorized_video(config):
    if len(sys.argv) != 2 or sys.argv[1] not in config.audio_authorized_video_ids:
        raise SyncError('Pass one video ID already listed in AUDIO_AUTHORIZED_VIDEO_IDS')
    return sys.argv[1]


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        logging.error('%s', str(error) if isinstance(error, SyncError) else type(error).__name__ + '; details suppressed')
        sys.exit(1)
