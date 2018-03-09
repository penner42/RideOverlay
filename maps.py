import numpy
from math import radians, sin, log, pi, floor, degrees, atan, sinh
import urllib.request
from PIL import Image as pillowimage
from PIL import ImageColor
from PIL.ImageDraw import Draw
from kivy.app import App
from geopy.distance import vincenty
import polyline, io, sys
import webbrowser


ZOOMLEVEL = 15
TILESIZE = 240


class LatLong():
    def __init__(self, arg1, arg2=None):
        if arg2:
            # lat and lng passed separately
            self.lat = arg1
            self.lon = arg2
        else:
            # lat and lng passed as tuple or array
            self.lat = arg1[0]
            self.lon = arg1[1]

    def to_str(self):
        return '{},{}'.format(self.lat, self.lon)

    def to_tuple(self):
        return self.lat, self.lon


class MapTile():
    def __init__(self, center):
        self.center = center
        self._pxcenter = MapData.latlng_to_pixel(self.center)
        self._topleft = MapData.pixel_to_latlng((self._pxcenter[0]-120, self._pxcenter[1]-120))
        self._bottomright = MapData.pixel_to_latlng((self._pxcenter[0]+120, self._pxcenter[1]+120))
        self._pxtopleft = MapData.latlng_to_pixel(self._topleft)
        self._pxbottomright = MapData.latlng_to_pixel(self._bottomright)
        self._indices = [0]
        self._polylines = []
        self._image = None

    def topleft(self):
        return self._topleft

    def bottomright(self):
        return self._bottomright

    def get_paths(self):
        if len(self._polylines) > 0:
            return self._polylines
        return None

    def add_path(self, path):
        try:
            self._polylines.append(polyline.encode([x.to_tuple() for x in path]))
        except TypeError as e:
            pass

    def calculatepaths(self):
        app = App.get_running_app()
        # nums = sorted(set(self._indices))
        # gaps = [[s, e] for s, e in zip(nums, nums[1:]) if s + 1 < e]
        # edges = iter(nums[:1] + sum(gaps, []) + nums[-1:])
        # paths = list(zip(edges,edges))
        # for p in paths:
        #     linecoords = []
        #     for index in range(max(0,p[0]-50), min(len(app.mapdata._coordinates)-1, p[1]+50)):
        #         linecoords.append(app.mapdata._coordinates[index])
        #     self._polylines.append(polyline.encode(linecoords))
        # start = max(0, self._indices[0])
        # end = min(len(app.mapdata._coordinates)-1, self._indices[-1])
        # linecoords = list(app.mapdata._coordinates[i] for i in range(start, end))
        # self._polylines = polyline.encode(linecoords)

    def set_image(self, data):
        self._image = pillowimage.open(data).convert("RGBA")

    def draw_point(self, latlong):
        if self._image:
            tmp = self._image.copy()
            draw = Draw(tmp)
            pix = MapData.latlng_to_pixel(latlong)

#            tilepix = (pix[0] - (self._pxcenter[0]-TILESIZE/2), pix[1] - (self._pxcenter[1]-TILESIZE/2))
            tilepix = (pix[0] - self._pxtopleft[0], pix[1] - self._pxtopleft[1])
            draw.ellipse([(tilepix[0]-5, tilepix[1]-5),(tilepix[0]+5, tilepix[1]+5)], fill=ImageColor.getrgb('red'))
            return tmp

    def contains(self, latlong):
        if latlong.lat < self._bottomright.lat or latlong.lat > self._topleft.lat:
            return False

        if self._topleft.lon > self._bottomright.lon:
            return 180 >= latlong.lon >= self._topleft.lon or self._bottomright.lon >= latlong.lon >= -180
        else:
            return self._bottomright.lon >= latlong.lon >= self._topleft.lon


class MapData():
    def __init__(self, stream):
        self._coordinates = [LatLong(c) for c in stream['latlng'].data]
        self._timeindex = stream['time'].data
        self._minlat = min([x.lat for x in self._coordinates])
        self._maxlat = max([x.lat for x in self._coordinates])
        self._minlon = min([x.lon for x in self._coordinates])
        self._maxlon = max([x.lon for x in self._coordinates])
        self._paths = []
        self._tiles = []
        self._calculate_paths()
        self._get_tiles()

    def _calculate_paths(self):
        # find paths in activity - all sets of consecutive time increments
        gap = start = 0
        for i, c in enumerate(self._timeindex):
            if c == i + gap:
                continue

            self._paths.append(self._timeindex[start:i])
            start = i
            gap = c - i
            print("{} {}".format(i,c))
        self._paths.append(self._timeindex[start:])

    def containsroute(self, tile):
        result = False
        t = tile.center.to_str()
        for i, c in enumerate(self._coordinates):
            if tile.contains(c):
                tile._indices.append(i)
                result = True
        return result

    def _get_tiles(self):
        current_lon = self._minlon
        while current_lon < self._maxlon:
            current_lat = self._maxlat
            while current_lat > self._minlat:
                tile = MapTile(LatLong(current_lat, current_lon))
                current_path = None
                for p in self._paths:
                    for i, c in enumerate(p):
                        if tile.contains(self._coordinates[i]):
                            try:
                                current_path.append(self._coordinates[i])
                            except AttributeError:
                                if i == 0:
                                    current_path = [self._coordinates[0]]
                                else:
                                    current_path = [self._coordinates[i-1]]
                                    current_path.append(self._coordinates[i])
                        else:
                            try:
                                current_path.append(self._coordinates[i])
                                tile.add_path(current_path)
                                current_path = None
                            except AttributeError as e:
                                pass
                    pass

                paths = tile.get_paths()
                if paths:
                    # if self.containsroute(tile):
                    #     tile.calculatepaths()
                    paths_str = ''.join('&path=enc:'+x for x in paths)
                    url = 'https://maps.googleapis.com/maps/api/staticmap?center={}' \
                          '&size=240x240&zoom={}{}&format=png&key={}'.format(
                           tile.center.to_str(),ZOOMLEVEL, paths_str,
                           App.get_running_app().config.get('Settings', 'googlemaps_api_key')
                    )
                    try:
                        with urllib.request.urlopen(url) as response:
                            tile.set_image(io.BytesIO(response.read()))
                    except urllib.error.HTTPError as e:
                        print('error with url {}'.format(url))
                        webbrowser.open(url)
                        sys.exit()

                    self._tiles.append(tile)

                # increment latitude by 1/3 of tile
                print(tile.center.to_str())
                pixel = MapData.latlng_to_pixel(tile.center)
                current_lat = MapData.pixel_to_latlng((pixel[0], pixel[1]+floor(TILESIZE/3))).lat

            # increment longitude by 1/3 of tile
            pixel = MapData.latlng_to_pixel(LatLong(current_lat, current_lon))
            current_lon = MapData.pixel_to_latlng((pixel[0]+floor(TILESIZE/3), pixel[1])).lon
            print(current_lon)

        # for lon in numpy.arange(self._minlon, self._maxlon, 0.005):
        #     for lat in numpy.arange(self._minlat, self._maxlat, 0.005):
        #         tile = MapTile(LatLong(lat, lon))
        #         # only save this tile if it contains points on the route
        #         if self.containsroute(tile):
        #             tile.calculatepaths()
        #             url = 'https://maps.googleapis.com/maps/api/staticmap?center={}' \
        #                   '&size=240x240&zoom={}&path=enc:{}&format=png&key={}'.format(
        #                    tile.center.to_str(),ZOOMLEVEL, tile._polylines,
        #                    App.get_running_app().config.get('Settings', 'googlemaps_api_key')
        #             )
        #             try:
        #                 with urllib.request.urlopen(url) as response:
        #                     tile.set_image(io.BytesIO(response.read()))
        #             except urllib.error.HTTPError:
        #                 pass
        #             self._tiles.append(tile)
        print(len(self._tiles))
        pass

    def getTilePoint(self, latlong):
        # find tile with center point closest to position
        # could probably use a lot of optimization
        min_distance = None
        resultTile = None
        for t in self._tiles:
            if t.contains(latlong):
                distance = vincenty(t.center.to_tuple(), latlong.to_tuple()).miles
                if min_distance is None or distance < min_distance:
                    min_distance = distance
                    resultTile = t
        return resultTile

    @staticmethod
    def pixel_to_latlng(pixel):
        scale = (1 << ZOOMLEVEL) * 256
        lon_deg = pixel[0] / scale * 360.0 - 180.0
        lat_rad = atan(sinh(pi * (1-2 * pixel[1] / scale)))
        lat_deg = degrees(lat_rad)
        return LatLong(lat_deg, lon_deg)

    @staticmethod
    def latlng_to_pixel(latlong):
        # get world coordinates
        siny = sin(latlong.lat * pi /180)
        siny = min(max(siny, -0.9999), 0.9999)
        worldcoords = (256 * (0.5 + latlong.lon / 360), 256 * (0.5 - log((1 + siny)/(1 - siny)) / (4 * pi)))
        scale = 1 << ZOOMLEVEL
        return floor(worldcoords[0] * scale), floor(worldcoords[1] * scale)