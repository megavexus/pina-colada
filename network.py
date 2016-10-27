from scapy.all import *
import logging
from scans import *
import psycopg2
import time
import datetime


#All other computers should be in an array of type computer, having (so far) an ip and a MAC address.
class Computer(object):
    def __init__(self, ip, mac):
        self.ip = ip
        self.mac = mac


# The overall object, called master, creates its own ip, subnet, and list of other computers on the network.
# Fields:
#   ip -> the ip of this computer
#   subnet -> the cidr
#   otherComps -> a result of running arping against the network (gives back unparsed packets)
#   comps -> A list of the computers on the network

class Network(object):

    def __init__(self, core):
        self.core = core
        self.iface = self.core.default_iface  # TODO
        self.ip = self.core.get_local_ip(self.iface)
        self.cidr = self.core.get_cidr(self.iface)
        self.subnet = str(self.cidr.network)
        self.mac = self.core.get_local_mac(self.iface)
        #self.otherComps = self.arp_all()
        #self.comps = self.profile()
        self.conn = self.connect()
        self.cur = self.conn.cursor() if self.conn else None


    def arp_all(self):
        #try:

            return arping(self.subnet, verbose=0)
        #except:
        #    return []

    def profile(self):
        comps = []
        x, y = self.otherComps
        for item in x:
            a, b = item
            comps.append(Computer(a.pdst, b.src))
        comps.append(Computer(self.ip, self.mac))
        return comps

    def connect(self):
        try:
            return psycopg2.connect("dbname='network' user='aces' host='localhost' password='aces'")
        except:
            #logging.log(ERROR, "Could not connect to database")  TODO
            return None


def begin_scan(thisComp, portLow, portHigh):
    for comp in thisComp.comps:
        ports = syn_scan(comp.ip, (portLow, portHigh))
        ports = ','.join(ports)
        ts = time.time()
        st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        thisComp.cur.execute(" \
                UPDATE computers SET ip='{0}', ports='{1}', last_online='{2}' WHERE mac='{3}'; \
                INSERT INTO computers(ip,mac,ports,last_online) SELECT '{4}', '{5}', '{6}', '{7}' \
                WHERE NOT EXISTS (SELECT 1 FROM computers WHERE mac='{8}')" \
                .format(comp.ip, ports, st, comp.mac, comp.ip, comp.mac, ports, st, comp.mac))
    for network in wifi_scan():
        thisComp.cur.execute(" \
                UPDATE networks SET last_online='{0}' WHERE name='{1}'; \
                INSERT INTO networks(name, status, last_online) SELECT '{2}', 'online', '{3}' WHERE NOT EXISTS (SELECT 1 FROM networks WHERE name='{4}')" \
                .format(st, network, network, st, network))
    thisComp.conn.commit()
    thisComp.cur
    return thisComp

def init_network(core):
    print "Initializing Network DB..."
    thisComp = Network(core)
    
    try:
        pass#thread.start_new_thread(begin_scan, (thisComp, 22, 22))
    except Exception as e:
        print "Thread creation failed :("
        print e
    

    return thisComp



