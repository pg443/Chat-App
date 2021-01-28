#!/usr/bin/env python3
""" PDU library to encode and decode the protocol data units for my custom protocol for Chat"""

__author__ = "Prasenjit Gaurav"
from datetime import datetime   # for UNIX timestamp
from zlib import adler32


file_format = {0:'png', 1:'jpg', 2:'gif', 3:'pdf', 4:'docx', 5:'pptx', 6:'xlsx'}

class sending_pdu:
    """This class is used to build the PDU for the chat protocol.
    It provides a very clean and easy API to initiate, change and load variables and data
    """
    def __init__(self, message, RID=None, SID=None):
        self.__messages = {
            "SYN" : 0,
            "OK" : 1,
            "REG" : 2,
            "RESET" : 3,
            "RANDOM" : 4,
            "MESSAGE" : 5,
            "FIN" : 6,
            "FRQ" : 7,
            "STATUS" : 8,
            "SEARCH" : 9,
            "ERROR" : 10
        }
        if message is not None:
            if not self.__is_validmessage(message):
                raise AttributeError("Not a valid message:", message)
        self.message = bin(self.__message2code(message))[2:].zfill(8)
        self.version = "0".zfill(4)
        self.data_encoding = "0"
        if RID is None:
            self.recvrs_ID = '0'.zfill(64)
        else:
            self.recvrs_ID = bin(RID)[2:].zfill(64)
        if SID is None:
            self.sendrs_ID = '0'.zfill(64)
        else:
            self.sendrs_ID = bin(SID)[2:].zfill(64)
        self.checksum = 0
        self.timestamp = bin(self.__gettime())[2:]
        self.payload_size = '0'
        self.file_type = '0'
        self.options = "0"
        self.sequence = 0
        self.reserve_space = '0'
        self.payload = b""
    

    def load_payload(self, data):
        """This function is used to attach the data to the PDU"""
        if not isinstance(data, bytes):
            raise TypeError("Data is expected to be 'bytes' object")
        self.payload = data

    def load_options(self, options):
        """This function is used to manipulate the options of the PDU"""
        if isinstance(options, str) and isinstance(int(options, 2), int):
            self.options = options
    def get_pdu(self):
        """Used to get the byte code of the PDU
        It gives the PDU in bytes form, so it is readymade for socket"""

        if len(self.payload) > 31208:  # 120mb = 31207 packets of each 4032bytes
            raise IOError("Payload size bigger than 120MB")
        self.checksum = bin(self.gen_checksum(self.payload))[2:]
        self.payload_size = bin(64 + len(self.payload))[2:]

        header1 = self.__binary_to_bytes(self.version.zfill(4) + self.message.zfill(8) + self.data_encoding.zfill(4) + self.options.zfill(16), 4)
        header2 = self.__binary_to_bytes(self.recvrs_ID, 8)
        header3 = self.__binary_to_bytes(self.sendrs_ID, 8)
        header4 = self.__binary_to_bytes(self.timestamp.zfill(32), 4)
        header5 = self.__binary_to_bytes(self.payload_size.zfill(28) + self.file_type.zfill(4) , 4)
        header6 = self.__binary_to_bytes(self.checksum.zfill(32) , 4)
        header7 = self.__binary_to_bytes(self.reserve_space.zfill(256), 32)
        return (header1 + header2 + header3 + header4 + header5 + header6 + header7 + self.payload)


    def gen_checksum(self, data):
        """Checksum generating algorithm"""
        return adler32(data)&0xfffffff

    def __is_validmessage(self, msg):
        if msg in self.__messages.keys():
            return  True
        return False
    def __message2code(self, msg):
        if msg in self.__messages:
            return self.__messages[msg]

    def __binary_to_bytes(self, bin_string, length):
        return int(bin_string, 2).to_bytes(length, byteorder='big')
    def __gettime(self):
        return int(datetime.utcnow().timestamp())

class recieving_pdu(sending_pdu):
    """This class is made on top of the sending_pdu class
    This class helps in recieving and parsing the PDU
    It also has very clean interface with all the function named as get_XXXXX
    These function output the result in their original form, i.e. str->str, int->int, byte->byte
    """
    def __init__(self):
        super()

    def get_size(self, stream):
        return int.from_bytes(stream[24:28], 'big')>>4
    def get_message(self, stream):
        msg = (int.from_bytes(stream[:4], 'big')>>20)&0xff
        if msg == 0:
            return "SYN"
        elif msg == 1:
            return "OK"
        elif msg == 2:
            return "REG"
        elif msg == 3:
            return "RESET"
        elif msg == 4:
            return "RANDOM"
        elif msg == 5:
            return "MESSAGE"
        elif msg == 6:
            return "FIN"
        elif msg == 7:
            return "FRQ"
        elif msg == 8:
            return "STATUS"
        elif msg == 9:
            return "SEARCH"
        elif msg == 10:
            return "ERROR"
    def get_payload(self, stream):
        return stream[64:]
    def get_checksum(self, stream):
        return int.from_bytes(stream[28:32], 'big')
    def get_options(self, stream):
        return int.from_bytes(stream[0:4], 'big')&0xffff
    def get_time(self, stream):
        time = int.from_bytes(stream[20:24], 'big')
        return datetime.utcfromtimestamp(time)
    def get_RID(self, stream):
        return int.from_bytes(stream[4:12], 'big')
    def get_SID(self, stream):
        return int.from_bytes(stream[12:20], 'big')
    def get_version(self, stream):
        return int.from_bytes(stream[0:4], 'big')&0xf0000000
    def get_filetype(self, stream):
        return file_format[int.from_bytes(stream[24:28], 'big')&0xf]


if __name__ == "__main__":
    mypdu = sending_pdu("SEARCH", 16465496, 56349429)
    payload = b'ghgjvcghc'
    mypdu.load_payload(payload)
    mypdu.load_options('00100')
    ram = mypdu.get_pdu()
    print(ram)
    z  =recieving_pdu()
    print(z.get_checksum(ram))
    print(z.gen_checksum(payload))
    print(z.get_options(ram))