from kivy.app import App
from kivy.uix.settings import SettingsWithTabbedPanel
from kivy.uix.boxlayout import BoxLayout
import sys, os
import webbrowser
from stravalib.client import Client
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import re, datetime, struct, sys, time
from datetime import timedelta
from kivy.clock import Clock, mainthread
from kivy.config import Config
from kivy.core.image import Image as CoreImage
import io
import sys
from maps import LatLong, MapData
from kivy.uix.popup import Popup
from video import RideVideo
from kivy.core.window import Window
from kivy.uix.button import Button
import threading, bisect
from customlayout import CustomLayout

class ProgressDialog(BoxLayout):
    pass

class RideOverlay(BoxLayout):
    @staticmethod
    def open_settings():
        App.get_running_app().open_settings()


class ListFileName(Button):
    def on_release(self):
        del App.get_running_app().videoselect.ids.listview.data[self.index]
        for i, b in enumerate(App.get_running_app().videoselect.ids.listview.data):
            b['index'] = i


class VideoSelect(BoxLayout):
    def __init__(self, **kwargs):
        self.videolist = []
        self.total_duration = 0.0
        super(VideoSelect, self).__init__(**kwargs)

    def _add_video(self, filename):
        v = RideVideo(filename)
        position = bisect.bisect([c.creation_time for c in self.videolist], v.creation_time)
        self.videolist[position:position] = [v]
        self.total_duration += v.video_duration
        relative_start_time = 0
        if position > 0:
            relative_start_time = self.videolist[position-1].relative_start_time + \
                                  self.videolist[position-1].video_duration

        for vid in self.videolist[position:]:
            vid.relative_start_time = relative_start_time
            relative_start_time += vid.video_duration

    def file_dropped(self, window, file_path):
        if self.ids.file_drag.collide_point(*window.mouse_pos):
            self.ids.listview.data.append({'text': file_path.decode('utf-8'),
                                           'index': len(self.ids.listview.data)})

    def read_video_files(self):
        app = App.get_running_app()
        del self.videolist
        self.videolist = []
        for f in self.ids.listview.data:
            app.update_popup(f['text'])
            self._add_video(f['text'])
        app.dismiss_popup()

        app = App.get_running_app()
        app.pagelayout.next_page()

    def next(self):
        App.get_running_app().open_popup('Getting video data...')
        threading.Thread(target=self.read_video_files).start()

class Auth(BoxLayout):
    def next(self):
        app = App.get_running_app()
        app.pagelayout.next_page()

    def prev(self):
        App.get_running_app().pagelayout.prev_page()

    def get_video_activity(self):
        App.get_running_app().open_popup('Getting Strava data...')
        threading.Thread(target=self.get_video_activity_real).start()

    def get_video_activity_real(self):
        app = App.get_running_app()
        # app.video = RideVideo('test.mp4')
        # video_start = app.video.creation_time
        # video_end = video_start + app.video.duration
        client = app.stravaclient
        c = app.config
        client.access_token = c.get('Settings', 'strava_access_token')
        athlete = client.get_athlete()
        activities = client.get_activities()
        for a in activities:
            activity_start = time.mktime(a.start_date_local.timetuple())
            activity_end = activity_start + (a.elapsed_time / timedelta(seconds=1))

            for v in app.videoselect.videolist:
                video_start = v.creation_time
                video_end = video_start + v.video_duration
                if video_start <= activity_start <= video_end:
                    app.update_popup("activity {} starts in video".format(a.id))
                    app.activity = a
                    app.stream = client.get_activity_streams(a.id, types=['time','latlng','velocity_smooth','heartrate','cadence','temp'])
                if video_start <= activity_end <= video_end:
                    app.update_popup("activity {} ends in video".format(a.id))
                if activity_start <= video_start and video_end <= activity_end:
                    app.update_popup("video entirely within activity {}".format(a.id))
                    app.activity = a
                    app.stream = client.get_activity_streams(a.id, types=['time','latlng','velocity_smooth','heartrate','cadence','temp'])

        if app.stream:
            app.mapdata = MapData(app.stream)
            app.stream['images'] = [None] * len(app.stream['latlng'].data)
            for i, latlng in enumerate(app.stream['latlng'].data):
                position = LatLong(latlng)
                tile = app.mapdata.get_point_tile(position)
                if tile:
                    im = tile.draw_point(position)
                    app.stream['images'][i] = im

        app.dismiss_popup()


class Sync(BoxLayout):
    def __init__(self):
        self._initialized = False
        self._mapoffset = 0
        self.video_index = 0
        self.current_video_pos = 0
        super(Sync, self).__init__()

    def prev(self):
        App.get_running_app().pagelayout.prev_page()

    def video_loaded(self):
        self.ids.video.seek(0)

    def state(self, st):
        pass

    def on_parent(self, widget, parent):
        if parent is not None and self._initialized is False:
            self.ids.video.source = App.get_running_app().videoselect.videolist[0].source
            self._initialized = True

        if parent is None:
            self.ids.video.state = 'pause'

    def jump(self):
        videos = App.get_running_app().videoselect
        if self.ids.video.eos:
            if self.video_index < len(videos.videolist)-1:
                self.video_index += 1
                self.current_video_pos = 0
                self.ids.video.source = videos.videolist[self.video_index].source
                self.ids.video.state = 'play'
            else:
                self.video_index = 0
                self.current_video_pos = 0

    def change(self, data, *largs):
        data.seek(0)
        test = CoreImage(data, ext='png')
        self.ids.mapimage.texture = test.texture

    def update_ride_data(self):
        app = App.get_running_app()
        videos = app.videoselect
        if app.stream:
            video_start = videos.videolist[self.video_index].creation_time
            activity_start = time.mktime(app.activity.start_date_local.timetuple())
            timeindex = round(self.ids.video.position - (activity_start - video_start))
            try:
                loc = app.stream['time'].data.index(timeindex) + self._mapoffset
                print("loc {}".format(loc))
                if loc >= 0:
                    self.ids.speed.text = "Speed: {}".format(
                        round(app.stream['velocity_smooth'].data[loc]*2.23694, 1))
                    self.ids.cadence.text = "Cadence: {}".format(app.stream['cadence'].data[loc])
                    self.ids.heartrate.text = "HR: {}".format(app.stream['heartrate'].data[loc])
                    # self.redraw_map()
                    if app.stream['images'][loc]:
                        output = io.BytesIO()
                        app.stream['images'][loc].save(output, format='PNG')
                        Clock.schedule_once(lambda dt: self.change(output), 0)
                    else:
                        print("no image")
                        position = LatLong(app.stream['latlng'].data[loc])
                        tile = app.mapdata.getTilePoint(position)
                        if tile:
                            im = tile.draw_point(position)
                            output = io.BytesIO()
                            im.save(output, format='PNG')
                            Clock.schedule_once(lambda dt: self.change(output), 0)
            except ValueError as e:
                pass

    #
    # def redraw_map(self):
    #     app = App.get_running_app()
    #
    #     print("position {}".format(self.ids.video.position))
    #     if app.stream and app.video:
    #         video_start = app.video.creation_time
    #         activity_start = time.mktime(App.get_running_app().activity.start_date_local.timetuple())
    #         timeindex = round(self.ids.video.position - (activity_start - video_start)) + self._mapoffset
    #         loc = app.stream['time'].data.index(timeindex)
    #         if loc >= 0 and app.stream['images'][loc]:
    #             output = io.BytesIO()
    #             app.stream['images'][loc].save(output, format='PNG')
    #             Clock.schedule_once(lambda dt: self.change(output), 0)

    def plusmap(self):
        self._mapoffset += 1
        self.update_ride_data()
        # self.redraw_map()

    def minusmap(self):
        self._mapoffset -=1
        self.update_ride_data()
        # self.redraw_map()

    def play(self):
        self.ids.slider.opacity = 100
        self.ids.video.size_hint_y = 1
        self.ids.video.source = App.get_running_app().videoselect.videolist[self.video_index].source
        self.ids.video.state = 'play'

    def pause(self):
        self.ids.video.state = 'pause'

    def duration(self):
        print("duration {} {}".format(self.ids.video.duration, self.ids.video.loaded))
        self.ids.slider.opacity = 100
        self.ids.video.size_hint_y = 1
        # video doesn't load unless I do this twice?
        self.ids.video.seek(self.current_video_pos)
        self.ids.video.seek(self.current_video_pos)

    def on_touch_down(self, touch):
        videos = App.get_running_app().videoselect
        if not self.ids.slider.collide_point(*touch.pos):
            return super(Sync, self).on_touch_down(touch)
        slider_pos = touch.pos[0]/self.ids.slider.width
        print(slider_pos)
        # figure out which video from the list is at this position
        total_video_pos = slider_pos * videos.total_duration
        old_video_index = self.video_index
        self.video_index = bisect.bisect([c.relative_start_time for c in videos.videolist], total_video_pos) - 1
        current_video = videos.videolist[self.video_index]
        self.current_video_pos = (total_video_pos - current_video.relative_start_time)/current_video.video_duration
        self.ids.video.source = current_video.source
        self.ids.video.seek(self.current_video_pos)

    def on_touch_move(self, touch):
        if not self.ids.slider.collide_point(*touch.pos):
            return super(Sync, self).on_touch_move(touch)
        self.on_touch_down(touch)

    def set_slider(self, pos):
        self.ids.slider.value = pos

    def position_change(self):
        app = App.get_running_app()
        videos = app.videoselect
        self.set_slider((100*(videos.videolist[self.video_index].relative_start_time+self.ids.video.position)) /
                        videos.total_duration)

        self.update_ride_data()

    def auth(self):
        c = App.get_running_app().config
        server_address = ('', 0)

        class handler_class(BaseHTTPRequestHandler):
            def do_GET(self):
                if re.search('/code/', self.path):
                    client = App.get_running_app().stravaclient
                    code = re.search('code=(.*?)$', self.path).group(1)
                    access_token = client.exchange_code_for_token(client_id=c.get('Settings', 'strava_client_id'),
                                                   client_secret=c.get('Settings', 'strava_oauth_secret'),
                                                   code=code)
                    c.set('Settings', 'strava_access_token', access_token)
                    c.write()
                    self.send_response(200)
                    self.end_headers()
                    response = '<body onload="window.close()">Authenticated to Strava. ' \
                               'You may now close this window</body>'
                    self.wfile.write(bytes(response, "utf-8"))
                    # shut down web server after responding
                    assassin = Thread(target=httpd.shutdown)
                    assassin.daemon = True
                    assassin.start()
                else:
                    self.send_response(404)
                    self.end_headers()

        httpd = HTTPServer(server_address, handler_class)
        thread = Thread(target=httpd.serve_forever)
        thread.start()
        authorize_url = App.get_running_app().stravaclient.authorization_url(client_id=c.get('Settings', 'strava_client_id'),
                                                 scope='view_private',
                                                 redirect_uri='http://localhost:{}/code/'.format(httpd.server_port))
        webbrowser.open(authorize_url)
        pass

class OverlayApp(App):
    def resource_path(self, relative_path=None):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        if relative_path:
            return os.path.join(base_path, relative_path)
        else:
            return base_path

    def build_config(self, config):
        config.setdefaults('Settings', {'strava_oauth_secret': '',
                                        'strava_client_id': '',
                                        'strava_access_token': '',
                                        'googlemaps_api_key': ''})

    def build_settings(self, settings):
        settings.add_json_panel('Settings', self.config, self.resource_path('Settings\Settings.json'))

    def keyboard(self, *args):
        if args[1] == 27:
            return True

    def open_popup(self, title):
        self.popup.title = title
        self.popup.open()

    @mainthread
    def update_popup(self, text):
        self.popup.content.ids.progresslabel.text = text

    def dismiss_popup(self):
        self.popup.title = ''
        self.popup.content.ids.progresslabel.text = ''
        self.popup.dismiss()

    def build(self):
        self.settings_cls = SettingsWithTabbedPanel
        self.stravaclient = Client()
        self.activity = None
        self.stream = None
        self.use_kivy_settings = False

        Config.set('input', 'mouse', 'mouse,multitouch_on_demand')
        Config.set('kivy', 'exit_on_escape', 0)
        inp = RideOverlay(orientation='vertical')
        self.pagelayout = CustomLayout()
        self.videoselect = VideoSelect()
        Window.bind(on_dropfile=self.videoselect.file_dropped)
        self.pagelayout.add_page(self.videoselect)

        self.stravaauth = Auth()
        self.pagelayout.add_page(self.stravaauth)
        self.sync = Sync()
        self.pagelayout.add_page(self.sync)
        inp.add_widget(self.pagelayout)
        Window.bind(on_key_down=self.keyboard)

        self.progressdialog = ProgressDialog()
        self.popup = Popup(title='', content=self.progressdialog,
                           size_hint=(.55, .3), auto_dismiss=False)

        return inp

OverlayApp().run()