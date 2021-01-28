#!/usr/bin/env python3
"""This is the server program designed to handle as many connection as the system can allow
The server plays the central role in the chat, every request is sent to the server and stored here
Then the server places those request in each individual users database 
That database is requested access through "STATUS" pdu
"""
__author__ = "Prasenjit Gaurav"


import socket
import threading
from pdu import sending_pdu, recieving_pdu
from random import getrandbits as randomgenerator
from random import choices as tokengenerator
from collections import deque as queue
import string
import xml.etree.ElementTree as xml_maker


print_lock = threading.Lock()                   #basix threading lock
semaphore = threading.BoundedSemaphore(2)       #semaphore with max allowing thread of 2
barrier = threading.Barrier(2)                  #barrier with least number of allowing thread 2
port = 13001                                    #Hard wired port for the chat
user_data = threading.local()                   #Thread local data storage to store information like random id, userid etc

class data_storage:
    """This is the storage class for registered users, it has many features in order to enable all
    the features of the chat"""
    frq = []
    frq_sent = []
    messages = {}
    read_messages = {}
    files = {}
    friends = []
    random_chat_partner = 0
class random_data_storage:
    """This is the storage class for unregistered user. Since they can only talk to people
    it has messages and partner chat it stored"""
    random_chat_partner = 0
    messages = queue()

class ThreadedServer(object):
    """This is the main class for the server which has the gui implementation following the
    DFA of my protocol"""
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.random_pool = queue()
        self.token_pool = []
        self.random_chat_agreement = []
        self.users = {}
        self.rand_to_userid = {}
        self.random_data = {}
        self.state = ["START", "INIT", "ESTABLISHED", "REGISTRATION"]        

    def listen(self):
        """This method listens to the socket and on each request creates a new thread"""
        self.sock.listen(5)
        while True:
            client, address = self.sock.accept()
            # client.settimeout(60)
            random_id = self.get_ID()
            threading.Thread(target = self.listenToClient,args = (client,address), name = random_id).start()

    def listenToClient(self, client, address):
        """This is the main thread function which runs all the time and collects data through the socket
        and then sends it to appropriate handle.
        It takes care of the state of the protocol and if anything unknown happens, it shuts down the port
        and close the thread"""
        curr_state = self.state[0]
        parser = recieving_pdu()
        user_data.dict = {}
        while True:
            try:
                data = client.recv(64)
                if data:
                    size = parser.get_size(data)-64
                    while True:
                        if size > 1024:
                            data += client.recv(1024)
                            size -= 1024
                        else:
                            data += client.recv(size)
                            break
                    if curr_state == self.state[0]:
                        if parser.get_message(data) is "SYN":
                            response, curr_state = self.handle_syn(data, parser)
                            client.send(response)
                            curr_state = self.state[2]
                        else:
                            raise ConnectionError("Client out of sync. Connection reset")
                    elif curr_state == self.state[2]:
                        msg = parser.get_message(data)
                        if msg is "REG":
                            curr_state = self.state[3]
                            curr_state = self.handle_registration(client, data, parser)
                        elif msg is "MESSAGE":
                            self.handle_messages(client, data, parser)
                        elif msg is "STATUS":
                            self.handle_status(client, data, parser)
                        elif msg is "FRQ":
                            self.handle_frq(client, data, parser)
                        elif msg is "SEARCH":
                            self.handle_search(client, data, parser)
                        elif msg is "FIN":
                            self.handle_fin(client, data, parser)
                        elif msg is "RESET":
                            ok_pdu = sending_pdu("OK", parser.get_SID(data))
                            ok_pdu.options = '100'
                            client.send(ok_pdu.get_pdu())
                            self.outof_rand_pool()
                            self.clear_rand_to_userid()
                            self.write_data(user_data.id)
                            raise ConnectionResetError("Connection resetted by the user")
                        else:
                            error_pdu = sending_pdu("ERROR")
                            error_pdu.load_payload(b"An error has occured")
                            client.send(error_pdu.get_pdu())
                else:
                    raise ConnectionResetError('Client disconnected')
            except Exception as e:
                client.close()
                print_lock.acquire()
                print(str(e))
                print_lock.release()
                return False

    def handle_syn(self, pdu, parser):
        """This function handles the initial handshake
        through a single SYN pdu, it can determine if the user is already registered or not"""
        if parser.get_version(pdu) == 0:
            if parser.get_options(pdu)&0xffff == 0:
                user_data.random = int(threading.current_thread().name)
                self.into_rand_pool()
                print_lock.acquire()
                self.random_data[user_data.random] = random_data_storage()
                print_lock.release()
                return sending_pdu("OK", user_data.random).get_pdu(), self.state[1]
            elif parser.get_options(pdu)&0xffff == 1:
                payload = parser.get_payload(pdu).decode('utf8')
                userid, token = payload.split('\n')
                if self.is_already_a_user(userid):
                    if self.check_token(userid, token):
                        random_id = int(threading.current_thread().name)
                        response = sending_pdu("OK", random_id).get_pdu()
                        self.read_data(userid)
                        user_data.random = random_id
                        user_data.id = userid
                        self.rand_join_to_id()
                        return response, self.state[1]
                error_pdu = sending_pdu("ERROR")
                error_pdu.load_payload(b"User ID and token doesn't match")
                return error_pdu.get_pdu(), self.state[0]
        else:
            error_pdu = sending_pdu("ERROR")
            error_pdu.load_payload(b"Version Mismatch")
            return error_pdu.get_pdu(), self.state[0]

    def handle_messages(self, client, data, parser):
        """This thread handles messages and place those messages into the users data
        It also creates token for files and save them to the server, once requested for the file download,
        it sends the file directly to the user"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            if parser.get_options(data)&0b1 == 0:
                print_lock.acquire()
                if (parser.get_options(data)>>1)&0b1 == 0:
                    rid = parser.get_RID(data)
                    sid = self.rand_to_userid[parser.get_SID(data)]
                    try:
                        self.users[self.rand_to_userid[rid]].messages[sid].append(data)
                    except KeyError:
                        self.users[self.rand_to_userid[rid]].messages[sid] = []
                        self.users[self.rand_to_userid[rid]].messages[sid].append(data)
                else:
                    rid = parser.get_RID(data)
                    sid = parser.get_SID(data)
                    if rid in self.rand_to_userid:
                        ruserid = self.rand_to_userid[rid]
                        if self.users[ruserid].random_chat_partner == sid:
                            try:
                                self.users[ruserid].messages[sid].append(data)
                            except KeyError:
                                self.users[ruserid].messages[sid] = []
                                self.users[ruserid].messages[sid].append(data)
                        else:
                            error_pdu = sending_pdu("ERROR", sid)
                            error_pdu.load_options('1000000')
                            error_pdu.load_payload(b"The user has already disconnected")
                            client.send(error_pdu.get_pdu())
                            print_lock.release()
                            return
                    else:
                        if self.random_data[rid].random_chat_partner == sid:
                            self.random_data[rid].messages.append(data)
                        else:
                            error_pdu = sending_pdu("ERROR", sid)
                            error_pdu.load_options('1000000')
                            error_pdu.load_payload(b"The user has already disconnected")
                            client.send(error_pdu.get_pdu())
                            print_lock.release()
                            return
                print_lock.release()

            else:
                file_name = self.get_token(16)+'.'+parser.get_filetype(data)
                with open(file_name, 'wb') as f:
                    f.write(parser.get_payload(data))
                print_lock.acquire()
                if parser.get_options(data)&0b10 == 0:
                    rid = parser.get_RID(data)
                    sid = parser.get_SID(data)
                    sid = self.rand_to_userid[sid]
                    try:
                        self.users[self.rand_to_userid[rid]].files[parser.get_SID(data)].append(file_name)
                    except KeyError:
                        self.users[self.rand_to_userid[rid]].files[parser.get_SID(data)] = []
                        self.users[self.rand_to_userid[rid]].files[parser.get_SID(data)].append(file_name)
                else:
                    rid = parser.get_RID(data)
                    sid = parser.get_SID(data)
                    if rid in self.rand_to_userid:
                        ruserid = self.rand_to_userid[rid]
                        if self.users[ruserid].random_chat_partner == sid:
                            try:
                                self.users[ruserid].files[sid].append(file_name)
                            except KeyError:
                                self.users[ruserid].files[sid] = []
                                self.users[ruserid].files[sid].append(file_name)
                        else:
                            error_pdu = sending_pdu("ERROR", sid)
                            error_pdu.load_options('1000000')
                            error_pdu.load_payload(b"The user has already disconnected")
                            client.send(error_pdu.get_pdu())
                            print_lock.release()
                            return
                print_lock.release()

            ok_pdu = sending_pdu("OK", parser.get_SID(data))
            ok_pdu.load_options('1000')
            client.send(ok_pdu.get_pdu())

        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.load_payload(b"Checksum Error")
            error_pdu.options = '10'
            client.send(error_pdu.get_pdu())
    
    def handle_fin(self, client, data, parser):
        """This is FIN handler, this is just a flag for random chat closing from any of the sides"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            rid = parser.get_RID(data)
            sid = parser.get_SID(data)
            print_lock.acquire()
            if sid in self.rand_to_userid:
                suserid = self.rand_to_userid[rid]
                self.users[suserid].random_chat_partner = 0
            else:
                self.random_data[sid].random_chat_partner = 0
            print_lock.release()

            ok_pdu = sending_pdu("OK", sid)
            ok_pdu.load_options('1000000')
            client.send(ok_pdu.get_pdu())

        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.load_payload(b"Checksum Error")
            error_pdu.options = '10'
            client.send(error_pdu.get_pdu())

    def handle_status(self, client, data, parser):
        """This function collect every new notification for the user, put them into an XML file
        and sends it to the user
        If induvidual messages asked, it sends messages for only one person, in XML
        If file is requested, it sends the file"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            print_lock.acquire()
            if parser.get_RID(data) == 0:
                rid = parser.get_RID(data)
                sid = parser.get_SID(data)                
                status_pdu = sending_pdu("STATUS", sid, rid)

                data_string = xml_maker.Element('data')
                msg = xml_maker.SubElement(data_string, 'message')

                for people in self.users[self.rand_to_userid[sid]].messages.keys():
                    user = xml_maker.SubElement(msg, 'sender')
                    user.text = people
                    for item in self.users[self.rand_to_userid[sid]].message[people]:
                        msg_data = xml_maker.SubElement(user, 'msg')
                        msg_data.text = parser.get_payload(item).decode('utf8')
                        time_data = xml_maker.SubElement(user, 'time')
                        time_data.text = str(parser.get_time(item))
                self.users[self.rand_to_userid[sid]].messages.clear()

                contact = xml_maker.SubElement(data_string, 'frq')
                for people in self.users[self.rand_to_userid[sid]].frq:
                    people_data = xml_maker.SubElement(contact, 'request')
                    people_data.text = people

            else:
                rid = parser.get_RID(data)
                sid = parser.get_SID(data)                
                status_pdu = sending_pdu("STATUS", sid, rid)

                data_string = xml_maker.Element('data')
                msg = xml_maker.SubElement(data_string, 'message')

                if sid in self.rand_to_userid:
                    suserid = self.rand_to_userid[sid]
                    if parser.get_size(data) > 64:
                        ruserid = parser.get_payload(data).decode('utf8')
                        try:
                            msg_list = self.users[suserid].messages[ruserid][:]
                            user = xml_maker.SubElement(msg, 'sender')
                            user.text = ruserid
                            for item in msg_list:
                                msg_data = xml_maker.SubElement(user, 'msg')
                                msg_data.text = parser.get_payload(item).decode('utf8')
                                time_data = xml_maker.SubElement(user, 'time')
                                time_data.text = str(parser.get_time(item))
                            del self.users[suserid].messages[ruserid]
                        except KeyError:
                            user = xml_maker.SubElement(msg, 'sender')
                    else:
                        if self.users[suserid].random_chat_partner == rid:
                            try:
                                msg_list = self.users[suserid].messages[rid][:]
                                user = xml_maker.SubElement(msg, 'sender')
                                user.text = ruserid
                                for item in msg_list:
                                    msg_data = xml_maker.SubElement(user, 'msg')
                                    msg_data.text = parser.get_payload(msg).decode('utf8')
                                    time_data = xml_maker.SubElement(user, 'time')
                                    time_data.text = str(parser.get_time(msg))
                                del self.users[suserid].messages[rid]
                            except KeyError:
                                user = xml_maker.SubElement(msg, 'sender')
                        else:
                            error_pdu = sending_pdu("ERROR", sid)
                            error_pdu.load_options("1000000")
                            error_pdu.load_payload(b"User already disconnected")
                            client.send(error_pdu.get_pdu())
                            print_lock.release()
                            return
                else:
                    if self.random_data[rid].random_chat_partner == sid:
                        try:
                            user = xml_maker.SubElement(msg, 'sender')
                            user.text = rid
                            while self.random_data[sid].messages:
                                item = self.random_data[sid].messages.popleft()
                                msg_data = xml_maker.SubElement(user, 'msg')
                                msg_data.text = parser.get_payload(item).decode('utf8')
                        except KeyError:
                            user = xml_maker.SubElement(msg, 'sender')
                    else:
                        error_pdu = sending_pdu("ERROR", sid)
                        error_pdu.load_options("1000000")
                        error_pdu.load_payload(b"User already disconnected")
                        client.send(error_pdu.get_pdu())
                        print_lock.release()
                        return
            print(xml_maker.dump(data_string))
            print_lock.release()
            status_pdu.load_payload(xml_maker.tostring(data_string, encoding='utf8'))
            client.send(status_pdu.get_pdu())
        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.options = '10'
            error_pdu.load_payload(b"Checksum Error")
            client.send(error_pdu.get_pdu())

    def handle_frq(self, client, data, parser):
        """This function handles friend requests
        If both users have sent each other request, they both are added as each other friend"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            if parser.get_size(data) > 64:
                userid = parser.get_payload(data).decode('utf8')
                print_lock.acquire()
                if userid in self.users[user_data.id].frq_sent:
                    self.users[user_data.id].friends.append(userid)
                    self.users[userid].friends.append(user_data.id)

                    self.users[userid].frq_sent.remove(user_data.id)
                    self.users[user_data.id].frq.remove(userid)

                    try:
                        self.users[user_data.id].frq_sent.remove(userid)
                    except ValueError:
                        pass
                    try:
                        self.users[userid].frq.remove(user_data.id)
                    except ValueError:
                        pass
                else:
                    self.users[user_data.id].frq_sent.append(userid)
                    self.users[userid].frq.append(user_data.id)
                print_lock.release()
            else:
                if parser.get_RID(data) in  self.rand_to_userid:
                    userid = self.rand_to_userid[parser.get_RID(data)]
                    print_lock.acquire()
                    self.users[userid].frq.append(user_data.id)
                    self.users[user_data.id].frq_sent.append(userid)
                    print_lock.release()
                else:
                    error_pdu = sending_pdu("ERROR", parser.get_SID(data))
                    error_pdu.options = '10'
                    error_pdu.load_payload(b"User disconnec ted, Friend request cannot be sent now")
                    client.send(error_pdu.get_pdu())
        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.options = '10'
            error_pdu.load_payload(b"Checksum Error")
            client.send(error_pdu.get_pdu())
    def handle_search(self, client, data, parser):
        """This function handles search
        for a search of zero, it returns RANDOM id based on smart algorithm"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            if parser.get_payload(data).decode('utf8') == '0':
                ok_pdu = sending_pdu("OK", parser.get_SID(data))
                ok_pdu.load_options('100000')
                client.send(ok_pdu.get_pdu())
                try:
                    semaphore.acquire()
                    self.random_chat_agreement.append(user_data.random)
                    barrier.wait(timeout=60)
                    random_id = [x for x in self.random_chat_agreement if x is not user_data.random][0]
                    self.random_chat_agreement.remove(random_id)
                    semaphore.release()
                    print_lock.acquire()
                    self.random_data[user_data.random].random_chat_partner = random_id
                    print("My:",user_data.random,'  Partner:', random_id)
                    print_lock.release()
                    random_pdu = sending_pdu("RANDOM", parser.get_SID(data), random_id)
                    client.send(random_pdu.get_pdu())
                except BrokenPipeError:
                    self.random_chat_agreement.remove(user_data.random)
                    semaphore.release()
                    error_pdu = sending_pdu("ERROR", parser.get_SID(data))
                    error_pdu.load_options('100000')
                    error_pdu.load_payload(b"No random users available to chat")
                    client.send(error_pdu.get_pdu())
            else:
                userid = parser.get_payload(data).decode('utf8')
                if self.is_already_a_user(userid):
                    ok_pdu = sending_pdu("OK", parser.get_SID(data), self.get_rand_from_userid(userid))
                    ok_pdu.load_options('100000')
                    client.send(ok_pdu.get_pdu())
            
        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.options = '10'
            error_pdu.load_payload(b"Checksum error")
            client.send(error_pdu.get_pdu())
    
    def handle_registration(self, client, data, parser, key=None, userid=None):
        """This function handles the registration on the users and create database entry for the users"""
        if parser.get_checksum(data) == parser.gen_checksum(parser.get_payload(data)):
            if parser.get_options(data)&0b1 == 0:
                userid = parser.get_payload(data).decode()
                if self.is_already_a_user(userid):
                    error_pdu = sending_pdu("ERROR", parser.get_SID(data))
                    error_pdu.options = '10'
                    error_pdu.load_payload(b"User id is already present, please try again with other username")
                    client.send(error_pdu.get_pdu())
                    return self.state[2]
                else:
                    ok_pdu = sending_pdu("OK", parser.get_SID(data))
                    ok_pdu.load_options('10')

                    client.send(ok_pdu.get_pdu())
                    client.settimeout(60)
                    try:
                        new_data = client.recv(64)
                        size = parser.get_size(new_data) - 64
                        new_data += client.recv(size)
                        client.settimeout(None)
                    except socket.timeout:
                        client.settimeout(None)
                        return self.state[2]
                    msg = parser.get_message(new_data)
                    if msg == 'REG':
                        return self.handle_registration(client, new_data, parser, self.regkeygenerator(), userid)
                    elif msg == "RESET":
                        ok_pdu = sending_pdu("OK", parser.get_SID(new_data))
                        ok_pdu.options = '100'
                        client.send(ok_pdu.get_pdu())
                        self.outof_rand_pool()
                        raise ConnectionResetError("Connection resetted by the user")
                    else:
                        raise ConnectionError("Registration failed, client out of sync")
            if parser.get_options(data)&0b1 == 1:
                regkey = parser.get_payload(data).decode()
                if regkey == key:
                    self.add_user(userid)
                    token = self.get_token(64)
                    ok_pdu = sending_pdu("OK", parser.get_SID(data))
                    ok_pdu.load_payload(token.encode('utf8'))
                    user_data.dict['token'] = token
                    ok_pdu.options = '110'
                    client.send(ok_pdu.get_pdu())
                    self.write_data(userid)
                    raise ConnectionResetError("User registered successfully")
                else:
                    error_pdu = sending_pdu("ERROR", parser.get_SID(data))
                    error_pdu.options = '10'
                    error_pdu.load_payload(b"Key is not correct, please try again with correct key")
                    client.send(error_pdu.get_pdu())
                    client.settimeout(300)
                    try:
                        new_data = client.recv(64)
                        new_data += client.recv(parser.get_size(new_data) - 64)
                        client.settimeout(None)
                    except socket.timeout:
                        client.settimeout(None)
                        return self.state[2]
                    self.handle_registration(client, new_data, parser, key, userid)
            

        else:
            error_pdu = sending_pdu("ERROR", parser.get_SID(data))
            error_pdu.options = '10'
            error_pdu.load_payload(b"Checksum Mismatch")
            client.send(error_pdu.get_pdu())
            return self.state[2]

"""Below are all the helper function"""
    def clear_rand_to_userid(self):
        print_lock.acquire()
        if user_data.random in self.rand_to_userid:
            del self.rand_to_userid[user_data.random]
    def rand_join_to_id(self):
        print_lock.acquire()
        self.rand_to_userid[user_data.random] = user_data.id
        print_lock.release()
    def into_rand_pool(self):
        print_lock.acquire()
        self.random_pool.append(user_data.random)
        print_lock.release()

    def outof_rand_pool(self):
        print_lock.acquire()
        if id in self.random_pool:
            self.random_pool.remove(user_data.random)
        print_lock.release()
    def get_rand_from_userid(self, userid):
        return list(self.rand_to_userid.keys())[list(self.rand_to_userid.values()).index(userid)]

    def check_token(self, userid, token):
        print_lock.acquire()
        if token == self.users[userid]['token']:
            print_lock.release()
            return True
        print_lock.release()
        return False

    def get_ID(self):
        while True:
            return_value = randomgenerator(64)
            if return_value not in self.random_pool:
                return return_value

    def get_token(self, length):
        print_lock.acquire()
        while True:
            return_value = ''.join(tokengenerator(string.ascii_letters + string.digits, k=length))
            if return_value not in self.token_pool:
                print_lock.release()
                return return_value

    def read_data(self, userid):
        print_lock.acquire()
        user_data.dict = {**user_data.dict, **self.users[userid]}
        print_lock.release()

    def write_data(self, userid):
        print_lock.acquire()
        self.users[userid] = {**self.users[userid], **user_data.dict}
        print_lock.release()

    def regkeygenerator(self):
        """ This method is meant to be overloaded with whatever Key Generation manner
            the protocol user chose to use
        """
        return '123456'
    
    def is_already_a_user(self,id):
        """ This method is meant to be overloaded to suit protocol user's preference
        of database to store USER IDs"""
        print_lock.acquire()
        answer = id in self.users.keys()
        print_lock.release()
        return answer

    def add_user(self,id):
        """ This method is meant to be overloaded to suit protocol user's preference
        of database to store USER IDs"""
        print_lock.acquire()
        self.users[id] = data_storage()
        print_lock.release()

    def safe_print(self, name):
        print_lock.acquire()
        print(str(name))
        print_lock.release()




if __name__ == "__main__":

    ThreadedServer('',port).listen()
