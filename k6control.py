import sys
import time
import json
import datetime
import requests
import curses
import random
from math import log10, pow

k6_url = "http://localhost:6565"

def main(stdscr):

    # Create a Communicator object that can talk to the running k6 instance
    k6 = Communicator(k6_url)
    
    # Init curses
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.clear()

    dbgwindow = DbgWindow(stdscr)
    dbgwindow.update("Starting...")

    # Fetch some initial data from k6
    k6.fetch_data()
    last_fetch = time.time()
    start_time = last_fetch
    update_interval = 1

    # Init onscreen curses windows
    vu_window = VUWindow(stdscr, dbgwindow)
    vu_window.update(k6)
    status_window = StatusWindow(stdscr)
    status_window.update(k6)

    stdscr.refresh()
    update = False

    # Main loop
    while True:
        c = stdscr.getch()
        if c == ord('q'):
            return
        if c == ord('p') or c == ord('P'):
            # PATCH back last status msg, with "paused" state inverted
            payload = {"data":k6.status[-1][1]}
            payload['data']['attributes']['paused'] = (not payload['data']['attributes']['paused'])
            r = requests.patch(k6_url + "/v1/status", data=json.dumps(payload))
            k6.fetch_status()
            update = True
        if c == ord('+'):
            # PATCH back last status msg, with "vus" increased
            payload = {"data":k6.status[-1][1]}
            payload['data']['attributes']['vus'] = payload['data']['attributes']['vus'] + 1
            r = requests.patch(k6_url + "/v1/status", data=json.dumps(payload))
            k6.fetch_status()
            update = True
        if c == ord('-'):
            # PATCH back last status msg, with "vus" decreased
            payload = {"data":k6.status[-1][1]}
            payload['data']['attributes']['vus'] = payload['data']['attributes']['vus'] - 1
            r = requests.patch(k6_url + "/v1/status", data=json.dumps(payload))
            k6.fetch_status()
            update = True
        # Check for a terminal resize event and recalculate window sizes if there was one
        if c == curses.KEY_RESIZE:
            stdscr.erase()
            vu_window.resize()
            dbgwindow.resize()
            status_window.resize()
            update = True
        # If new data has been fetched or terminal has been resized, recreate window contents
        if update:
            vu_window.update(k6)
            status_window.update(k6)
            update = False
        # If it is time to fetch new data, do so and set update flag so window contents will be recreated
        if time.time() > (last_fetch + update_interval):
            k6.fetch_data()  # this can take a bit of time = fairly likely a terminal resize event happens
            last_fetch = time.time()            
            update = True      # don't update windows immediately, in case terminal has been resized
        # Tell curses to update display, if necessary
        curses.doupdate()
        
class Communicator:
    def __init__(self, k6_address):
        self.k6_address = k6_address
        self.status = []
        self.metrics = []
        self.vus = []
    def fetch_status(self):
        t = datetime.datetime.now()
        r = requests.get(self.k6_address + "/v1/status")
        data = r.json()['data']
        self.status.append((t, data))
        self.vus.append((t, data['attributes']['vus']))
    def fetch_metrics(self):
        t = datetime.datetime.now()
        r = requests.get(self.k6_address + "/v1/metrics")
        data = r.json()['data']
        self.metrics.append((t, data))
    def fetch_data(self):
        self.fetch_status()
        self.fetch_metrics()
        #for metric in data:
        #    if metric['type'] == "metrics" and metric['id'] == "vus":
        #        self.vus.append((t, metric['attributes']['sample']['value']))

class VUWindow:
    def __init__(self, stdscr, dbgwindow):
        self.stdscr = stdscr
        self.dbgwindow = dbgwindow
        self.resize()
    def resize(self):
        stdscr_height, stdscr_width = self.stdscr.getmaxyx()
        self.height = int(stdscr_height - 5)
        self.width = int(0.6 * stdscr_width)
        self.win = self.stdscr.subwin(self.height, self.width, 0, int(stdscr_width*0.4+0.5))
        self.win.bkgd(' ', curses.color_pair(1))
        self.chart_width = self.width - 12
        self.chart_height = self.height - 7
    def update(self, data):
        self.win.clear()
        self.win.box()
        # We can display chart_width # of data points - retrieve that many
        if len(data.vus) > self.chart_width:
            points = data.vus[-self.chart_width:]
        else:
            points = data.vus
        if len(points) < 1:
            return
        # Find largest sample value in the series, and first and last timestamp
        maxval = 0
        for point in points:
            t, val = point
            if val > maxval:
                maxval = val
        # Calculate an appropriate range and tick interval for the Y axis
        if maxval > 0:
            magnitude = int(pow(10, log10(maxval)))
            ymax = int(magnitude * int(maxval/magnitude) * 1.2)
        else:
            ymax = 1
        ytick = float(ymax) / 2.0
        # Calculate an appropriate tick interval for the X (time) axis
        xtick = (points[-1][0] - points[0][0]) / 3
        # Plot X and Y axis ticks
        self.win.addstr(1, 2, "VU")
        for i in range(3):
            ypos = 3 + self.chart_height - int( (float(self.chart_height)/2.0) * float(i) )
            s = str(int(i * ytick))
            self.win.addstr(ypos, 1 + 2-int(len(s)/2), s)
            self.win.addstr(ypos, 0, "-")
        # Plot the values
        for i in range(len(points)):
            bar_position = 7 + self.chart_width - len(points) + i
            t, val = points[i]
            bar_height = int(float(self.chart_height) * (float(val)/float(ymax)))
            self.win.vline(4 + self.chart_height - bar_height, bar_position, '#', bar_height)
            if i==0 or i==self.chart_width-1 or i==int((self.chart_width-1)/2):
                self.win.addstr(self.height-2, bar_position, "|")
                self.win.addstr(self.height-1, bar_position - 3, t.strftime("%H:%M:%S"))
            if i==len(points)-1:
                s = "%d VU" % val
                self.win.addstr(1 + self.chart_height - bar_height, bar_position - int(len(s)/2), s, curses.A_REVERSE)
                self.win.addstr(2 + self.chart_height - bar_height, bar_position, "|")
        self.win.noutrefresh()

class StatusWindow:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.resize()
    def resize(self):
        stdscr_height, stdscr_width = self.stdscr.getmaxyx()
        self.height = (stdscr_height - 5) / 2
        self.width = int(stdscr_width*0.4)
        self.win = self.stdscr.subwin(self.height, self.width, 0, 0)
        self.win.bkgd(' ', curses.color_pair(1))
    def update(self, data):
        self.win.clear()
        self.win.box()
        status = data.status[-1][1]['attributes']
        self.win.addstr(1, (self.width-14)/2-1, "k6 test status")
        self.win.addstr(3, 2, "Running: ")
        self.win.addstr(3, 11, str(status['running']), curses.A_REVERSE)
        self.win.addstr(4, 2, " Paused: ")
        self.win.addstr(4, 11, str(status['paused']), curses.A_REVERSE)
        self.win.addstr(4, 17, "(P = toggle)")
        self.win.addstr(5, 2, "Tainted: ")
        self.win.addstr(5, 11, str(status['tainted']), curses.A_REVERSE)
        self.win.addstr(7, 2, "vus-max: %d" % status['vus-max'])
        self.win.addstr(8, 6, "vus: ")
        self.win.addstr(8, 11, str(status['vus']), curses.A_REVERSE)
        self.win.addstr(8, 16, "(+/- to change)")
        #self.win.addstr(1, 16, "%s" % status['running'], curses.A_REVERSE)
        #self.win.addstr(2, 2, "Test paused: ")
        #self.win.addstr(2, 15, "%s (P to toggle)" % status['paused'], curses.A_REVERSE)
        self.win.noutrefresh()
    

class DbgWindow:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.resize()
    def resize(self):
        stdscr_height, stdscr_width = self.stdscr.getmaxyx()
        self.height = 5
        self.width = int(stdscr_width)
        self.win = self.stdscr.subwin(self.height, self.width, stdscr_height-5, 0)
        self.win.bkgd(' ', curses.color_pair(1))
    def update(self, text):
        self.win.clear()
        self.win.box()
        self.win.addstr(1, 2, text)
        self.win.noutrefresh()
    
    

if __name__ == "__main__":
    curses.wrapper(main)