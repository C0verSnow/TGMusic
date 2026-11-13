import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from audio_resolver import AudioResolver


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg runs in remote CI')
class AudioConversionTests(unittest.TestCase):
    def test_converts_actual_pcm_into_mp3_and_m4a(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.wav'
            with wave.open(str(source),'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b''.join(struct.pack('<h',int(10000*math.sin(2*math.pi*440*i/16000))) for i in range(16000)))
            for format,codec in [('mp3','mp3'),('m4a','aac')]:
                resolver=AudioResolver(None,None,SimpleNamespace(audio_format=format))
                converted=resolver.convert(source,directory,'abcdefghijk')
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name',
                                      '-of','json',str(converted)],capture_output=True,text=True,check=True)
                self.assertEqual(json.loads(probe.stdout)['streams'][0]['codec_name'],codec)
