#!/usr/bin/env python
# CICS.py - A class to do asynchronous polling / listening of a Codan NGT via the CICS interface. 
#
# Copyright 2015 Mark Jessop <vk5qi@rfhead.net>
#
# 
# This library is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public License
# along with this library.  If not, see <http://www.gnu.org/licenses/>.

import serial, thread, logging
from decimal import Decimal
from datetime import datetime


class CICS(object):

    current_state = {
    "channel": "Unknown",
    "freq": "Unknown",
    "sideband": "Unknown",
    "scanning": "Unknown",
    "call": "Unknown",
    "link_state": "Unknown"
    }

    stations = {
    "VK5QI": {"id":1337, "lat":"Unknown", "lon":"Unknown", "lastheard":"Unknown"}
    }

    running = True # This is set false when we want to kill the rx thread.

    def __init__(self, serial_device = '/dev/ttyS0', serial_baud = 9600):
        try:
            self.s = serial.Serial(serial_device, serial_baud, timeout=1)
        except serial.serialutil.SerialException as e:
            print "ERROR:",e
        thread.start_new_thread(self.rx_thread, ())

    def close(self):
        running = False
        self.s.close()

    def write(self,data):
        self.s.write(data + "\r\n")

    def rx_thread(self):
        while(self.running):
            try:
                line = self.s.readline()
                if(len(line)>0):
                    self.parseline(line)
            except: # Catch errors caused by the serial port being closed during a read operation.
                pass


    # Functions to poll various NGT functions.
    def poll_state(self):
        # Poll the current scan state, channel, and frequency
        self.write("scan")
        self.write("chan")
        self.write("freq")
        self.write("sb")

    def poll_gps_by_id(self,id):
        self.write("gpsbeacon %04d -lbt" % int(id))
        return

    def poll_gps_by_callsign(self, callsign):
        try:
            id = self.stations[callsign]["id"]
            self.poll_gps_by_id(id)
        except:
            print "Unknown Callsign"
            return

    # Functions to parse data from the NGT
    # These all run asynchronously in the RX thread.

    def parseline(self, data):
        print data
        # Pretty messy function, just looking for keywords atm.
        if data.startswith(">"):
            # CICS Prompt, discard.
            return
        elif data.startswith("FREQ:"):
            # Current Frequency Report
            self.parse_freq(data)
            return
        elif data.startswith("CHAN:"):
            # Current Channel
            self.parse_chan(data)
            return
        elif data.startswith("SCAN:"):
            # Scan State
            self.parse_scan(data)
            return
        elif data.startswith("SIDEBAND:"):
            # Sideband
            self.parse_ssb(data)
            return
        elif data.startswith("CALL"):
            # Call State Info
            self.parse_call(data)
            return
        elif data.startswith("LINK:"):
            # Link State
            self.parse_link(data)
            return
        elif data.startswith("GPS-POSITION:"):
            # GPS Position report from someone!
            self.parse_gps_pos(data)
            return
        else:
            # Unknown.
            return

    def parse_gps_pos(self,data):
        #  GPS-POSITION:   'Ham CODAN 005',   1542,   1882, 17/08 14:45, 2753.0015, S, 14023.6726, E, 051521\r\n
        # Format is: Channel, source id, dest id, local time (DD/MM HH:MM), lat (DDMM.MMMM), S/N, lon (DDDMM.MMM), E/W, UTC time (HHMMSS)
        try:
            gps_data = data.split(",")
            source_call = int(gps_data[1])
            dest_call = int(gps_data[2])
            call_time = gps_data[3].strip()
            call_lat = gps_data[4].strip()
            call_lat_sign = gps_data[5].strip()
            call_lon = gps_data[6].strip()
            call_lon_sign = gps_data[7].strip()
            call_remote_utc = gps_data[8].strip()

            # Extract Latitude
            lat = Decimal(call_lat[:2]) + (Decimal(call_lat[2:])/Decimal(60))
            if call_lat_sign == "S":
                lat = lat*-1

            # Extract Longitude
            lon = Decimal(call_lon[:3]) + (Decimal(call_lat[3:])/Decimal(60))
            if call_lon_sign == "W":
                lon = lon * -1

            # Write to log.
            logging.info("RX GPS Position: %d,%s,%.5f,%.5f" % (source_call,call_time,lat,lon))

            # Search through station database and update matching callsigns
            for k in self.stations.iteritems():
                if k[1]["id"] == source_call:
                    k[1]["lat"] = lat
                    k[1]["lon"] = lon
                    k[1]["lastheard"] = datetime.utcnow()
                    logging.info("ID Matched Callsign %s." % k[0])
        except:
            return

    def parse_call(self,data):
        try:
            call = data.split(" ")[1]
            self.current_state["call"] = call.rstrip('\r\n')
            logging.info("Call Event: %s" % self.current_state["call"])
        except:
            return

    def parse_link(self,data):
        try:
            link = data.split(" ")[1]
            self.current_state["link_state"] = link.rstrip('\r\n')
            logging.info("Link Event: %s" % self.current_state["link_state"])
        except:
            return

    def parse_freq(self,data):
        # "FREQ: 7044.0 RX/TX\r\n"
        try:
            freq = data.split(" ")[1]
            self.current_state["freq"] = freq.rstrip('\r\n')
            logging.info("Frequency Update: %s" % self.current_state["freq"])
        except:
            return

    def parse_ssb(self,data):
        # "SIDEBAND: USB\r\n"
        try:
            ssb = data.split(" ")[1]
            self.current_state["sideband"] = ssb.rstrip('\r\n')
            logging.info("Sideband Update: %s" % self.current_state["sideband"])
        except:
            return

    def parse_chan(self,data):
        # "CHAN: 'Ham CODAN 003'\r\n"
        try:
            chan = data.split("'")[1]
            self.current_state["channel"] = chan.rstrip('\r\n')
            logging.info("Channel Update: %s" % self.current_state["channel"])
        except:
            return

    def parse_scan(self,data):
        # "SCAN: OFF"
        try:
            scanning = data.split(" ")[1]
            self.current_state["scanning"] = scanning.rstrip('\r\n')
            logging.info("Scan State: %s" % self.current_state["scanning"])
        except:
            return


logging.basicConfig(filename='activity.log',level=logging.DEBUG,format='%(asctime)s %(message)s',datefmt='%m/%d/%Y %I:%M:%S %p')