import re, datetime, struct, sys, time
from kivy.uix.video import Video
from kivy.core.video import VideoBase
import subprocess, re, bisect

class RideVideo(Video):
    def __init__(self, filename):
        self.creation_time = self._get_creation_time(filename)
        self.video_duration = self._get_duration(filename)
        self.relative_start_time = 0
        super(RideVideo, self).__init__(source=filename)

    @staticmethod
    def _get_duration(filename):
        result = subprocess.Popen(
            'ffprobe -i "{}" -show_entries format=duration -v quiet -of csv="p=0"'.format(filename),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.communicate()
        return float(output[0].decode('utf-8'))

    @staticmethod
    def _get_creation_time(filename):
        atom_header_size = 8
        # difference between Unix epoch and QuickTime epoch, in seconds
        epoch_adjuster = 2082844800
        # open file and search for moov item
        f = open(filename, "rb")
        while 1:
            atom_header = f.read(atom_header_size)
            if atom_header[4:8] == b'moov':
                break
            else:
                atom_size = struct.unpack(">I", atom_header[0:4])[0]
                f.seek(atom_size - 8, 1)

        # found 'moov', look for 'mvhd' and timestamps
        atom_header = f.read(atom_header_size)
        if atom_header[4:8] == b'cmov':
            print("moov atom is compressed")
        elif atom_header[4:8] != b'mvhd':
            print("expected to find 'mvhd' header")
        else:
            f.seek(4, 1)
            creation_date = struct.unpack(">I", f.read(4))[0]
            return time.mktime(datetime.datetime.utcfromtimestamp(creation_date).timetuple()) - epoch_adjuster
