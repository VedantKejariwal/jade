# combo HTTP server (GETs) and key/value store (POSTs)
# uses a json file to save user state

try:
    from BaseHTTPServer import BaseHTTPRequestHandler
    import SocketServer as socketserver
except:
    # python 3 compatibility
    from http.server import BaseHTTPRequestHandler
    import socketserver

import mimetypes
import posixpath
import shutil
import os
import cgi
import json
import atexit
import urllib

jsonfile = input("Enter the name of the json file to use (leave blank for default 'labs.json'): ")
if jsonfile == '': jsonfile = 'labs.json'

PORT = input("Enter the port number to use (leave blank for default 8000): ")
if PORT == '': PORT = 8000
else: 
    try:
        PORT = int(PORT)
    except ValueError:
        print("WARNING: Invalid port number, using default port 8000")
        PORT = 8000

print(f"INFO: Loading {jsonfile} in directory {os.getcwd()}")

class JadeRequestHandler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):
        #print format % args
        return

    # serve up static files
    def do_GET(self):
        path = self.path
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = path.replace('/','')
        if path == '': path = 'index.html'
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None
        try:
            self.send_response(200)
            self.send_header("Content-type", ctype)
            fs = os.fstat(f.fileno())
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()

            shutil.copyfileobj(f,self.wfile)
            f.close()
        except:
            f.close()
            raise

    def do_POST(self):
        # determine key, value
        ctype, pdict = cgi.parse_header(self.headers['content-type'])
        postvars = {}
        if ctype == 'multipart/form-data':
            for k,v in cgi.parse_multipart(self.rfile, pdict).items():
                # python3 returns everything as bytes, so decode into strings
                if type(k) == bytes: k = k.decode()
                postvars[k] = [s.decode() if type(s) == bytes else s for s in v]
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            content = self.rfile.read(length)
            for k,v in urllib.parse.parse_qs(content, keep_blank_values=1).items():
                # python3 returns everything as bytes, so decode into strings
                if type(k) == bytes: k = k.decode()
                postvars[k] = [s.decode() if type(s) == bytes else s for s in v]

        key = postvars.get('key',[None])[0]
        value = postvars.get('value',[None])[0]
        name = postvars.get('name',[None])[0]
        self.log_message('%s',json.dumps([key,value]))
        
        # read json file with user's state
        try: 
            global jsonfile
            if (name is not None):
                jsonfile = name
                print(f"INFO: Switching to JSON file {jsonfile}")
            with open(jsonfile,'r') as f:
                labs = json.load(f)
        except json.JSONDecodeError:
            print("ERROR: JSON file is not formatted correctly. Is this the correct file?")
            exit()
        except Exception as e:
            print("ERROR: An error occurred while reading the JSON file:",e)
            exit()

        response = ''
        if value is None:
            # send state for particular lab to user
            response = labs.get(key,'{}')
            response = response.encode('utf-8')
        else:
            # update state for particular lab
            response = value
            labs[key] = value
            with open(jsonfile,'w') as f:
                json.dump(labs,f)
                                                        
        self.send_response(200)
        self.send_header("Content-type", 'text/plain')
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        if (type(response) == str):
            response = response.encode('utf-8')
        self.wfile.write(response)

    def guess_type(self, path):
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream', # Default
    })
        
httpd = socketserver.TCPServer(("",PORT),JadeRequestHandler)

def cleanup():
  # free the socket
  print("INFO: CLEANING UP!")
  httpd.shutdown()
  print("INFO: CLEANED UP")

if (os.path.exists(jsonfile) == False):
    print("ERROR: No JSON file found, are you sure you entered the correct name / directory?")
    exit()
else:
    print("INFO: Requested file found, starting server...")
atexit.register(cleanup)
print("INFO: Jade Server: port",PORT)
print(f"INFO: Access Jade in a web browser here: http://localhost:{PORT}/jade.html")
httpd.serve_forever()