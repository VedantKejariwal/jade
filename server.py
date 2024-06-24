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

        key = postvars.get('key',[None])[0] # key / lab name in JSON file
        value = postvars.get('value',[None])[0] # state for particular lab
        name = postvars.get('name',[None])[0] # for JSON switcher, name of JSON to switch to
        stop = postvars.get('stop',[None])[0] # signal to stop the server
        netlist = postvars.get('netlist',[None])[0] # netlist contents to save
        netlist_name = postvars.get('netlist_name',[None])[0] # name of new netlist file to save
        module = postvars.get('module',[None])[0] # name of module to save for module upload
        combine_name = postvars.get('combine_name',[None])[0] # name of new file to save for module combination
        files = postvars.get('files',[None])[0] # list of files to combine
        extra = postvars.get('extra',[None])[0] # additional info as needed for file combination
        self.log_message('%s',json.dumps([key,value]))
        
        # read json file with user's state
        try: 
            global jsonfile
            # Netlist Extraction
            if (netlist is not None and netlist_name is not None):
                netlist_name = netlist_name.replace('/','-')[1:] + '-netlist.json'
                print("INFO: Saving netlist to file: ",netlist_name)
                with open(netlist_name,'w') as f:
                    f.write(netlist)
            # Module Extraction
            elif (module is not None):
                try:
                    self.module_extraction(module)
                except Exception as e:
                    print("ERROR: Could not save module info", e)
                    self.send_error(e)
            # Module/File Combination
            elif (combine_name is not None and files is not None):
                try:
                    self.module_combination(combine_name, files, extra)
                    return
                except Exception as e:
                    print("ERROR: Could not combine files:",e)
                    self.send_error(e)
            # JSON Switcher
            elif (name is not None):
                savedFile = jsonfile
                jsonfile = name
                print(f"INFO: Switching to JSON file {jsonfile}")
            # Used in all operations, particularly when updating current state
            with open(jsonfile,'r') as f:
                labs = json.load(f)
        except json.JSONDecodeError:
            response = 'Bad JSON file format. Please check the JSON file and try again.'
            self.send_response(422)
            self.send_header("Content-type", 'text/plain')
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            if (type(response) == str):
                response = response.encode('utf-8')
            self.wfile.write(response)

            if (name is not None): # JSON Switch failed, revert to saved file
                jsonfile = savedFile
                print(f"ERROR: JSON file {name} is not formatted correctly. Keeping {savedFile} as the current JSON file")
                return
            else: # Initial JSON file is not formatted correctly
                print(f"ERROR: JSON file {jsonfile} is not formatted correctly. Please check the JSON file and try again.")
                print("INFO: Terminating server...")
                exit()
        except Exception as e:
            print("ERROR: A fatal error occurred while reading the JSON file:",e)
            print("INFO: Terminating server...")
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
        if (stop is not None and stop == "TRUE"):
            print("INFO: Request to stop web server received. Terminating web server...")
            exit() # Assuming the server does in fact get shutdown, not really checking.

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

    def module_extraction(self, module):
        jsoncontent = {}
        with open(jsonfile,'r') as jsonfile_FP:
            jsoncontent = json.load(jsonfile_FP)
        
        jsoncontent = {k: v for k, v in jsoncontent.items() if k == "/jade.html"}
        
        inner_data = json.loads(jsoncontent["/jade.html"])
        inner_data["tests"] = {k: v for k, v in inner_data["tests"].items() if k == module}
        inner_data["state"] = {k: v for k, v in inner_data["state"].items() if k == module}
        
        jsoncontent["/jade.html"] = json.dumps(inner_data)
        new_file_name = module.replace('/','-')[1:] + '-save.json'
        
        with open(new_file_name,'w') as f:
            f.write(json.dumps(jsoncontent))
        
        print("INFO: Saved module info to file: ",new_file_name)

    def module_combination(self, file_name, files, extra):
        module_names = {}
        result_jsoncontent = {}
        jsoncontent = {}
        files = files[1:-2].replace('"','').split(',')

        for file in files:
            try:
                with open(file,'r') as jsonfile_FP:
                    jsoncontent = json.load(jsonfile_FP)
            except FileNotFoundError:
                raise Exception(f"File {file} not found. Please check the file names and try again.")
            except json.JSONDecodeError:
                raise Exception(f"File {file} is not formatted correctly. Please check the file and try again.")
            except Exception as e:
                raise Exception(e)
            jsoncontent = {k: v for k, v in jsoncontent.items() if k == "/jade.html"}
            innercontent = json.loads(jsoncontent["/jade.html"])

            for key, value in innercontent["state"].items():
                if key not in module_names:
                    module_names[key] = {'filename': [file], 'count': 1}
                else:
                    module_names[key]['filename'].append(file)
                    module_names[key]['count'] += 1

        noConflicts = True
        # Conflicts resolved by user in previous request
        if extra is not None:
            extra = json.loads(extra)
            for key, value in module_names.items():
                if module_names[key]['count'] != 1 and key in extra:
                    module_names[key]['filename'] = [extra[key]]
                    module_names[key]['count'] = 1

        # No conflict resolutions available
        else:
            for key, value in module_names.items():
                if value['count'] != 1 and noConflicts == True:
                    noConflicts = False
                    response = {"status": "CONFLICT", "conflicts": {key: [value['filename']]}}
                    print(f"ERROR: Module {key} found in multiple files. Prompting user to resolve conflicts.")
                elif value['count'] != 1:
                    if key not in response['conflicts']:
                        response['conflicts'][key] = [value['filename']]
                    else:
                        response['conflicts'][key].append(value['filename'])
                    print(f"ERROR: Module {key} found in multiple files. Prompting user to resolve conflicts.")

        if noConflicts:
            result_jsoncontent = {"/jade.html": {"tests": {}, "state": {}, "last_saved": 0}} # Initialize JSON file
            for module in module_names:
                with open(module_names[module]['filename'][0],'r') as jsonfile_FP:
                    jsoncontent = json.load(jsonfile_FP)

                jsoncontent = {k: v for k, v in jsoncontent.items() if k == "/jade.html"}
                innercontent = json.loads(jsoncontent["/jade.html"])

                result_jsoncontent["/jade.html"]["tests"].update({k: v for k, v in innercontent["tests"].items() if k == module})
                result_jsoncontent["/jade.html"]["state"].update({k: v for k, v in innercontent["state"].items() if k == module})

            result_jsoncontent["/jade.html"] = json.dumps(result_jsoncontent["/jade.html"])
            with open(file_name,'w') as f:
                f.write(json.dumps(result_jsoncontent))
            response = {"status": "SUCCESS", "filename": file_name}
        
        response = json.dumps(response)
        response = str(response)
        
        if (noConflicts == True):
            self.send_response(200)
        else:
            self.send_response(409)
        self.send_header("Content-type", 'text/plain')
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        if (type(response) == str):
            response = response.encode('utf-8')
        self.wfile.write(response)

    def send_error(self, e):
        response = str(e)
        self.send_response(400)
        self.send_header("Content-type", 'text/plain')
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        if (type(response) == str):
            response = response.encode('utf-8')
        self.wfile.write(response)
        
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