import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path('src').resolve()))
from models import Song
from youtube_client import parse_song, playlist_page, CollectionError, YouTubeClient
from audio_resolver import AudioResolver, choose_stream


def row(video_id, title='Song'):
    return {'musicResponsiveListItemRenderer': {
        'playlistItemData': {'videoId': video_id},
        'flexColumns': [{'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [{'text': title}]}}},
                        {'musicResponsiveListItemFlexColumnRenderer': {'text': {'runs': [
                            {'text': 'Artist', 'navigationEndpoint': {'browseEndpoint': {'browseId': 'UCartist'}}}]}}}],
        'fixedColumns': [{'text': {'runs': [{'text': '3:12'}]}}]}}


class YouTubeTests(unittest.TestCase):
    def test_song_metadata_and_missing_id(self):
        song = parse_song(row('abcdefghijk'))
        self.assertEqual((song.video_id, song.title, song.artist, song.duration), ('abcdefghijk', 'Song', 'Artist', 192))
        self.assertIsNone(parse_song(row('')))

    def test_new_and_old_continuations_and_empty_shelf(self):
        data = {'contents': {'musicPlaylistShelfRenderer': {'contents': [row('abcdefghijk')],
                 'continuations': [{'nextContinuationData': {'continuation': 'next'}}]}}}
        self.assertEqual(playlist_page(data)[1], 'next')
        new = {'onResponseReceivedActions': [{'appendContinuationItemsAction': {'continuationItems': [
            row('abcdefghijk'), {'continuationItemRenderer': {'continuationEndpoint': {'continuationCommand': {'token': 'more'}}}}]}}]}
        self.assertEqual(playlist_page(new)[1], 'more')
        self.assertEqual(playlist_page({'contents': {'musicPlaylistShelfRenderer': {'contents': []}}}), ([], None))
        with self.assertRaises(CollectionError):
            playlist_page({'error': 'blocked'})

    def test_complete_pagination_or_no_result(self):
        client = object.__new__(YouTubeClient)
        responses = iter([{'contents': {'musicPlaylistShelfRenderer': {'contents': [row('abcdefghijk')],
                          'continuations': [{'nextContinuationData': {'continuation': 'next'}}]}}},
                          {'continuationContents': {'musicPlaylistShelfContinuation': {'contents': [row('ABCDEFGHIJK')]}}}])
        client.request = lambda *args: next(responses)
        self.assertEqual(len(client.innertube_songs('LM')), 2)
        client.request = lambda *args: {'contents': {'musicPlaylistShelfRenderer': {'contents': [],
                                        'continuations': [{'nextContinuationData': {'continuation': 'loop'}}]}}}
        with self.assertRaises(CollectionError):
            client.innertube_songs('LM')

    def test_audio_requires_explicit_permission(self):
        config = SimpleNamespace(audio_authorized_video_ids=frozenset())
        resolver = AudioResolver(None, None, config)
        self.assertIsNone(resolver.resolve(Song('abcdefghijk','a','b'), '/tmp'))

    def test_quality_and_ciphered_stream_fallback(self):
        formats = [{'mimeType': 'audio/mp4', 'url': 'https://example.com/a', 'bitrate': 100},
                   {'mimeType': 'audio/webm', 'url': 'https://example.com/b', 'bitrate': 200},
                   {'mimeType': 'audio/mp4', 'signatureCipher': 'encrypted', 'bitrate': 300}]
        data = {'streamingData': {'adaptiveFormats': formats}}
        self.assertEqual(choose_stream(data, 'best')['bitrate'], 200)
        self.assertEqual(choose_stream(data, 'worst')['bitrate'], 100)
        self.assertIsNone(choose_stream({'streamingData': {'adaptiveFormats': formats[2:]}}, 'best'))
