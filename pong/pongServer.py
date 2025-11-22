# =================================================================================================
# Contributing Authors:	    <Anyone who touched the code>
# Email Addresses:          <Your uky.edu email addresses>
# Date:                     <The date the file was last edited>
# Purpose:                  <How this file contributes to the project>
# Misc:                     <Not Required.  Anything else you might want to include>
# =================================================================================================

import socket
import threading
import json
import time

#Initialization variables used to create game state and initialize the clients
SCREEN_WIDTH : int = 480
SCREEN_HEIGHT : int = 640
PADDLE_START_Y : int = (SCREEN_HEIGHT/2)

#Create dictionary to store current game state
game_data = {
    "left_paddle_y": PADDLE_START_Y,
    "right_paddle_y": PADDLE_START_Y,
    "ball_x": SCREEN_WIDTH/2,
    "ball_y": SCREEN_HEIGHT/2,
    "left_score": 0,
    "right_score": 0,
    "max_sync": 0
}

#Store ball pos and prospective scores to find most updated 
left_ball_pos : list[int] = [game_data["ball_x"], game_data["ball_y"]]
right_ball_pos : list[int] = [game_data["ball_x"], game_data["ball_y"]]
scores : list[list[int]] = [[0,0], [0,0]]

#Create a mutex
mutex = threading.Lock()

def acceptor() -> None:

# Author: Parker Jenkins
# Purpose: Accepts sockets and adds them to a list to track who is connected
# Pre: This method expects there to be clients not assigned a role
# Post: This method assigns users a role and allows them to start sending and recieving data

    while True:
        try:
            client_sock, client_addr = sock.accept()
            
            with mutex:
                client_sockets.append(client_sock)
                threading.Thread( target = handle_clients, args = (client_sock,)).start()
        except socket.timeout:
            pass

def handle_clients( conn : socket.socket) -> None:
    # Author: Parker Jenkins
    # Purpose: Accepts sockets and assigns them roles
    # Pre: This method expects there to be clients attempting to connect
    # Post: This method changes one of the global variables to store sockets with one pointing to the proper client

    global left_sock, right_sock, spec_sock #define as global so the value is non local
    paddle_side : str
    global left_sync
    global right_sync

    with mutex: #Place mutex lock to ensure only one in each paddle, rest are spectators
        
        #Add first connection to the left player
        if left_sock is None:
            left_sock = conn
            paddle_side = "left"
            print(f"LEFT SIDE IS: {left_sock}")

        #Add second connection to right side
        elif right_sock is None:
            right_sock = conn
            paddle_side = "right"
            print(f"RIGHT SIDE IS: {right_sock}")

        #Add everyone else to the spectators
        else:
            spec_sock.append(conn)
            paddle_side = "spectator"
        
    #Create initial game state dictionary to send at the start of the game to each player
    init_game_state : dict = {
        "screen_width" : SCREEN_WIDTH,
        "screen_height" : SCREEN_HEIGHT,
        "paddle" : paddle_side
    }
    try:
        #Send the initial game state
        conn.sendall(json.dumps(init_game_state).encode("utf-8"))
        
        #Stay in loop for sending and recieving data
        while True:    

            #If they are a player, recieve and parse data
            if conn not in spec_sock:
                msg : str = conn.recv(1024) #Recieve Data from client

                #If the message is empty break
                if not msg:
                    break

                #decode the string, then create a library out of it.
                data = json.loads(msg.decode("utf-8"))

                #Use a mutex to lock any shared variables
                with mutex:

                    #Update the game data with the data recieved from the left side
                    if conn == left_sock:
                        game_data["left_paddle_y"] =  data["paddle_y"]
                        left_sync = data["sync"]
                        left_ball_pos[0] = data["ball_x"]
                        left_ball_pos[1] = data["ball_y"]
                        scores[0][0] = data["lscore"]
                        scores[0][1] = data["rscore"]
                    #Update the game data with the data recieved from the right side
                    elif conn == right_sock:
                        game_data["right_paddle_y"] =  data["paddle_y"]
                        right_sync = data["sync"]
                        right_ball_pos[0] = data["ball_x"]
                        right_ball_pos[1] = data["ball_y"]
                        scores[1][0] = data["lscore"]
                        scores[1][1] = data["rscore"]
            #Recieve data from the spectators to ensure the connection is open
            elif conn in spec_sock:
                msg = conn.recv(1024)

                #If the message was empty, exit the loop
                if not msg:
                    break
    #After the try block, clear variables and close connection
    finally:
        with mutex:
           if conn == left_sock:
               left_sock = None
           elif conn == right_sock:
               right_sock = None
           elif conn in spec_sock:
               spec_sock.remove(conn)
           
           if conn in client_sockets:
               client_sockets.remove(conn)
       
        conn.close()

def update_game_vals() -> None:
    # Author: Parker Jenkins
    # Purpose: Decide which client is the most updated
    # Pre: This method expects there to be clients connected and transmitting
    # Post: This method changes the game state and transmits it to the clients

    while True:
        time.sleep(1/60) #Update 60 times per second, can change update rate in this line
        if left_sync != None and right_sync != None:
            with mutex:

            #If the left sync is higher, it is ahead, so use its values for score and ball position
                if left_sync > right_sync:
                    game_data["ball_x"] = left_ball_pos[0]
                    game_data["ball_y"] = left_ball_pos[1]
                    game_data["left_score"] = scores[0][0]
                    game_data["right_score"] = scores[0][1]
            #If the right sync is higher, it is ahead, so use its values for score and ball position
                else: 
                    game_data["ball_x"] = right_ball_pos[0]
                    game_data["ball_y"] = right_ball_pos[1]
                    game_data["left_score"] = scores[1][0]
                    game_data["right_score"] = scores[1][1]

            #Send the game state to the players
            if left_sock:
                left_sock.sendall(json.dumps(game_data).encode("utf-8"))
            if right_sock:
                right_sock.sendall(json.dumps(game_data).encode("utf-8"))
            if spec_sock:
                for c in spec_sock:
                    c.sendall(json.dumps(game_data).encode("utf-8"))


#These will store the sockets for each role
left_sock : socket.socket = None
right_sock : socket.socket = None
left_sync : int = None
right_sync : int = None
spec_sock : list[socket.socket] = list()

#This stores the needed IP and Port to establish a server
LAN_IP : str = "127.0.0.1"
PORT : int = 50000

#Create the socket and bind it
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((LAN_IP, PORT))

#This list tracks who is connected
client_sockets : list[socket.socket] = list()

#Listen to the socket for people attempting to connect and start a thread to accept them
sock.listen()
threading.Thread(target = acceptor).start()

threading.Thread(target=update_game_vals, daemon=True).start()

try:
    while True:
       time.sleep(1)
except KeyboardInterrupt:
    sock.close()