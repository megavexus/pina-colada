import socket
import threading
import os
import traceback
import random
import base64
import importlib
import inspect
import sys
import zlib
import core

from Crypto.Cipher import AES
from Crypto import Random
from Crypto.Util import number
from datetime import datetime

VERBOSE = True

BS = AES.block_size
pad = lambda s: s + (BS - len(s) % BS) * chr(BS - len(s) % BS)
unpad = lambda s: s[0:-ord(s[-1])]

SEP = "|:|"
END_SEP = "!:!"
MSG = 0
NEWC = 1
CLOSE = 2
INFO = 3
REQ = 4
RELOAD = 5


def get_date():
    return "%02d:%02d:%02d" % (datetime.now().hour, datetime.now().minute, datetime.now().second)

class PinaColadaServer():

    def __init__(self, name, port):
        self.name = name
        self.port = port
        self.handlers = {}
        self.client_handlers = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        self.core = core.PinaColada()
        self.SERVER_VERSION = 0.5

        self.clients = {}
        self.threads = {}
        self.ips = {}
        self.ids = {}
        self.blocks = []
        self.keys = {}

    #################################################################
    #
    # Server Handling
    #
    #################################################################

    def server(self):
        try:
            try:
                self.socket.bind(("0.0.0.0", self.port))
            except socket.error:
                print("[!] %s startup failed - can't bind to %s:%d" % (self.name, "0.0.0.0", self.port))
                return
            self.socket.listen(10000)
            sys.stdout.write("[*] %s startup successful - listening on %s:%s\n" % (self.name, "0.0.0.0", self.port))
            sys.stdout.flush()
            while True:
                client, addr = self.socket.accept()
                cid = random.randint(0, 99999)
                self.ips[cid] = addr[0]
                print("[*] Accepted connection from %s:%d - ID: %d" % (addr[0], addr[1], cid)),

                self.threads[cid] = threading.Thread(target=self.handle_client, args=(client, cid))
                self.threads[cid].start()
        except Exception as exc:
            print exc
            self.print_exc(exc, "")
            self.shutdown()
        finally:
            self.shutdown()

    def shutdown(self):
        print("[!] Shutting down %s..." % self.name)
        self.socket.close()
        for sock in self.clients:
            self.clients[sock].send("[!] Shutting down server...")
            self.close(sock)

    #################################################################
    #
    # Client Handling
    #
    #################################################################

    def handle_client(self, c, id):
        try:
            #Diffie-Helmen Exchange
            shared_prime = number.getPrime(10)
            shared_base = number.getPrime(10)
            server_secret = random.randint(0, 99)
            c.send(str(shared_prime) + "|" + str(shared_base))
            a = ((shared_base**server_secret) % shared_prime)
            c.send("%ld" % a)  # send A
            b = long(c.recv(1024))  # receive B
            self.keys[c] = pad("%ld" % ((b ** server_secret) % shared_prime))

            _, name, name = self.unpack_data(self.decrypt(c.recv(1024), c))
            name = name.replace(END_SEP, "").replace(SEP, "")
            print("(%s)" % name)
            self.ids[id] = name
            self.clients[id] = c

        except Exception as e:
            self.print_exc(e, "\n[!] Failed to initialize client connection for %d." % id, always=True)
            self.close(id)
            return False
        try:
            while True:
                d = c.recv(1024)
                msgs = filter(None, self.decrypt(d, c).split(END_SEP))
                for m in msgs:
                    self.inbound(m, c)
                #print d

        except Exception as e:
            self.print_exc(e, "")
            print("[!] Connection closed from client %d (%s) - %s" % (id, self.ids[id], self.ips[id]))
            self.close(id)

    def inbound(self, d, c):
        message_type, name, data = self.unpack_data(d)
        print("%s : %s (%d|%s): %s" % (get_date(), name, self.get_id(c), message_type, data))
        pass # TODO HANDLE INBOUND COMMANDS

    def get_id(self, c):
        id = [id for id in self.clients if self.clients[id] == c]
        return id[0] if id != [] else 0

    def get_ids_by_name(self, name):
        return [id for id in self.ids if self.ids[id] == name]

    def get_client_name(self, client):
        try:
            return self.ids[self.get_id(client)]
        except KeyError:
            return None
    #################################################################
    #
    # Command Handling
    #
    #################################################################

    def cmdloop(self, cmd):
        key = cmd.split()[0]
        if key == "clients":
            if len(self.ids.values()) == 0:
                print "[*] No currently connected clients"
            else:
                c_id = list()
                for id in self.ids:
                    c_id.append("<%s, %d>" % (self.ids[id], id))
                print "[*] Currently connected clients: " + ", ".join(c_id)

    def command(self, c, data):
        data = data.lower()
        if data == "\\help":
            self.direct(MSG, c, self.build_help())
        elif data == "\\info":
            self.direct(MSG, c, "[*] %s" % self.get_versions())
        elif data == "\\clients":
            self.send_cur_clients(c)
        else:
            self.direct(MSG, c, "[!] Unknown command %s." % data)

    # TODO BUG
    def close(self, id):
        try:
            self.direct(CLOSE, self.clients[id], "[!] You have been disconnected from the server.")
        except:
            pass
        finally:
            try:
                self.clients[id].close()
            except:
                pass
            try:
                self.clients.pop(id)
                self.ids.pop(id)
            except:
                pass

    
    def safe_command(self, cmd, expected):
        return cmd != "" and len(cmd.split()) >= expected

    ####################################################################
    #
    # Message Handling
    #
    ####################################################################

    def encrypt(self, string, c):
        iv = Random.new().read(AES.block_size)
        cipher = AES.new(self.keys[c], AES.MODE_CBC, iv)
        return base64.b64encode(iv + cipher.encrypt(pad(zlib.compress(string))))

    def decrypt(self, msg, c):
        enc = base64.b64decode(msg)
        cipher = AES.new(self.keys[c], AES.MODE_CBC, enc[:16])
        return zlib.decompress(unpad(cipher.decrypt(enc[16:])))

    def direct(self, msg_type, c, msg):
        c.send(self.encrypt(self.pack_data(msg_type, "SERVER", msg), c))

    def unpack_data(self, msg):
        msgs = [self.replace_seps(s) for s in msg.split(SEP)]
        try:
            msgs[0] = int(msgs[0])  # convert type to int
        finally:
            return msgs

    def pack_data(self, type, name, data):
        return (str(type) + SEP + self.save_seps(name) + SEP + self.save_seps(data) + END_SEP)

    def replace_seps(self, message):
        return str(message).replace("|::|", SEP).replace("!::!", END_SEP)

    def save_seps(self, message):
        return str(message).replace(SEP, "|::|").replace(END_SEP, "!::!")


    def message(self, name, msg):
        if not self.get_ids_by_name(name):
            print("[!] No client by name %s connected." % name)
        for id in self.get_ids_by_name(name):
            self.direct(MSG, self.clients[id], "SERVER: " + msg)

    def print_exc(self, e, msg, always=False):
        if always or VERBOSE:
            print msg
        if VERBOSE:
            print e
            traceback.print_exc()

sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)  # force a flushed output for all prints
if __name__ == "__main__":
    threads = {}
    servers = {}
    
    servers["PinaColada"] = PinaColadaServer("PinaColada", 9999)
    for c in servers:
        threads[c] = threading.Thread(target=servers[c].server)
        threads[c].start()
    try:
        while True:
            sys.stdout.write("Pina Colada >> ")
            cmd = raw_input("")

            if not cmd:
                continue

            cmds = cmd.split()

            chatrooms[context].cmdloop(cmd)

    except KeyboardInterrupt:
        print("[!] Exiting...")
    except Exception as e:
        print e
        servers[0].print_exc(e, "")
    finally:
        for c in servers:
            servers[c].shutdown()
            threads[c].join()
        os._exit(0)