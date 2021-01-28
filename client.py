#!/usr/bin/env python3
"""This is the GUI implementation of the client
GUI move forward in only few paths, hence it very nicely follows the DFA"""

__author__ = "Prasenjit Gaurav"

import socket 
from tkinter import *
import threading
from pdu import *
from xml.etree import ElementTree as xml_parser


"""Host is setup on localhost for now, but to test on in real ground, host variable needs to be changed to whatever IP the server is on"""
host = '127.0.0.1'		
port = 13001

class ClientGUI:
	"""This is the main GUI class"""
	def __init__(self, master):
		self.master = master
		master.title("MyChat")
		geometry = "700x550"
		master.geometry(geometry)
		self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
		self.host = host
		self.port = port
		self.parser = recieving_pdu()
		self.state = ["START", "INIT", "ESTABLISHED", "STATUS", "MESSAGE", \
						"FRIEND-REQUEST", "SEARCH", "REGISTRATION", "RESET"]
		self.random_ID = 0
		self.user_ID = ''
		self.registered = 0




	def start_frame(self):
		"""This is the start page of the application"""
		self.curr_state = 'START'
		self.data = "Output will appear here!"
		self.text_input_label = Label(self.master, text="Message")
		self.text_input_entry = Entry(self.master)
		self.text_output_label = Label(self.master, text="Output will go here")
		self.stop_button = Button(self.master, text='EXIT', width=20, command=self.close_gui)
		self.start_button = Button(self.master, text='START', width=20, command= self.start)
		self.reg_button = Button(self.master, text = "Register")
		self.search_button = Button(self.master)
		self.chat_window = Text(self.master, state = DISABLED)

		self.text_input_label.grid(row=0, columnspan=4,rowspan=2, sticky=E+W)
		self.start_button.grid(row=3, column=0, sticky=W)
		self.stop_button.grid(row=3, column=3, sticky=E)
		self.text_output_label.grid(row=4, columnspan=4, sticky=E+W)

	def start(self):
		"""This function establishes and reestablishes the connection and provide all the function of the chat based on the user
		This also does the handshake"""
		try:
			self.sock.connect((host,port))
		except OSError:
			pass
		self.curr_state = self.state[0]
		start_pdu = sending_pdu("SYN")
		if self.registered == 1:
			start_pdu.load_options('1')
			with open("profile.conf", 'r') as f:
				start_pdu.load_payload(f.read().encode('utf8'))
		else:
			try:
				with open("profile.conf", 'r') as f:
					start_pdu.load_payload(f.read().encode('utf8'))
					start_pdu.load_options('1')
					self.registered = 1
			except:
				self.registered = 0
				start_pdu.load_options('0')
		self.sock.send(start_pdu.get_pdu())
		self.curr_state = self.state[1]
		data = self.sock.recv(64)
		size = self.parser.get_size(data)
		if size - 64 > 0:
			data += self.sock.recv(size - 64)
		message = self.parser.get_message(data)
		if message == "OK":
				print("Message recieved", message)
				self.random_ID = self.parser.get_RID(data)
				self.curr_state = self.state[2]
				self.master.title("MyChat "+str(self.random_ID))
		if  self.curr_state == self.state[2]:
			if self.registered == 0:
				self.unregistered_main_workflow()
			else:
				self.registered_main_workflow()

	def unregistered_main_workflow(self):
		"""This is the main page for unregistered user after the handshake"""
		self.start_button.config(text="RANDOM CHAT", command = self.random_chat_workflow)
		self.text_input_label.config(text="Enter ID to search. Enter 0 to chat with random people.")
		self.reg_button.grid(row = 3, column = 2)
		self.reg_button.config(command = self.reg_workflow)

	def registered_main_workflow(self):
		"""This is the main page for the registered users after the handshake"""
		self.chat_window.grid_forget()
		self.search_button.config(text = "Search", command = self.search_workflow)
		self.search_button.grid(row = 2, column = 4, sticky = W)
		self.text_input_entry.grid(row=2, column = 0, columnspan = 4, sticky=E+W)
		self.text_input_label.config(text = "Search 0 for chat with random person")
		self.start_button.config()
	

	def random_chat_workflow(self):
		"""this page handles the random chat and its workflow"""
		search_pdu = sending_pdu("SEARCH", None, self.random_ID)
		search_pdu.load_payload(b'0')
		self.sock.send(search_pdu.get_pdu())
		print("Random chat request sent")
		data = self.sock.recv(64)
		if self.parser.get_size(data) - 64 > 0:
			data += self.sock.recv(self.parser.get_size(data) - 64)
		print("Data recieved from server")
		if self.parser.get_message(data) is "OK":
			print("Connection Established to random")
			self.text_output_label.config(text = "Waiting for random person to respond")
			data = self.sock.recv(64)
			if self.parser.get_size(data) - 64 > 0:
				data += self.sock.recv(self.parser.get_size(data) - 64)
			if self.parser.get_message(data) is "RANDOM":
				random_id = self.parser.get_SID(data)
				self.text_input_label.config(text = "You are taking to a stranger")
				self.text_input_entry.grid(row = 6, column = 0, columnspan = 3, sticky=E+W)
				self.chat_window.grid(row = 2, rowspan = 4, column = 0, columnspan = 3)
				self.start_button.config(text='Send', command = lambda: self.send_pressed_random(random_id))
				self.start_button.grid(row=7, column = 0, sticky = E)
				self.reg_button.config(text="Stop", command = lambda: self.stop_chat_random(random_id))
				self.reg_button.grid(row=7, column =1)
				self.stop_button.grid(row=7, column = 2, sticky = W)
				self.text_output_label.grid(row=8, column=0, columnspan=3, sticky=E+W)
		
			elif self.parser.get_message is "ERROR":
				self.text_output_label.config(text = self.parser.get_payload(data).decode('utf8'))


	def check_for_random_messages(self, randid):
		"""This function continuously keeps checking for new messages in the background and if any new
		message arrives, it updates the GUI"""
		status_pdu = sending_pdu("STATUS", randid, self.random_ID)
		self.sock.send(status_pdu.get_pdu())
		data  = self.sock.recv(64)
		if self.parser.get_size(data)-64 >0:
			data += self.sock.recv(self.parser.get_size(data)-64)
		print("Message recieved is:  ", self.parser.get_message(data))
		print("Payload", self.parser.get_payload(data).decode('utf8'))
		if self.parser.get_message(data) is "STATUS":
			if len(data) > 64:
				data_string = xml_parser.fromstring(self.parser.get_payload(data).decode('utf8'))
				for tags in data_string:
					print("tags", tags)
					if tags:
						for users in tags:
							print("users", users)
							if users:
								counter = 0
								for data in users:
									print("data", data)
									if counter == 0:
										msg = data.text
										counter += 1
									else:
										self.chat_window.config(state = NORMAL)
										self.chat_window.insert(END, msg+'\n')
										self.chat_window.config(state = DISABLED)
		else:
			self.text_output_label.config(text = "No msg recieved yet")
		self.master.after(5000, func = lambda: self.check_for_random_messages(randid))
		pass

	def send_pressed_random(self, randid):
		self.chat_window.config(state = NORMAL)
		self.chat_window.insert(END, self.text_input_entry.get()+'\n')
		self.chat_window.config(state = DISABLED)
		self.text_input_entry.delete(0, END)
		message_pdu = sending_pdu("MESSAGE", randid, self.random_ID)
		msg = self.text_input_entry.get()
		print(msg)
		message_pdu.load_payload(msg.encode('utf8'))
		message_pdu.load_options('10')
		self.sock.send(message_pdu.get_pdu())
		self.start_button.config(state=DISABLED)
		data = self.sock.recv(64)
		if self.parser.get_size(data)-64 > 0:
			self.sock.recv(self.parser.get_size(data))
		if self.parser.get_message(data) is "OK":
			self.start_button.config(state = ACTIVE)
			self.text_output_label.config(text = "Message sent")
		self.master.after(1000, func = lambda: self.check_for_random_messages(randid))


	def stop_chat_random(self, randid):
		fin_pdu = sending_pdu("FIN", randid, self.random_ID)
		self.sock.send(fin_pdu.get_pdu())
		data = self.sock.recv(64)
		if self.parser.get_size(data) - 64 > 0:
			data += self.sock.recv(self.parser.get_size(data)-64)
		if self.parser.get_message(data) is "OK":
			self.unregistered_main_workflow()
		if self.parser.get_message(data) is "ERROR":
			self.text_output_label.config(text = self.parser.get_payload(data).decode('utf8'))
			self.unregistered_main_workflow()



	def search_workflow(self):
		search_pdu = sending_pdu("SEARCH", self.random_ID)
		search_pdu.load_payload(self.text_input_entry.get().encode('utf8'))
		print("Search button is working")

	def reg_workflow(self):
		self.text_input_entry.delete(0, END)
		self.text_input_entry.grid(row=2, column=0, columnspan=4, sticky=E+W)
		self.start_button.config(text = "HOME", command = self.unregistered_main_workflow)
		self.text_input_label.config(text='Enter a desired user ID')
		self.reg_button.config(command = self.reg_button_clicked)


	def reg_button_clicked(self):
		if len(self.text_input_entry.get()) != 0:
			reg_pdu = sending_pdu("REG", None, self.random_ID)
			reg_pdu.load_payload(self.text_input_entry.get().encode('utf8'))
			self.user_ID = self.text_input_entry.get()
			self.text_input_entry.delete(0, END)
			self.start_button.config(state = DISABLED)			
			self.reg_button.config(state = DISABLED)
			reg_pdu.options = '0'
			self.sock.send(reg_pdu.get_pdu())
			data = self.sock.recv(64)
			print('in reg button, message recvd: ', self.parser.get_message(data))
			if self.parser.get_size(data)-64 > 0:
				data += self.sock.recv(self.parser.get_size(data)-64)
			print('Error: ', self.parser.get_payload(data).decode('utf8'),' + ', self.parser.get_size(data))
			if self.parser.get_checksum(data) == self.parser.gen_checksum(self.parser.get_payload(data)):
				if self.parser.get_message(data) is "OK":
					self.text_input_label.config(text = "Enter OTP")
					self.reg_button.configure(text = "Send", command = self.send_otp, state = ACTIVE)
					self.start_button.config(text = 'Cancel', command = self.cancel_registration, state = ACTIVE)
				elif self.parser.get_message(data) is "ERROR":
					self.text_output_label.config(text = self.parser.get_payload(data).decode('utf8'))
					self.reg_button.config(state = ACTIVE)

	def send_otp(self):
		if len(self.text_input_entry.get()) != 0:
			self.reg_button.config(state = DISABLED)
			self.start_button.config(state = DISABLED)
			reg_pdu = sending_pdu("REG", None, self.random_ID)
			reg_pdu.load_payload(self.text_input_entry.get().encode('utf8'))
			self.text_input_entry.delete(0, END)
			reg_pdu.options = '1'
			self.sock.send(reg_pdu.get_pdu())
			data = self.sock.recv(64)
			if self.parser.get_size(data)-64 > 0:
				data += self.sock.recv(self.parser.get_size(data)-64)
			if self.parser.get_checksum(data) == self.parser.gen_checksum(self.parser.get_payload(data)):
				if self.parser.get_message(data) is "OK" and self.parser.get_options(data)&0b111 == 6:
					self.registered = 1
					self.master.title(self.user_ID)
					with open("profile.conf", "w") as f:
						data_string = str(self.user_ID)+'\n'+self.parser.get_payload(data).decode('utf8')
						print(data_string)
						f.write(data_string)
					self.text_input_entry.grid_forget()
					self.reg_button.grid_forget()
					self.start_frame()
				elif self.parser.get_message(data) is "ERROR":
					self.text_output_label.config(text = self.parser.get_payload(data).decode('utf8'))
					self.reg_button.config(state = ACTIVE)
					self.start_button.config(state = ACTIVE)

	def cancel_registration(self):
		self.text_input_entry.delete(0, END)
		self.reg_button.config(state = DISABLED)
		self.start_button.config(state = DISABLED)
		reset_pdu = sending_pdu("RESET", None, self.random_ID)
		reset_pdu.options = '1'
		self.sock.send(reset_pdu.get_pdu())
		data = self.sock.recv(64)
		if self.parser.get_size(data)-64 > 0:
			data += self.sock.recv(self.parser.get_size(data)-64)
		if self.parser.get_checksum(data) == self.parser.gen_checksum(self.parser.get_payload(data)):
			if self.parser.get_message(data) is "OK":
				self.text_input_entry.grid_forget()
				self.reg_button.grid_forget()
				self.start_frame()


	def close_gui(self):
		self.sock.close()
		self.master.destroy()

if __name__ == '__main__': 	

	root = Tk()
	ClientGUI(root).start_frame()
	root.mainloop()

